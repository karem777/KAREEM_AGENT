import json
import re
import queue
import subprocess
import threading
import time
from urllib.parse import urlparse


class BrowserTool:
    name = "browser"

    description = (
        "Control the user's existing Chrome session using Chrome DevTools MCP. "
        "Uses the currently selected page and dynamically resolves runtime page IDs."
    )

    def __init__(self):
        self._process = None
        self._lock = threading.RLock()
        self._request_id = 0
        self._initialized = False
        self._tools = {}
        self._stdout_queue = None
        self._stderr_lines = []
        self._reader_threads = []
        # Browser-session binding: once a web target is selected, every later
        # action is forced onto that exact runtime page. This prevents MCP
        # failures or tab drift from silently falling back to KAREEM_AGENT UI.
        self._bound_page_id = None
        self._expected_origin = None
        self._pending_target_url = None

    def _next_id(self):
        self._request_id += 1
        return self._request_id

    def _start_mcp(self):
        if self._process and self._process.poll() is None:
            return

        self._stdout_queue = queue.Queue()
        self._stderr_lines = []
        self._reader_threads = []

        self._process = subprocess.Popen(
            [
                "npx.cmd",
                "--yes",
                "chrome-devtools-mcp@latest",
                "--autoConnect",
                "--channel=stable",
                "--no-usage-statistics",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def read_stdout():
            try:
                for line in iter(self._process.stdout.readline, ""):
                    if self._stdout_queue is not None:
                        self._stdout_queue.put(line)
            except Exception as exc:
                if self._stdout_queue is not None:
                    self._stdout_queue.put({"__reader_error__": str(exc)})
            finally:
                if self._stdout_queue is not None:
                    self._stdout_queue.put({"__eof__": True})

        def read_stderr():
            try:
                for line in iter(self._process.stderr.readline, ""):
                    self._stderr_lines.append(line)
                    if len(self._stderr_lines) > 200:
                        del self._stderr_lines[:-200]
            except Exception:
                pass

        t1 = threading.Thread(target=read_stdout, daemon=True)
        t2 = threading.Thread(target=read_stderr, daemon=True)
        t1.start()
        t2.start()
        self._reader_threads = [t1, t2]

        time.sleep(0.5)

    def _send(self, method, params=None):
        self._start_mcp()

        if not self._process or not self._process.stdin:
            raise RuntimeError(
                "Chrome DevTools MCP process is unavailable."
            )

        request_id = self._next_id()

        self._process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        self._process.stdin.flush()

        deadline = time.time() + 30

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                stderr = "".join(self._stderr_lines)[-4000:]
                raise TimeoutError(
                    f"MCP request timed out after 30s: {method}"
                    + (f"\nMCP stderr:\n{stderr}" if stderr else "")
                )

            try:
                item = self._stdout_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self._process.poll() is not None:
                    stderr = "".join(self._stderr_lines)[-4000:]
                    raise RuntimeError(
                        "Chrome DevTools MCP exited."
                        + (f"\n{stderr}" if stderr else "")
                    )
                continue

            if isinstance(item, dict):
                if item.get("__eof__"):
                    stderr = "".join(self._stderr_lines)[-4000:]
                    raise RuntimeError(
                        "Chrome DevTools MCP closed stdout."
                        + (f"\n{stderr}" if stderr else "")
                    )
                if "__reader_error__" in item:
                    raise RuntimeError(
                        "Chrome DevTools MCP stdout reader failed: "
                        + str(item["__reader_error__"])
                    )
                continue

            line = str(item).strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except Exception:
                # Ignore non-JSON diagnostic lines emitted on stdout.
                continue

            if data.get("id") != request_id:
                continue

            if "error" in data:
                raise RuntimeError(
                    json.dumps(
                        data["error"],
                        ensure_ascii=False,
                    )
                )

            return data.get("result", {})

    def _initialize(self):
        if self._initialized:
            return

        self._send(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "KAREEM_AGENT",
                    "version": "1.1.0",
                },
            },
        )

        self._process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        self._process.stdin.flush()

        result = self._send(
            "tools/list",
            {},
        )

        self._tools = {
            item.get("name"): item
            for item in result.get("tools", [])
            if item.get("name")
        }

        self._initialized = True

    def _call(self, name, arguments=None):
        with self._lock:
            self._initialize()

            if name not in self._tools:
                result = self._send(
                    "tools/list",
                    {},
                )

                self._tools = {
                    item.get("name"): item
                    for item in result.get("tools", [])
                    if item.get("name")
                }

            if name not in self._tools:
                raise RuntimeError(
                    "Chrome DevTools MCP tool not found: "
                    + name
                )

            result = self._send(
                "tools/call",
                {
                    "name": name,
                    "arguments": arguments or {},
                },
            )

            text = "\n".join(
                item.get("text", "")
                for item in result.get("content", [])
                if item.get("type") == "text"
            ).strip()

            return {
                "success": not bool(
                    result.get("isError", False)
                ),
                "text": text,
                "raw": result,
            }

    def _extract_selected_page_id(self, text):
        match = re.search(
            r"(?m)^\s*(\d+):.*\[selected\]\s*$",
            str(text or ""),
        )

        if match:
            return int(
                match.group(1)
            )

        return None

    def _extract_first_page_id(self, text):
        text = str(text or "")
        m = re.search(r"(?m)^(?:Page ID|pageId|id)[:=]\s*(\d+)", text)
        if m:
            return int(m.group(1))
        m = re.search(r"(?m)\bpageId\s*[:=]\s*(\d+)", text)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _origin(url):
        try:
            parsed = urlparse(str(url or '').strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return None
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        except Exception:
            return None

    @classmethod
    def _is_agent_ui_url(cls, url):
        origin = cls._origin(url)
        return origin in {"http://127.0.0.1:5000", "http://localhost:5000"}

    @staticmethod
    def _root_url_from_snapshot(snapshot):
        m = re.search(r'RootWebArea\s+"[^"]*"\s+url="([^"]+)"', str(snapshot or ''))
        return m.group(1).strip() if m else ""

    def _resolve_bound_or_current(self, page_id=None):
        if page_id is not None:
            try:
                if int(page_id) > 0:
                    return int(page_id)
            except Exception:
                pass
        if self._bound_page_id is not None:
            return int(self._bound_page_id)
        return self._resolve_page_id(None)

    def _page_snapshot(self, page_id, verbose=False):
        self._call("select_page", {"pageId": int(page_id), "bringToFront": True})
        result = self._snapshot(int(page_id), verbose=verbose, retries=6, delay=0.5)
        return result.get("text", "")

    def _guard_bound_page(self, page_id, *, require_expected=True):
        page_id = int(page_id)
        if self._bound_page_id is not None and page_id != int(self._bound_page_id):
            raise RuntimeError("Browser page binding mismatch; refusing to act on another tab.")

        if not require_expected or not self._expected_origin:
            return

        snapshot = self._page_snapshot(page_id, verbose=False)
        actual_url = self._root_url_from_snapshot(snapshot)
        actual_origin = self._origin(actual_url)
        expected = self._expected_origin
        if actual_origin and actual_origin != expected:
            raise RuntimeError(
                f"Browser target drift detected: expected {expected}, got {actual_origin}."
            )

    def _resolve_page_id(self, page_id=None):
        if page_id is not None:
            try:
                page_id = int(page_id)
            except Exception:
                page_id = None

        # A bound page always wins when the caller did not explicitly name a page.
        # This is the core anti-drift rule.
        if page_id is None and self._bound_page_id is not None:
            return int(self._bound_page_id)

        if page_id is not None and page_id > 0:
            return page_id

        pages = self._call("list_pages", {})
        selected = self._extract_selected_page_id(pages.get("text", ""))
        if selected is None:
            raise RuntimeError("No selected Chrome page is available.")
        return selected

    def _error(self, exc):
        return {
            "success": False,
            "error": (
                "تعذر التحكم في Chrome الحالي."
            ),
            "details": str(exc),
        }

    def list_pages(self):
        try:
            result = self._call(
                "list_pages",
                {},
            )

            return {
                "success": result["success"],
                "text": result["text"],
                "selected_page_id": (
                    self._extract_selected_page_id(
                        result["text"]
                    )
                ),
            }

        except Exception as exc:
            return self._error(exc)

    def current_page(self):
        return self.list_pages()

    def open_url(self, url, page_id=None, new_tab=False):
        try:
            url = str(url or "").strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("open_url requires a valid http(s) URL.")

            target_origin = self._origin(url)
            self._pending_target_url = url

            if page_id is not None:
                try:
                    if int(page_id) <= 0:
                        page_id = None
                except Exception:
                    page_id = None

            selected_page = None
            if page_id is None:
                if self._bound_page_id is not None:
                    selected_page = int(self._bound_page_id)
                else:
                    selected_page = self._resolve_page_id(None)

            # Never navigate the agent's own Flask UI to an external site.
            # Instead create a real browser page and bind to it. This removes the
            # self-control deadlock that caused V6 to fill the agent chat box.
            if selected_page is not None and self._is_agent_ui_url(
                self._root_url_from_snapshot(self._page_snapshot(selected_page, verbose=False))
            ) and not self._is_agent_ui_url(url):
                result = self._call("new_page", {"url": url, "background": False})
                new_id = (
                    self._extract_first_page_id(result.get("text", ""))
                    or self._extract_selected_page_id(result.get("text", ""))
                )
                if not new_id:
                    # Last chance: list pages and use the selected one returned by MCP.
                    pages = self._call("list_pages", {})
                    new_id = self._extract_selected_page_id(pages.get("text", ""))
                if not new_id:
                    raise RuntimeError("MCP created the target page but did not expose a runtime page ID.")
                self._bound_page_id = int(new_id)
                self._expected_origin = target_origin
                self._pending_target_url = url
                # Verify before handing control back to the planner.
                snapshot = self._page_snapshot(new_id, verbose=False)
                actual = self._origin(self._root_url_from_snapshot(snapshot))
                if actual and actual != target_origin:
                    raise RuntimeError(f"Opened page drifted to {actual}; expected {target_origin}.")
                return {
                    "success": True,
                    "url": url,
                    "page_id": int(new_id),
                    "reused": False,
                    "text": result.get("text", ""),
                    "bound": True,
                }

            if page_id is None:
                page_id = selected_page
            page_id = self._resolve_page_id(page_id)

            # An explicit external target creates a binding before navigation.
            # A failure therefore cannot fall through to a different selected tab.
            self._bound_page_id = int(page_id)
            self._expected_origin = target_origin

            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            result = self._call(
                "navigate_page",
                {"pageId": page_id, "type": "url", "url": url},
            )

            selected = self._extract_selected_page_id(result.get("text", "")) or int(page_id)
            self._bound_page_id = int(selected)

            snapshot = self._page_snapshot(selected, verbose=False)
            actual_url = self._root_url_from_snapshot(snapshot)
            actual_origin = self._origin(actual_url)
            if actual_origin and actual_origin != target_origin:
                raise RuntimeError(f"Navigation completed on unexpected origin {actual_origin} (expected {target_origin}).")

            self._pending_target_url = None
            return {
                "success": bool(result["success"]),
                "url": url,
                "page_id": int(selected),
                "text": result["text"],
                "bound": True,
                "actual_url": actual_url,
            }

        except Exception as exc:
            # Preserve the binding/expected origin so subsequent inspect/action calls
            # fail closed instead of silently selecting KAREEM_AGENT UI.
            return self._error(exc)

    def inspect(self, page_id=None, verbose=False):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            result = self._page_snapshot(page_id, verbose=verbose)
            return {
                "success": True,
                "page_id": page_id,
                "snapshot": result,
                "text": result,
                "url": self._root_url_from_snapshot(result),
                "bound": self._bound_page_id is not None,
            }
        except Exception as exc:
            return self._error(exc)

    def _find_uid_for_click(self, snapshot, selector=None, text=None, first_result=False):
        snapshot = str(snapshot or "")
        selector = str(selector or "").strip()
        text = str(text or "").strip()

        # Extract an XPath-ish contains(text(), '...') hint when the model emits one.
        if selector:
            match = re.search(r"contains\s*\(\s*text\(\)\s*,\s*['\"]([^'\"]+)['\"]", selector, flags=re.IGNORECASE)
            if match:
                text = match.group(1).strip()

        # On a Google search-results page, a bare click request means
        # "open the first organic result" when no UID/text/selector was supplied.
        # The planner's natural-language description may carry that intent, but
        # the tool itself must remain deterministic because it does not receive
        # the full step description.
        google_results_page = (
            'نتائج البحث' in snapshot
            or 'Search results' in snapshot
            or 'google.com/search' in snapshot
        )
        if not selector and not text and not first_result and google_results_page:
            first_result = True

        # Prefer links inside the actual search results area.
        in_results = False
        candidates = []
        for line in snapshot.splitlines():
            if 'heading "نتائج البحث"' in line or 'heading "Search results"' in line:
                in_results = True
                continue
            if in_results and 'uid=' in line and ' link ' in line and 'url=' in line:
                m = re.search(r'uid=([^\s]+)\s+link\s+"([^"]*)"(?:\s+url="([^"]*)")?', line)
                if not m:
                    continue
                uid, label, url = m.group(1), m.group(2), (m.group(3) or '')
                # Skip navigation/Google-internal links for organic-result selection.
                if first_result:
                    lowered = url.lower()
                    if not url or lowered.startswith('https://www.google.com') or lowered.startswith('https://support.google.com'):
                        continue
                candidates.append((uid, label, url))
                if first_result and candidates:
                    return uid, label, url

        # Generic structural fallback: on Google, choose the first external
        # result-like link even if the exact heading marker changed slightly.
        if first_result and not candidates:
            for line in snapshot.splitlines():
                if 'uid=' not in line or ' link ' not in line or 'url=' not in line:
                    continue
                m = re.search(r'uid=([^\s]+)\s+link\s+"([^"]*)"(?:\s+url="([^"]*)")?', line)
                if not m:
                    continue
                uid, label, url = m.group(1), m.group(2), (m.group(3) or '')
                lowered = url.lower()
                if not url or lowered.startswith('https://www.google.com') or lowered.startswith('https://support.google.com'):
                    continue
                return uid, label, url

        # Text-directed click fallback over the full snapshot.
        if text:
            needle = text.casefold()
            for line in snapshot.splitlines():
                if 'uid=' not in line or ' link ' not in line or 'url=' not in line:
                    continue
                m = re.search(r'uid=([^\s]+)\s+link\s+"([^"]*)"(?:\s+url="([^"]*)")?', line)
                if m and needle in m.group(2).casefold():
                    return m.group(1), m.group(2), m.group(3) or ''

        return None

    def click(
        self,
        page_id=None,
        uid=None,
        selector=None,
        text=None,
        first_result=False,
        dbl_click=False,
    ):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)

            self._call(
                "select_page",
                {
                    "pageId": page_id,
                    "bringToFront": True,
                },
            )

            if self._is_agent_ui_url(self._root_url_from_snapshot(self._page_snapshot(page_id, verbose=False))) and self._pending_target_url and not self._is_agent_ui_url(self._pending_target_url):
                raise RuntimeError("Refusing to interact with KAREEM_AGENT UI while an external browser target is pending.")

            if uid is None or str(uid).strip() == "":
                snapshot_result = self._snapshot(page_id, verbose=False, retries=8, delay=0.75)
                found = self._find_uid_for_click(
                    snapshot_result.get("text", ""),
                    selector=selector,
                    text=text,
                    first_result=bool(first_result),
                )
                if not found:
                    raise RuntimeError("Could not resolve a clickable link from the current page snapshot.")
                uid, label, url = found
            else:
                label, url = None, None

            result = self._call(
                "click",
                {
                    "pageId": page_id,
                    "uid": str(uid),
                    "dblClick": bool(dbl_click),
                    "includeSnapshot": True,
                },
            )

            # A click can legitimately navigate the bound page to a different
            # origin. The old safety guard treated that as "drift" and then
            # blocked every subsequent inspect/action, even though the click
            # itself had succeeded. Rebase the browser session on the page that
            # the click actually reached before returning control to cognition.
            actual_url = self._root_url_from_snapshot(result.get("text", ""))
            actual_origin = self._origin(actual_url)
            selected_after_click = self._extract_selected_page_id(result.get("text", ""))
            if selected_after_click is not None:
                self._bound_page_id = int(selected_after_click)
                page_id = int(selected_after_click)
            if actual_origin:
                self._expected_origin = actual_origin
            self._pending_target_url = None

            return {
                "success": result["success"],
                "page_id": page_id,
                "uid": str(uid),
                "clicked_text": label,
                "clicked_url": url,
                "actual_url": actual_url,
                "text": result["text"],
                "bound": self._bound_page_id is not None,
            }

        except Exception as exc:
            return self._error(exc)

    def _snapshot(self, page_id, verbose=False, retries=5, delay=0.7):
        """Take a fresh accessibility snapshot, retrying while an SPA is still hydrating.

        Some modern commerce sites briefly expose only the RootWebArea while
        client-side JavaScript is loading. Returning that sparse snapshot too
        early makes semantic actions such as fill() fail even though the page
        becomes interactive a moment later.
        """
        last = None
        for attempt in range(max(1, int(retries))):
            last = self._call(
                "take_snapshot",
                {
                    "pageId": page_id,
                    "verbose": bool(verbose),
                },
            )
            text = str(last.get("text", "") or "")
            # A hydrated accessibility tree normally contains interactive roles
            # or substantially more than the single RootWebArea line.
            hydrated = (
                re.search(r"\b(textbox|combobox|button|link|navigation|main|search|form)\b", text, re.I)
                or text.count("uid=") >= 5
            )
            if hydrated:
                return last
            if attempt < retries - 1:
                time.sleep(float(delay))
        return last or {"success": False, "text": ""}

    def _find_uid_for_fill(self, snapshot, target=None):
        snapshot = str(snapshot or "")
        target = str(target or "").strip().casefold()

        fields = []
        for line in snapshot.splitlines():
            if "uid=" not in line:
                continue
            if not any(token in line for token in ("textbox", "combobox", "textarea", "searchfield", "input")):
                continue
            match = re.search(
                r'uid=([^\s]+).*?(?:textbox|combobox|textarea|searchfield|input)\s+"([^"]*)"',
                line,
            )
            if match:
                fields.append((match.group(1), match.group(2)))

        if not fields:
            return None

        search_names = {
            "search", "بحث", "search box", "مربع البحث", "بحث المنتجات",
            "what are you looking for", "what are you looking for?",
        }

        if target in search_names or not target:
            for uid, name in fields:
                name_cf = name.casefold()
                if any(word in name_cf for word in search_names):
                    return uid
            if len(fields) == 1:
                return fields[0][0]
            for uid, name in fields:
                if not name.strip():
                    return uid

        if target:
            for uid, name in fields:
                if target in name.casefold():
                    return uid

        return fields[0][0] if len(fields) == 1 else None

    def fill(self, page_id=None, uid=None, value="", target=None):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)

            self._call(
                "select_page",
                {
                    "pageId": page_id,
                    "bringToFront": True,
                },
            )

            if self._is_agent_ui_url(self._root_url_from_snapshot(self._page_snapshot(page_id, verbose=False))) and self._pending_target_url and not self._is_agent_ui_url(self._pending_target_url):
                raise RuntimeError("Refusing to fill KAREEM_AGENT UI while an external browser target is pending.")

            if uid is None or str(uid).strip() == "":
                snapshot_result = self._call(
                    "take_snapshot",
                    {
                        "pageId": page_id,
                        "verbose": False,
                    },
                )
                uid = self._find_uid_for_fill(
                    snapshot_result.get("text", ""),
                    target=target or "search",
                )
                if not uid:
                    raise RuntimeError(
                        "Could not resolve an editable field from the current page snapshot."
                    )

            result = self._call(
                "fill",
                {
                    "pageId": page_id,
                    "uid": str(uid),
                    "value": str(value),
                    "includeSnapshot": True,
                },
            )

            return {
                "success": result["success"],
                "page_id": page_id,
                "uid": str(uid),
                "value": str(value),
                "target": target,
                "text": result["text"],
            }

        except Exception as exc:
            return self._error(exc)

    def type_text(
        self,
        text,
        submit_key=None,
    ):
        try:
            page_id = self._resolve_bound_or_current(None)
            self._guard_bound_page(page_id, require_expected=True)
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            arguments = {
                "pageId": page_id,
                "text": str(text),
            }

            if submit_key:
                arguments["submitKey"] = str(
                    submit_key
                )

            result = self._call(
                "type_text",
                arguments,
            )

            return {
                "success": result["success"],
                "text": result["text"],
            }

        except Exception as exc:
            return self._error(exc)

    def _normalize_key(self, key):
        # Chrome DevTools MCP uses DOM/keyboard key names (for example
        # "Enter"), while the planner commonly emits uppercase aliases such
        # as "ENTER". Normalize the common aliases here so the planner can
        # stay human-friendly without leaking invalid key names to MCP.
        raw = str(key or "").strip()
        aliases = {
            "ENTER": "Enter",
            "RETURN": "Enter",
            "ESC": "Escape",
            "ESCAPE": "Escape",
            "TAB": "Tab",
            "SPACE": "Space",
            "BACKSPACE": "Backspace",
            "DELETE": "Delete",
            "DEL": "Delete",
            "HOME": "Home",
            "END": "End",
            "PAGEUP": "PageUp",
            "PAGEDOWN": "PageDown",
            "ARROWUP": "ArrowUp",
            "ARROWDOWN": "ArrowDown",
            "ARROWLEFT": "ArrowLeft",
            "ARROWRIGHT": "ArrowRight",
            "SHIFT": "Shift",
            "CTRL": "Control",
            "CONTROL": "Control",
            "ALT": "Alt",
            "META": "Meta",
            "CTRL+A": "Control+a",
            "CTRL+C": "Control+c",
            "CTRL+V": "Control+v",
            "CTRL+X": "Control+x",
            "CTRL+Z": "Control+z",
            "CTRL+F": "Control+f",
        }
        return aliases.get(raw.upper(), raw)

    def press_key(self, key, page_id=None):
        try:
            # Chrome DevTools MCP requires the runtime pageId even though
            # the user-facing action can omit it. Resolve the current page
            # dynamically just like inspect/fill/click.
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            normalized_key = self._normalize_key(key)
            result = self._call(
                "press_key",
                {
                    "pageId": page_id,
                    "key": normalized_key,
                },
            )

            # Keyboard actions such as Enter may navigate. Rebase the session
            # to the actual page before the next perception pass.
            actual_url = self._root_url_from_snapshot(result.get("text", ""))
            actual_origin = self._origin(actual_url)
            selected_after_key = self._extract_selected_page_id(result.get("text", ""))
            if selected_after_key is not None:
                self._bound_page_id = int(selected_after_key)
                page_id = int(selected_after_key)
            if actual_origin:
                self._expected_origin = actual_origin
            self._pending_target_url = None

            return {
                "success": result["success"],
                "page_id": page_id,
                "key": normalized_key,
                "requested_key": str(key),
                "actual_url": actual_url,
                "text": result["text"],
                "bound": self._bound_page_id is not None,
            }

        except Exception as exc:
            return self._error(exc)

    def navigate(self, page_id=None, direction="back"):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            if direction not in {"back", "forward", "reload"}:
                return {"success": False, "error": "direction must be back, forward, or reload"}
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            result = self._call("navigate_page", {"pageId": page_id, "type": direction})
            actual_url = self._root_url_from_snapshot(result.get("text", ""))
            actual_origin = self._origin(actual_url)
            if actual_origin:
                self._expected_origin = actual_origin
            self._pending_target_url = None
            return {
                "success": result["success"],
                "page_id": page_id,
                "actual_url": actual_url,
                "text": result["text"],
                "bound": self._bound_page_id is not None,
            }
        except Exception as exc:
            return self._error(exc)

    def wait_for(self, text, page_id=None, timeout=10000):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            result = self._call("wait_for", {"pageId": page_id, "text": [str(text)], "timeout": int(timeout)})
            return {"success": result["success"], "page_id": page_id, "text": result["text"]}
        except Exception as exc:
            return self._error(exc)

    def screenshot(self, page_id=None, path=None, full_page=False):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            args = {"pageId": page_id, "fullPage": bool(full_page)}
            if path:
                args["filePath"] = str(path)
            result = self._call("take_screenshot", args)
            return {"success": result["success"], "page_id": page_id, "path": path, "text": result["text"]}
        except Exception as exc:
            return self._error(exc)

    def drag(self, page_id, from_uid, to_uid):
        try:
            page_id = self._resolve_bound_or_current(page_id)
            self._guard_bound_page(page_id, require_expected=True)
            self._call("select_page", {"pageId": page_id, "bringToFront": True})
            result = self._call("drag", {"pageId": page_id, "from_uid": str(from_uid), "to_uid": str(to_uid), "includeSnapshot": True})
            return {"success": result["success"], "page_id": page_id, "text": result["text"]}
        except Exception as exc:
            return self._error(exc)

    def close(self):
        with self._lock:
            if (
                self._process
                and self._process.poll() is None
            ):
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

            self._process = None
            self._initialized = False
            self._tools = {}
            self._stdout_queue = None
            self._stderr_lines = []
            self._reader_threads = []
            self._bound_page_id = None
            self._expected_origin = None
            self._pending_target_url = None

        return {
            "success": True,
            "message": (
                "KAREEM_AGENT detached from Chrome. "
                "Chrome itself was not closed."
            ),
        }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "list_pages": {
                    "description": "List tabs/pages in the current Chrome session.",
                    "parameters": {},
                },
                "current_page": {
                    "description": "List the current Chrome page and selected page ID.",
                    "parameters": {},
                },
                "open_url": {
                    "description": "Open a URL in the current Chrome session.",
                    "parameters": {
                        "url": {
                            "type": "string",
                            "required": True,
                        },
                        "page_id": {
                            "type": "integer",
                            "required": False,
                        },
                        "new_tab": {
                            "type": "boolean",
                            "required": False,
                        },
                    },
                },
                "inspect": {
                    "description": "Inspect the selected/current page. Page ID is optional and resolved dynamically.",
                    "parameters": {
                        "page_id": {
                            "type": "integer",
                            "required": False,
                        },
                        "verbose": {
                            "type": "boolean",
                            "required": False,
                        },
                    },
                },
                "click": {
                    "description": "Click a UI element by UID; when omitted, deterministically resolve a target from the current snapshot (including the first organic Google result on Google search pages).",
                    "parameters": {
                        "page_id": {
                            "type": "integer",
                            "required": False,
                        },
                        "uid": {
                            "type": "string",
                            "required": False,
                        },
                        "selector": {
                            "type": "string",
                            "required": False,
                        },
                        "text": {
                            "type": "string",
                            "required": False,
                        },
                        "first_result": {
                            "type": "boolean",
                            "required": False,
                        },
                        "dbl_click": {
                            "type": "boolean",
                            "required": False,
                        },
                    },
                },
                "fill": {
                    "description": "Fill an editable field by UID or semantic target using the latest accessibility snapshot.",
                    "parameters": {
                        "page_id": {
                            "type": "integer",
                            "required": False,
                        },
                        "uid": {
                            "type": "string",
                            "required": False,
                        },
                        "target": {
                            "type": "string",
                            "required": False,
                            "description": "Semantic field such as search / بحث.",
                        },
                        "value": {
                            "type": "string",
                            "required": True,
                        },
                    },
                },
                "type_text": {
                    "description": "Type into the focused element.",
                    "parameters": {
                        "text": {
                            "type": "string",
                            "required": True,
                        },
                        "submit_key": {
                            "type": "string",
                            "required": False,
                        },
                    },
                },
                "press_key": {
                    "description": "Press a keyboard key on the selected/current page. Page ID is optional and resolved dynamically.",
                    "parameters": {
                        "key": {
                            "type": "string",
                            "required": True,
                        },
                        "page_id": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "navigate": {
                    "description": "Move back/forward or reload the selected page.",
                    "parameters": {"page_id": {"type": "integer", "required": False}, "direction": {"type": "string", "required": True}},
                },
                "wait_for": {
                    "description": "Wait until text appears on the current page.",
                    "parameters": {"text": {"type": "string", "required": True}, "page_id": {"type": "integer", "required": False}, "timeout": {"type": "integer", "required": False}},
                },
                "screenshot": {
                    "description": "Take a screenshot for verification or save it to a file.",
                    "parameters": {"page_id": {"type": "integer", "required": False}, "path": {"type": "string", "required": False}, "full_page": {"type": "boolean", "required": False}},
                },
                "drag": {
                    "description": "Drag one snapshot element onto another.",
                    "parameters": {"page_id": {"type": "integer", "required": True}, "from_uid": {"type": "string", "required": True}, "to_uid": {"type": "string", "required": True}},
                },
                "close": {
                    "description": "Detach without closing Chrome.",
                    "parameters": {},
                },
            },
        }
