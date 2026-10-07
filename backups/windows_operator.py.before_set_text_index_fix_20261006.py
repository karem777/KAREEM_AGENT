
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import psutil
import pyautogui
import pyperclip
from pywinauto import Desktop


@dataclass
class WindowTarget:
    target_id: str
    hwnd: int
    pid: int
    process_name: str
    title: str
    class_name: str
    created_at: float
    confidence: int


@dataclass
class ControlTarget:
    control_id: str
    window_id: str
    name: str
    control_type: str
    automation_id: str
    value: str


class TargetRegistry:
    def __init__(self):
        self.windows: dict[str, WindowTarget] = {}
        self.controls: dict[str, ControlTarget] = {}

    def add_window(self, target: WindowTarget) -> WindowTarget:
        self.windows[target.target_id] = target
        return target

    def add_control(self, target: ControlTarget) -> ControlTarget:
        self.controls[target.control_id] = target
        return target

    def get_window(self, target_id: str) -> WindowTarget | None:
        return self.windows.get(str(target_id))

    def get_control(self, control_id: str) -> ControlTarget | None:
        return self.controls.get(str(control_id))

    def clear_stale(self, operator) -> None:
        stale = []
        for target_id, target in self.windows.items():
            if not operator.window_exists(target.hwnd):
                stale.append(target_id)
        for target_id in stale:
            self.windows.pop(target_id, None)
        stale_controls = [
            cid for cid, c in self.controls.items()
            if c.window_id not in self.windows
        ]
        for cid in stale_controls:
            self.controls.pop(cid, None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "windows": {
                key: asdict(value)
                for key, value in self.windows.items()
            },
            "controls": {
                key: asdict(value)
                for key, value in self.controls.items()
            },
        }


class WindowsOperator:
    name = "computer"
    description = (
        "Professional Windows UI operator using UIA + Win32 window discovery, "
        "target identity binding, verified actions, dialogs, files and visible/background modes."
    )

    def __init__(self, workspace: str | Path | None = None):
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.mode = os.getenv("KAREEM_EXECUTION_MODE", "visible").strip().lower()
        if self.mode not in {"visible", "background"}:
            self.mode = "visible"
        self.targets = TargetRegistry()
        self._last_dialog_snapshot: list[dict[str, Any]] = []

    # ---------- Win32 ----------
    @staticmethod
    def foreground_hwnd() -> int:
        try:
            return int(ctypes.windll.user32.GetForegroundWindow())
        except Exception:
            return 0

    @staticmethod
    def window_exists(hwnd: int) -> bool:
        try:
            return bool(ctypes.windll.user32.IsWindow(int(hwnd)))
        except Exception:
            return False

    @staticmethod
    def window_visible(hwnd: int) -> bool:
        try:
            return bool(ctypes.windll.user32.IsWindowVisible(int(hwnd)))
        except Exception:
            return False

    @staticmethod
    def win_title(hwnd: int) -> str:
        try:
            length = ctypes.windll.user32.GetWindowTextLengthW(int(hwnd))
            buf = ctypes.create_unicode_buffer(max(length + 1, 1))
            ctypes.windll.user32.GetWindowTextW(int(hwnd), buf, len(buf))
            return buf.value.strip()
        except Exception:
            return ""

    @staticmethod
    def win_class(hwnd: int) -> str:
        try:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(int(hwnd), buf, 255)
            return buf.value.strip()
        except Exception:
            return ""

    @staticmethod
    def win_pid(hwnd: int) -> int | None:
        try:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            return int(pid.value)
        except Exception:
            return None

    @staticmethod
    def process_name(pid: int | None) -> str:
        if not pid:
            return ""
        try:
            return psutil.Process(int(pid)).name()
        except Exception:
            return ""

    @staticmethod
    def process_tree(root_pid: int) -> set[int]:
        roots = {int(root_pid)}
        changed = True
        while changed:
            changed = False
            for p in psutil.process_iter(["pid", "ppid"]):
                try:
                    pid = int(p.info["pid"])
                    ppid = int(p.info["ppid"] or 0)
                    if ppid in roots and pid not in roots:
                        roots.add(pid)
                        changed = True
                except Exception:
                    continue
        return roots

    def _top_level_windows(self) -> list[dict[str, Any]]:
        seen: set[int] = set()
        rows: list[dict[str, Any]] = []

        # UIA and Win32 give complementary coverage.
        for backend in ("uia", "win32"):
            try:
                for window in Desktop(backend=backend).windows():
                    try:
                        hwnd = int(window.handle)
                    except Exception:
                        continue
                    if hwnd in seen or not self.window_visible(hwnd):
                        continue
                    seen.add(hwnd)
                    pid = self.win_pid(hwnd)
                    if not pid:
                        continue
                    title = self.win_title(hwnd)
                    if not title:
                        continue
                    rows.append({
                        "hwnd": hwnd,
                        "pid": pid,
                        "process_name": self.process_name(pid),
                        "title": title,
                        "class_name": self.win_class(hwnd),
                    })
            except Exception:
                continue
        return rows

    # ---------- Identity ----------
    @staticmethod
    def _hint_score(row: dict[str, Any], process_hint: str = "", title_hint: str = "") -> int:
        score = 0
        proc = str(row.get("process_name") or "").casefold()
        title = str(row.get("title") or "").casefold()
        process_hint = str(process_hint or "").casefold()
        title_hint = str(title_hint or "").casefold()

        if process_hint:
            stem = Path(process_hint).stem
            if proc == process_hint:
                score += 100
            if stem and stem == Path(proc).stem:
                score += 45

        for token in re.split(r"[|,]", title_hint):
            token = token.strip()
            if token and token in title:
                score += 50

        # Never accept an unrelated browser as a fallback for a non-browser target.
        browsers = ("chrome", "msedge", "edge", "firefox", "brave", "opera")
        if any(x in proc or x in title for x in browsers):
            if not any(x in process_hint for x in browsers):
                score -= 200

        return score

    def _candidate(
        self,
        *,
        pids: set[int] | None = None,
        process_hint: str = "",
        title_hint: str = "",
        exclude_hwnds: set[int] | None = None,
    ) -> dict[str, Any] | None:
        """Universal broker-aware Windows window resolver."""
        rows = self._top_level_windows()
        exclude_hwnds = exclude_hwnds or set()
        candidates = []

        process_hint = str(process_hint or "")
        title_hint = str(title_hint or "")

        title_tokens = [
            t.strip().casefold()
            for t in re.split(r"[|,]", title_hint)
            if t.strip()
        ]
        process_token = (
            Path(process_hint).stem.casefold()
            if process_hint
            else ""
        )

        for row in rows:
            hwnd = int(row.get("hwnd") or 0)
            if not hwnd or hwnd in exclude_hwnds:
                continue

            row_pid = int(row.get("pid") or 0)
            row_proc = Path(
                str(row.get("process_name") or "")
            ).stem.casefold()
            row_title = str(
                row.get("title") or ""
            ).casefold()

            pid_match = bool(
                pids and row_pid in pids
            )
            process_match = bool(
                process_token
                and process_token == row_proc
            )
            title_match = bool(
                title_tokens
                and any(
                    token in row_title
                    for token in title_tokens
                )
            )

            # Windows broker/launcher processes can create the real UI
            # under another PID. A strong title/process identity must
            # therefore override the launcher PID filter.
            if (
                pids
                and row_pid not in pids
                and not (process_match or title_match)
            ):
                continue

            score = self._hint_score(
                row,
                process_hint,
                title_hint,
            )

            if pid_match:
                score += 120
            if process_match:
                score += 80
            if title_match:
                score += 140

            # Never bind a browser for a non-browser target.
            browsers = (
                "chrome",
                "msedge",
                "edge",
                "firefox",
                "brave",
                "opera",
            )

            if any(
                x in row_proc or x in row_title
                for x in browsers
            ):
                if not any(
                    x in process_token
                    for x in browsers
                ):
                    score -= 500

            if (
                pid_match
                or process_match
                or title_match
            ) and score >= 50:
                candidates.append(
                    (score, row)
                )

        if candidates:
            candidates.sort(
                key=lambda x: (
                    -x[0],
                    -len(
                        str(
                            x[1].get("title") or ""
                        )
                    ),
                )
            )
            return candidates[0][1]

        # Foreground fallback for a newly-created window that
        # enumeration temporarily misses.
        try:
            foreground = int(
                self.foreground_hwnd()
            )
        except Exception:
            foreground = 0

        if (
            foreground
            and foreground not in exclude_hwnds
            and self.window_visible(foreground)
        ):
            try:
                fg_pid = self.win_pid(foreground)
                fg_proc = Path(
                    self.process_name(fg_pid)
                ).stem.casefold()
                fg_title = self.win_title(foreground)
                fg_title_low = str(
                    fg_title or ""
                ).casefold()

                process_match = bool(
                    process_token
                    and process_token == fg_proc
                )
                title_match = bool(
                    title_tokens
                    and any(
                        token in fg_title_low
                        for token in title_tokens
                    )
                )
                pid_match = bool(
                    pids
                    and fg_pid in pids
                )

                if (
                    pids
                    and fg_pid not in pids
                    and not (
                        process_match
                        or title_match
                    )
                ):
                    return None

                if (
                    process_match
                    or title_match
                    or pid_match
                ):
                    return {
                        "hwnd": foreground,
                        "pid": fg_pid,
                        "process_name": self.process_name(fg_pid),
                        "title": fg_title,
                        "class_name": self.win_class(foreground),
                    }
            except Exception:
                pass

        return None

    def _register_window(self, row: dict[str, Any], confidence: int) -> WindowTarget:
        target = WindowTarget(
            target_id=f"win_{uuid.uuid4().hex[:12]}",
            hwnd=int(row["hwnd"]),
            pid=int(row["pid"]),
            process_name=str(row["process_name"]),
            title=str(row["title"]),
            class_name=str(row["class_name"]),
            created_at=time.time(),
            confidence=int(confidence),
        )
        return self.targets.add_window(target)

    def _wrapper(self, hwnd: int):
        try:
            return Desktop(backend="uia").window(handle=int(hwnd))
        except Exception:
            return None

    def _resolve_window(
        self,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
    ):
        if target_id:
            target = self.targets.get_window(target_id)
            if target and self.window_exists(target.hwnd):
                current_title = self.win_title(target.hwnd)
                current_pid = self.win_pid(target.hwnd)
                if current_pid and (
                    Path(self.process_name(current_pid)).stem.casefold()
                    == Path(target.process_name).stem.casefold()
                    or current_pid == target.pid
                ):
                    wrapper = self._wrapper(target.hwnd)
                    if wrapper:
                        return target, wrapper

        if hwnd and self.window_exists(int(hwnd)):
            row = next((r for r in self._top_level_windows() if r["hwnd"] == int(hwnd)), None)
            if row:
                wrapper = self._wrapper(int(hwnd))
                if wrapper:
                    target = self._register_window(row, 90)
                    return target, wrapper

        pids = self.process_tree(int(pid)) if pid else None
        row = self._candidate(
            pids=pids,
            process_hint=process_name,
            title_hint=title,
        )
        if not row:
            return None, None
        wrapper = self._wrapper(int(row["hwnd"]))
        if not wrapper:
            return None, None
        target = self._register_window(row, max(70, self._hint_score(row, process_name, title)))
        return target, wrapper

    def _focus_verified(self, target: WindowTarget, wrapper) -> bool:
        if self.mode == "background":
            return True
        try:
            wrapper.set_focus()
        except Exception:
            try:
                wrapper.click_input()
            except Exception:
                return False
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self.foreground_hwnd() == target.hwnd:
                return True
            time.sleep(0.05)
        return False

    # ---------- Launch ----------
    def open_app(
        self,
        command: str,
        args: list[str] | None = None,
        wait_seconds: float = 0.8,
        process_hint: str = "",
        title_hint: str = "",
        require_new_window: bool = False,
    ):
        command = str(command or "").strip()
        if not command:
            return {"success": False, "error": "command is required"}

        argv = [command, *[str(x) for x in (args or [])]]
        before = {r["hwnd"] for r in self._top_level_windows()}
        before_pids = {r["pid"] for r in self._top_level_windows()}
        process_name_hint = process_hint or Path(command).name

        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                proc = subprocess.Popen(
                    ["cmd", "/c", "start", "", command, *(args or [])],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                return {"success": False, "stage": "launch", "error": str(exc)}
        except Exception as exc:
            return {"success": False, "stage": "launch", "error": str(exc)}

        deadline = time.time() + max(4.0, min(float(wait_seconds) + 5.0, 12.0))
        selected = None
        root_pids = self.process_tree(proc.pid)

        while time.time() < deadline:

            # Windows GUI apps can expose the correct new HWND in the
            # foreground before the generic window enumeration is refreshed.
            # Use foreground + strong identity first; PID is only a hint.
            try:
                fg = int(self.foreground_hwnd())
            except Exception:
                fg = 0

            if (
                fg
                and fg not in before
                and self.window_visible(fg)
            ):
                try:
                    fg_pid = self.win_pid(fg)
                    fg_row = {
                        "hwnd": fg,
                        "pid": fg_pid,
                        "process_name": self.process_name(fg_pid),
                        "title": self.win_title(fg),
                        "class_name": self.win_class(fg),
                    }

                    fg_proc = Path(
                        str(fg_row.get("process_name") or "")
                    ).stem.casefold()

                    fg_title = str(
                        fg_row.get("title") or ""
                    ).casefold()

                    process_match = (
                        bool(process_name_hint)
                        and Path(process_name_hint).stem.casefold()
                        == fg_proc
                    )

                    title_match = (
                        bool(title_hint)
                        and any(
                            token.strip().casefold() in fg_title
                            for token in title_hint.split("|")
                            if token.strip()
                        )
                    )

                    if process_match or title_match:
                        selected = fg_row
                        break

                except Exception:
                    pass

            selected = self._candidate(
                pids=root_pids,
                process_hint=process_name_hint,
                title_hint=title_hint,
                exclude_hwnds=before,
            )
            if selected:
                break
            selected = self._candidate(
                process_hint=process_name_hint,
                title_hint=title_hint,
                exclude_hwnds=before,
            )
            if selected:
                break
            time.sleep(0.12)

        reused_existing = False

        if not selected and not require_new_window:
            # Modern Windows applications can launch through a broker process
            # and reuse an already-running top-level window. In that case the
            # launch PID is not the UI PID. Reuse is permitted only when the
            # caller explicitly allows it and the application identity matches.
            selected = self._candidate(
                process_hint=process_name_hint,
                title_hint=title_hint,
                exclude_hwnds=set(),
            )
            if selected:
                reused_existing = True

        # FINAL VERIFIED FOREGROUND FALLBACK
        # The window can be visibly foreground even when enumeration/launch
        # timing has not exposed it to the normal candidate path yet.
        if not selected:
            try:
                fg = int(self.foreground_hwnd())

                if (
                    fg
                    and fg not in before
                    and self.window_visible(fg)
                ):
                    fg_pid = self.win_pid(fg)
                    fg_process = Path(
                        self.process_name(fg_pid)
                    ).stem.casefold()

                    fg_title = self.win_title(fg)
                    fg_title_low = str(
                        fg_title or ""
                    ).casefold()

                    wanted_process = Path(
                        process_name_hint
                    ).stem.casefold()

                    title_tokens = [
                        token.strip().casefold()
                        for token in re.split(
                            r"[|,]",
                            str(title_hint or "")
                        )
                        if token.strip()
                    ]

                    process_match = (
                        bool(wanted_process)
                        and fg_process == wanted_process
                    )

                    title_match = (
                        bool(title_tokens)
                        and any(
                            token in fg_title_low
                            for token in title_tokens
                        )
                    )

                    if process_match or title_match:
                        selected = {
                            "hwnd": fg,
                            "pid": fg_pid,
                            "process_name": self.process_name(fg_pid),
                            "title": fg_title,
                            "class_name": self.win_class(fg),
                        }

            except Exception:
                pass

        if not selected:
            return {
                "success": False,
                "stage": "window_discovery",
                "pid": proc.pid,
                "command": argv,
                "error": "No matching application window could be positively identified; refusing unrelated foreground input.",
                "foreground": self.active_window(),
                "known_before_pids": sorted(before_pids)[:50],
            }

        wrapper = self._wrapper(selected["hwnd"])
        if not wrapper:
            return {
                "success": False,
                "stage": "window_attach",
                "error": "Target window found but UIA attach failed.",
                "target": selected,
            }

        confidence = self._hint_score(selected, process_name_hint, title_hint)
        if reused_existing and Path(process_name_hint).stem.casefold() == Path(str(selected.get("process_name") or "")).stem.casefold():
            confidence += 20
        target = self._register_window(selected, confidence)

        focused = self._focus_verified(target, wrapper)
        if self.mode == "visible" and not focused:
            return {
                "success": False,
                "stage": "focus_verification",
                "error": "Target window could not be foreground-verified.",
                "target": asdict(target),
                "foreground": self.active_window(),
            }

        return {
            "success": True,
            "target": asdict(target),
            "focused_verified": focused,
            "reused_existing_window": reused_existing,
            "launch_pid": int(proc.pid),
        }

    # ---------- Inspection ----------
    @staticmethod
    def _name(control) -> str:
        try:
            return str(control.element_info.name or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _automation_id(control) -> str:
        try:
            return str(control.element_info.automation_id or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _ctype(control) -> str:
        try:
            return str(control.element_info.control_type or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _value(control) -> str:
        for method_name in ("get_value", "window_text"):
            try:
                value = getattr(control, method_name)()
                if value is not None:
                    return str(value)
            except Exception:
                continue
        return ""

    def inspect(
        self,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
        max_controls: int = 120,
    ):
        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}

        controls = []
        try:
            items = wrapper.descendants()
        except Exception:
            items = []

        for item in items:
            name = self._name(item)
            ctype = self._ctype(item)
            automation_id = self._automation_id(item)
            value = self._value(item)
            if name or ctype or automation_id or value:
                control_target = ControlTarget(
                    control_id=f"ctl_{uuid.uuid4().hex[:12]}",
                    window_id=target.target_id,
                    name=name,
                    control_type=ctype,
                    automation_id=automation_id,
                    value=value[:1000],
                )
                self.targets.add_control(control_target)
                controls.append(asdict(control_target))
            if len(controls) >= int(max_controls):
                break

        return {
            "success": True,
            "target": asdict(target),
            "controls": controls,
        }

    def _find_control(self, wrapper, *, control_id="", name="", automation_id="", control_type="", text="", index=0):
        if control_id:
            target = self.targets.get_control(control_id)
            if target:
                try:
                    for c in wrapper.descendants():
                        if (
                            self._name(c) == target.name
                            and self._automation_id(c) == target.automation_id
                            and self._ctype(c) == target.control_type
                        ):
                            return c
                except Exception:
                    pass

        try:
            candidates = wrapper.descendants()
        except Exception:
            candidates = []

        def match(c):
            n = self._name(c).casefold()
            aid = self._automation_id(c).casefold()
            typ = self._ctype(c).casefold()
            val = self._value(c).casefold()
            if name and name.casefold() not in n:
                return False
            if automation_id and automation_id.casefold() != aid:
                return False
            if control_type and control_type.casefold() != typ:
                return False
            if text and text.casefold() not in (n + " " + val):
                return False
            return True

        matches = [c for c in candidates if match(c)]
        return matches[min(int(index), len(matches) - 1)] if matches else None

    # ---------- Actions ----------
    def set_text(
        self,
        text: str,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
        control_id: str = "",
        control_name: str = "",
        automation_id: str = "",
        control_type: str = "",
        replace: bool = False,
        verify: bool = True,
    ):
        expected = str(text)
        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )
        if not target or not wrapper:
            return {"success": False, "stage": "target_lookup", "error": "Target window not found."}

        if not self._focus_verified(target, wrapper):
            return {"success": False, "stage": "target_focus", "error": "Target focus not verified.", "target": asdict(target)}

        control = self._find_control(
            wrapper,
            control_id=control_id,
            name=control_name,
            automation_id=automation_id,
            control_type=control_type,
        )
        if control is None:
            # Prefer Edit/Document without a semantic selector.
            try:
                edits = wrapper.descendants(control_type="Edit") + wrapper.descendants(control_type="Document")
            except Exception:
                edits = []
            control = edits[0] if edits else None

        if control is None:
            return {"success": False, "stage": "control_lookup", "error": "No editable control found.", "target": asdict(target)}

        try:
            control.set_focus()
        except Exception:
            pass

        applied = False
        method = ""

        # Windows 11 Notepad exposes its editor as a UIA Document. In tabbed
        # builds, merely calling set_focus() on a Document can leave keyboard
        # input attached to a stale/inactive tab. In visible mode, click the
        # editor first so the actual active tab owns the keyboard focus.
        if self.mode == "visible" and self._ctype(control).casefold() == "document":
            try:
                control.click_input()
                time.sleep(0.08)
            except Exception:
                pass
            try:
                if replace:
                    pyautogui.hotkey("ctrl", "a")
                pyperclip.copy(expected)
                pyautogui.hotkey("ctrl", "v")
                applied = True
                method = "visible.document_clipboard"
            except Exception as exc:
                return {"success": False, "stage": "text_input", "error": str(exc), "target": asdict(target)}

        if not applied:
            for candidate in ("set_edit_text", "set_value"):
                try:
                    getattr(control, candidate)(expected)
                    applied = True
                    method = f"uia.{candidate}"
                    break
                except Exception:
                    continue

        if not applied and self.mode == "visible":
            try:
                if replace:
                    pyautogui.hotkey("ctrl", "a")
                pyperclip.copy(expected)
                pyautogui.hotkey("ctrl", "v")
                applied = True
                method = "visible.clipboard"
            except Exception as exc:
                return {"success": False, "stage": "text_input", "error": str(exc), "target": asdict(target)}

        if not applied:
            return {"success": False, "stage": "text_input", "error": "No supported text input path for this control.", "target": asdict(target)}

        time.sleep(0.2)

        if not verify:
            return {"success": True, "target": asdict(target), "method": method, "verification": "not_requested"}

        actual = self._value(control)
        matched = actual == expected or (expected and expected in actual)

        # For visible Document input, the strongest proof is reading the text
        # back from the currently focused editor after Ctrl+A/Ctrl+C. This
        # avoids a false positive where a stale UIA Document wrapper reports
        # the requested value while the active Notepad tab remains empty.
        if self.mode == "visible" and (self._ctype(control).casefold() == "document" or method.startswith("visible.")):
            try:
                control.click_input()
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.1)
                copied = str(pyperclip.paste() or "")
                if copied == expected:
                    matched = True
                    actual = copied
                else:
                    matched = False
                    actual = copied
            except Exception:
                pass
        elif not matched and self.mode == "visible":
            try:
                control.set_focus()
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.1)
                copied = str(pyperclip.paste() or "")
                if copied == expected:
                    matched = True
                    actual = copied
            except Exception:
                pass

        if not matched:
            return {
                "success": False,
                "stage": "text_verification",
                "error": "Control did not confirm requested text.",
                "expected": expected,
                "actual": actual,
                "method": method,
                "target": asdict(target),
            }

        return {
            "success": True,
            "target": asdict(target),
            "method": method,
            "text_length": len(expected),
            "verification": "exact_or_contained",
        }

    def click_control(
        self,
        name: str = "",
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
        control_id: str = "",
        automation_id: str = "",
        control_type: str = "",
        index: int = 0,
    ):
        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}

        control = self._find_control(
            wrapper,
            control_id=control_id,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            index=index,
        )
        if control is None:
            return {"success": False, "error": "UI control not found.", "target": asdict(target)}

        if self.mode == "background":
            try:
                control.invoke()
            except Exception as exc:
                return {"success": False, "stage": "invoke", "error": str(exc)}
        else:
            try:
                control.click_input()
            except Exception:
                try:
                    control.invoke()
                except Exception as exc:
                    return {"success": False, "stage": "click", "error": str(exc)}

        return {
            "success": True,
            "target": asdict(target),
            "control": {
                "name": self._name(control),
                "type": self._ctype(control),
                "automation_id": self._automation_id(control),
                "value": self._value(control),
            },
        }

    def active_window(self):
        hwnd = self.foreground_hwnd()
        pid = self.win_pid(hwnd) if hwnd else None
        return {
            "success": bool(hwnd),
            "hwnd": hwnd,
            "pid": pid,
            "title": self.win_title(hwnd) if hwnd else "",
            "process_name": self.process_name(pid),
        }

    def focus_window(
        self,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
    ):
        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )

        if not target or not wrapper:
            return {
                "success": False,
                "stage": "target_lookup",
                "error": "Target window not found.",
            }

        verified = self._focus_verified(
            target,
            wrapper,
        )

        return {
            "success": bool(verified),
            "target": asdict(target),
            "foreground": self.active_window(),
            "focus_verified": bool(verified),
        }

    def type_text(self, text: str):
        if self.mode != "visible":
            return {"success": False, "error": "type_text is visible-only; use set_text for background mode."}
        value = str(text)
        pyperclip.copy(value)
        pyautogui.hotkey("ctrl", "v")
        return {"success": True, "text_length": len(value), "method": "clipboard_paste"}

    def hotkey(self, keys: list[str]):
        if self.mode != "visible":
            return {"success": False, "error": "hotkey is visible-only."}
        values = [str(k).strip().lower() for k in (keys or []) if str(k).strip()]
        if not values:
            return {"success": False, "error": "keys required"}
        pyautogui.hotkey(*values)
        return {"success": True, "keys": values}

    def press(self, key: str, presses: int = 1):
        if self.mode != "visible":
            return {"success": False, "error": "press is visible-only."}
        pyautogui.press(str(key), presses=int(presses))
        return {"success": True, "key": str(key), "presses": int(presses)}

    def click(self, x: int, y: int, clicks: int = 1, button: str = "left"):
        if self.mode != "visible":
            return {"success": False, "error": "coordinate click is visible-only."}
        pyautogui.click(int(x), int(y), clicks=int(clicks), button=str(button))
        return {"success": True, "x": int(x), "y": int(y), "clicks": int(clicks), "button": str(button)}

    def double_click(self, x: int, y: int):
        if self.mode != "visible":
            return {"success": False, "error": "double_click is visible-only."}
        pyautogui.doubleClick(int(x), int(y), interval=0.08)
        return {"success": True, "x": int(x), "y": int(y), "clicks": 2}

    def move(self, x: int, y: int, duration: float = 0.15):
        if self.mode != "visible":
            return {"success": False, "error": "move is visible-only."}
        pyautogui.moveTo(int(x), int(y), duration=max(0.0, float(duration)))
        return {"success": True, "x": int(x), "y": int(y), "duration": float(duration)}

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None):
        if self.mode != "visible":
            return {"success": False, "error": "scroll is visible-only."}
        if x is not None and y is not None:
            pyautogui.moveTo(int(x), int(y), duration=0.05)
        pyautogui.scroll(int(clicks))
        return {
            "success": True,
            "clicks": int(clicks),
            "x": x,
            "y": y,
        }

    def wait(self, seconds: float = 0.5):
        delay = max(0.0, min(float(seconds), 30.0))
        time.sleep(delay)
        return {"success": True, "waited_seconds": delay}

    # ---------- Save As ----------
    def _save_dialog_signature(self, wrapper):
        """Return strong evidence that a UIA subtree is a Save/Confirm dialog."""
        try:
            edits = wrapper.descendants(control_type="Edit")
        except Exception:
            edits = []
        try:
            buttons = wrapper.descendants(control_type="Button")
        except Exception:
            buttons = []

        edit_hay = []
        for e in edits[:30]:
            edit_hay.append(
                (self._name(e) + " " + self._automation_id(e) + " " + self._value(e)).casefold()
            )

        button_hay = []
        for b in buttons[:50]:
            button_hay.append((self._name(b) or self._value(b)).casefold())

        name_hint = any(
            any(x in text for x in ("file name", "filename", "file name:", "Ø§Ø³Ù… Ø§Ù„Ù…Ù„Ù", "Ø§Ù„Ø§Ø³Ù…"))
            for text in edit_hay
        )
        save_hint = any(any(x in text for x in ("save", "Ø­ÙØ¸")) for text in button_hay)
        cancel_hint = any(any(x in text for x in ("cancel", "Ø¥Ù„ØºØ§Ø¡")) for text in button_hay)

        # Windows 11 modern Save UI can expose the filename Edit without a
        # useful Automation Name. The old detector required name_hint and
        # therefore rejected a real Save As surface on some builds. Keep the
        # detector conservative: a modal Save surface must expose Save/Cancel
        # semantics plus at least one Edit control.
        identified = bool((save_hint or cancel_hint) and edits)

        return {
            "identified": identified,
            "name_hint": name_hint,
            "save_hint": save_hint,
            "cancel_hint": cancel_hint,
            "edit_count": len(edits),
            "button_count": len(buttons),
        }

    def _global_uia_windows(self):
        """Return visible top-level windows from both UIA and Win32 backends.

        Windows common file dialogs can be brokered into a different process
        from the application that opened them. pywinauto's Desktop backend is
        explicitly designed for cross-process dialog discovery, so never gate
        Save As discovery on the application's PID tree.
        """
        out = []
        seen: set[int] = set()
        for backend in ("uia", "win32"):
            try:
                for wrapper in Desktop(backend=backend).windows(visible_only=True, enabled_only=False):
                    try:
                        hwnd = int(wrapper.element_info.handle)
                    except Exception:
                        try:
                            hwnd = int(wrapper.handle)
                        except Exception:
                            continue
                    if not hwnd or hwnd in seen:
                        continue
                    seen.add(hwnd)
                    out.append(wrapper)
            except Exception:
                continue
        return out

    def _row_from_wrapper(self, wrapper):
        try:
            hwnd = int(wrapper.element_info.handle)
        except Exception:
            hwnd = 0
        if not hwnd:
            return None
        pid = self.win_pid(hwnd)
        return {
            "hwnd": hwnd,
            "pid": int(pid or 0),
            "title": self.win_title(hwnd),
            "process_name": self.process_name(pid),
            "class_name": self.win_class(hwnd),
        }

    def _find_save_dialog(self, related_pids: set[int], before_hwnds: set[int], timeout: float = 7.0):
        deadline = time.time() + float(timeout)
        last_snapshot = []

        while time.time() < deadline:
            wrappers = self._global_uia_windows()
            candidates = []

            for wrapper in wrappers:
                row = self._row_from_wrapper(wrapper)
                if not row:
                    continue
                if row["hwnd"] in before_hwnds:
                    # A modal dialog can still reuse the same HWND on some WinUI
                    # surfaces, so do not discard it if its title/signature proves
                    # it is a save dialog.
                    same_hwnd_allowed = False
                else:
                    same_hwnd_allowed = True

                title = str(row.get("title") or "").casefold()
                cls = str(row.get("class_name") or "")
                title_like_dialog = any(
                    t in title
                    for t in (
                        "save as", "save", "Ø­ÙØ¸ Ø¨Ø§Ø³Ù…", "Ø­ÙØ¸",
                        "confirm", "replace", "Ø§Ø³ØªØ¨Ø¯Ø§Ù„", "overwrite",
                    )
                )

                signature = self._save_dialog_signature(wrapper)
                if signature["identified"] or cls == "#32770" or title_like_dialog:
                    candidates.append((row, wrapper, signature))

                if len(last_snapshot) < 12:
                    last_snapshot.append({
                        "title": row["title"],
                        "class_name": row["class_name"],
                        "pid": row["pid"],
                        "hwnd": row["hwnd"],
                        "signature": signature,
                    })

            # Prefer a genuinely new dialog, but accept a brokered dialog whose
            # HWND is managed outside the target process. Never require PID match.
            candidates.sort(key=lambda item: (
                item[0]["hwnd"] in before_hwnds,
                not item[2]["identified"],
                not (str(item[0]["class_name"]) == "#32770"),
            ))
            if candidates:
                return candidates[0][0], candidates[0][1]

            time.sleep(0.10)

        if last_snapshot:
            self._last_dialog_snapshot = last_snapshot
        return None, None

    def _find_menu_command_global(self, labels: tuple[str, ...], timeout: float = 1.8):
        wanted = [x.casefold() for x in labels if x]
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            for wrapper in self._global_uia_windows():
                try:
                    items = wrapper.descendants(control_type="MenuItem")
                except Exception:
                    items = []
                for item in items:
                    text = (self._name(item) or self._value(item)).casefold()
                    if any(label in text for label in wanted):
                        return item
            time.sleep(0.08)
        return None

    def _invoke_save_as_command(self, target_wrapper):
        """Use the actual File menu as a fallback when Ctrl+Shift+S doesn't surface UIA."""
        try:
            file_item = self._find_control(
                target_wrapper,
                name="File",
                control_type="MenuItem",
            )
            if file_item is not None:
                try:
                    file_item.click_input()
                except Exception:
                    file_item.invoke()
                time.sleep(0.12)
                command = self._find_menu_command_global(
                    ("save as", "save as...", "save as â€¦", "Ø­ÙØ¸ Ø¨Ø§Ø³Ù…")
                )
                if command is not None:
                    try:
                        command.click_input()
                    except Exception:
                        command.invoke()
                    return True
        except Exception:
            pass
        return False

    def _describe_dialog_controls(self, wrapper):
        out = []
        try:
            hwnd = int(wrapper.element_info.handle)
        except Exception:
            try:
                hwnd = int(wrapper.handle)
            except Exception:
                hwnd = 0
        for backend in ("uia", "win32"):
            try:
                w = Desktop(backend=backend).window(handle=hwnd) if hwnd else wrapper
                items = w.descendants()
                for item in items[:120]:
                    row = {
                        "backend": backend,
                        "class": self._ctype(item),
                        "name": self._name(item),
                        "automation_id": self._automation_id(item),
                        "value": self._value(item)[:200],
                    }
                    if row not in out:
                        out.append(row)
            except Exception:
                continue
        return out[:160]

    def _dialog_edit(self, wrapper):
        """Resolve the actual filename Edit in legacy/modern Windows Save dialogs.

        Windows 11 common Save As dialogs can expose the filename field as:
        #32770 -> DirectUIHWND -> ComboBox(FileNameControlHost) -> Edit
        or as a classic Win32 Edit with control ids such as 1001/1148/41477.
        The wrapper returned by global discovery may come from either UIA or
        Win32, so inspect both backends explicitly and then fall back to raw
        Win32 child enumeration.
        """
        hwnd = 0
        try:
            hwnd = int(wrapper.element_info.handle)
        except Exception:
            try:
                hwnd = int(wrapper.handle)
            except Exception:
                hwnd = 0

        # 1) Re-wrap the dialog explicitly with UIA so we can inspect the
        # FileNameControlHost ComboBox path even if global discovery supplied
        # a Win32 wrapper for the same HWND.
        if hwnd:
            try:
                uia = Desktop(backend="uia").window(handle=hwnd)
                try:
                    hosts = uia.descendants(control_type="ComboBox")
                except Exception:
                    hosts = []
                for host in hosts:
                    aid = self._automation_id(host).casefold()
                    hay = (self._name(host) + " " + aid).casefold()
                    if aid == "filenamecontrolhost" or "file name" in hay or "filename" in hay or "Ø§Ø³Ù… Ø§Ù„Ù…Ù„Ù" in hay:
                        try:
                            nested = host.descendants(control_type="Edit")
                        except Exception:
                            nested = []
                        if nested:
                            return nested[0]
                try:
                    edits = uia.descendants(control_type="Edit")
                except Exception:
                    edits = []
                for e in edits:
                    aid = self._automation_id(e).casefold()
                    hay = (self._name(e) + " " + aid + " " + self._value(e)).casefold()
                    if aid in {"filenamecontrolhost", "1001", "1148", "41477"}:
                        return e
                    if any(x in hay for x in ("file name", "filename", "Ø§Ø³Ù… Ø§Ù„Ù…Ù„Ù")):
                        return e
            except Exception:
                pass

        # 2) The existing wrapper (UIA or Win32), including nested descendants.
        for candidate_wrapper in (wrapper,):
            try:
                edits = candidate_wrapper.descendants(control_type="Edit")
            except Exception:
                edits = []
            for e in edits:
                aid = self._automation_id(e).casefold()
                hay = (self._name(e) + " " + aid + " " + self._value(e)).casefold()
                if aid in {"filenamecontrolhost", "1001", "1148", "41477"}:
                    return e
                if any(x in hay for x in ("file name", "filename", "Ø§Ø³Ù… Ø§Ù„Ù…Ù„Ù")):
                    return e

        # 3) Explicit Win32 backend. This handles #32770 dialogs whose UIA
        # tree does not expose the nested Edit even though Win32 does.
        if hwnd:
            try:
                w32 = Desktop(backend="win32").window(handle=hwnd)
                try:
                    children = w32.descendants(class_name="Edit")
                except Exception:
                    children = []
                preferred_ids = {1001, 1148, 41477}
                for e in children:
                    try:
                        cid = int(e.element_info.control_id or 0)
                    except Exception:
                        cid = 0
                    if cid in preferred_ids:
                        return e
                if children:
                    # On the classic common dialog the filename editor is a
                    # descendant Edit; if no stable id is exposed, choose the
                    # last Edit only after the dialog itself is positively
                    # identified as Save As.
                    return children[-1]
            except Exception:
                pass

        # 4) Raw Win32 fallback: recursively enumerate Edit children.
        if hwnd:
            try:
                user32 = ctypes.windll.user32
                enum_proc_t = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                found = []

                def _walk(parent):
                    child = user32.FindWindowExW(int(parent), 0, None, None)
                    while child:
                        buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(int(child), buf, 255)
                        cls = buf.value
                        if cls.casefold() == "edit":
                            cid = int(user32.GetDlgCtrlID(int(child)) or 0)
                            found.append((int(child), cid))
                        _walk(int(child))
                        child = user32.FindWindowExW(int(parent), int(child), None, None)

                _walk(hwnd)
                preferred = [item for item in found if item[1] in {1001, 1148, 41477}]
                chosen = preferred[0] if preferred else (found[-1] if found else None)
                if chosen:
                    # Wrap the raw HWND so the existing input path can use it.
                    return Desktop(backend="win32").window(handle=int(chosen[0]))
            except Exception:
                pass

        return None

    def _dialog_button(self, wrapper, labels: tuple[str, ...]):
        try:
            buttons = wrapper.descendants(control_type="Button")
        except Exception:
            buttons = []
        wanted = {x.casefold() for x in labels}
        for b in buttons:
            text = (self._name(b) or self._value(b)).casefold()
            aid = self._automation_id(b).casefold()
            if text in wanted:
                return b
            if "save" in wanted and aid in {"1", "savebutton", "save"}:
                return b
        return None

    def save_file(
        self,
        path: str,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
        timeout: float = 8.0,
        overwrite: bool = True,
    ):
        if self.mode != "visible":
            return {"success": False, "stage": "mode", "error": "save_file requires visible mode in this operator."}

        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )
        if not target or not wrapper:
            return {"success": False, "stage": "target_lookup", "error": "Target application not identified."}

        if not self._focus_verified(target, wrapper):
            return {"success": False, "stage": "target_focus", "error": "Target application is not verified as focused.", "target": asdict(target)}

        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        before_hwnds = {r["hwnd"] for r in self._top_level_windows()}
        related = self.process_tree(target.pid)

        # Primary invocation: documented Windows Notepad shortcut for Save As.
        pyautogui.hotkey("ctrl", "shift", "s")
        time.sleep(0.35)

        dialog_row, dialog = self._find_save_dialog(
            related_pids=related,
            before_hwnds=before_hwnds,
            timeout=min(float(timeout), 2.2),
        )

        # Deterministic fallback: use the application's own File -> Save As menu
        # when the shortcut did not expose a dialog to UI Automation.
        if not dialog_row or not dialog:
            self._focus_verified(target, wrapper)
            if self._invoke_save_as_command(wrapper):
                print("SAVE: File -> Save As menu fallback invoked")
                time.sleep(0.35)
                dialog_row, dialog = self._find_save_dialog(
                    related_pids=related,
                    before_hwnds=before_hwnds,
                    timeout=max(1.0, min(float(timeout), 4.0)),
                )

        if not dialog_row or not dialog:
            debug = getattr(self, "_last_dialog_snapshot", [])
            return {
                "success": False,
                "stage": "dialog_detection",
                "error": "Save As was invoked but no Save dialog was exposed through global UI Automation.",
                "target": asdict(target),
                "foreground": self.active_window(),
                "dialog_candidates": debug,
            }

        edit = self._dialog_edit(dialog)
        if edit is None:
            return {
                "success": False,
                "stage": "dialog_control",
                "error": "Save dialog filename control not found.",
                "dialog": dialog_row,
                "dialog_ui_tree": self._describe_dialog_controls(dialog),
            }

        pyperclip.copy(str(destination))
        placed = False

        # Prefer the verified filename Edit when it exposes a meaningful name.
        hay = (self._name(edit) + " " + self._automation_id(edit) + " " + self._value(edit)).casefold()
        meaningful_name = any(x in hay for x in ("file name", "filename", "Ø§Ø³Ù… Ø§Ù„Ù…Ù„Ù"))
        if meaningful_name:
            for method in ("set_edit_text", "set_value"):
                try:
                    edit.set_focus()
                    getattr(edit, method)(str(destination))
                    placed = True
                    break
                except Exception:
                    continue

        # Modern Windows Save As often exposes an anonymous Edit. In that case
        # use the standard Alt+N filename-field navigation only after the
        # modal Save surface has already been positively identified.
        if not placed:
            try:
                pyautogui.hotkey("alt", "n")
                time.sleep(0.08)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "v")
                placed = True
            except Exception:
                placed = False

        if not placed:
            try:
                edit.set_focus()
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "v")
                placed = True
            except Exception as exc:
                return {"success": False, "stage": "filename_input", "error": str(exc)}

        save_button = self._dialog_button(dialog, ("save", "Ø­ÙØ¸"))
        try:
            if save_button:
                try:
                    save_button.click_input()
                except Exception:
                    save_button.invoke()
            else:
                pyautogui.press("enter")
        except Exception as exc:
            return {"success": False, "stage": "save_submit", "error": str(exc)}

        time.sleep(0.7)

        if overwrite and destination.exists():
            deadline = time.time() + 2.5
            while time.time() < deadline:
                confirm_row, confirm = self._find_save_dialog(
                    related_pids=related,
                    before_hwnds=before_hwnds,
                    timeout=0.3,
                )
                if not confirm_row or not confirm:
                    break
                low = confirm_row["title"].casefold()
                if not any(x in low for x in ("replace", "confirm", "Ø§Ø³ØªØ¨Ø¯Ø§Ù„", "ØªØ£ÙƒÙŠØ¯", "overwrite")):
                    break
                button = self._dialog_button(confirm, ("yes", "replace", "Ù†Ø¹Ù…", "Ø§Ø³ØªØ¨Ø¯Ø§Ù„"))
                try:
                    if button:
                        try:
                            button.click_input()
                        except Exception:
                            button.invoke()
                    else:
                        pyautogui.press("enter")
                except Exception:
                    pass
                break

        return {
            "success": destination.is_file(),
            "path": str(destination),
            "target": asdict(target),
            "dialog": dialog_row,
            "method": "verified_dialog",
        }

    def verify_file(self, path: str, expected_text: str | None = None):
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            return {"success": False, "exists": False, "path": str(target), "error": "File does not exist."}
        result = {
            "success": True,
            "exists": True,
            "path": str(target),
            "size": target.stat().st_size,
        }
        if expected_text is not None:
            raw = target.read_bytes()
            try:
                if raw.startswith(b"\xef\xbb\xbf"):
                    actual = raw.decode("utf-8-sig")
                elif raw.startswith(b"\xff\xfe"):
                    actual = raw.decode("utf-16")
                elif raw.startswith(b"\xfe\xff"):
                    actual = raw.decode("utf-16")
                else:
                    actual = raw.decode("utf-8")
            except Exception:
                actual = raw.decode("utf-8", errors="replace")
            expected = str(expected_text)
            result["content_match"] = actual == expected
            result["content_length"] = len(actual)
            result["expected_length"] = len(expected)
            if actual != expected:
                result["success"] = False
                result["actual_preview"] = actual[:1200]
        return result

    def screenshot(self, path: str = ""):
        if not path:
            path = str(self.workspace / "agent_memory" / "screenshots" / f"screen_{int(time.time()*1000)}.png")
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            pyautogui.screenshot().save(str(target))
            return {"success": True, "path": str(target)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def close_window(self, target_id: str = "", hwnd: int | None = None, confirm: bool = False):
        if not confirm:
            return {"success": False, "approval_required": True, "reason": "Closing a window changes UI state. Set confirm=true."}
        target, wrapper = self._resolve_window(target_id=target_id, hwnd=hwnd)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        try:
            wrapper.close()
        except Exception:
            try:
                ctypes.windll.user32.PostMessageW(int(target.hwnd), 0x0010, 0, 0)
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        time.sleep(0.4)
        return {"success": not self.window_exists(target.hwnd), "closed_hwnd": target.hwnd}

    # ---------- Universal UI capabilities ----------
    def _resolve_control_with_meta(
        self,
        wrapper,
        control_id: str = "",
        name: str = "",
        automation_id: str = "",
        control_type: str = "",
        text: str = "",
        index: int = 0,
    ):
        control = self._find_control(
            wrapper,
            control_id=control_id,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            text=text,
            index=index,
        )
        return control

    @staticmethod
    def _pattern_flags(control) -> list[str]:
        patterns = []
        mapping = {
            "invoke": "iface_invoke",
            "toggle": "iface_toggle",
            "selection_item": "iface_selection_item",
            "selection": "iface_selection",
            "value": "iface_value",
            "range_value": "iface_range_value",
            "expand_collapse": "iface_expand_collapse",
            "scroll": "iface_scroll",
            "scroll_item": "iface_scroll_item",
            "grid": "iface_grid",
            "grid_item": "iface_grid_item",
            "text": "iface_text",
            "window": "iface_window",
            "transform": "iface_transform",
            "legacy_accessible": "iface_legacy_iaccessible",
        }
        for label, attr in mapping.items():
            try:
                obj = getattr(control, attr, None)
                if obj is not None:
                    patterns.append(label)
            except Exception:
                continue
        # pywinauto exposes high-level helpers on common UIA wrappers.
        for label, attr in {
            "invoke": "invoke",
            "toggle": "toggle",
            "select": "select",
            "expand": "expand",
            "collapse": "collapse",
            "scroll_into_view": "scroll_into_view",
            "set_value": "set_value",
        }.items():
            try:
                if callable(getattr(control, attr, None)) and label not in patterns:
                    patterns.append(label)
            except Exception:
                pass
        return sorted(set(patterns))

    def inspect_control(
        self,
        target_id: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        title: str = "",
        process_name: str = "",
        control_id: str = "",
        control_name: str = "",
        automation_id: str = "",
        control_type: str = "",
        text: str = "",
        index: int = 0,
    ):
        target, wrapper = self._resolve_window(
            target_id=target_id,
            hwnd=hwnd,
            pid=pid,
            title=title,
            process_name=process_name,
        )
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(
            wrapper,
            control_id=control_id,
            name=control_name,
            automation_id=automation_id,
            control_type=control_type,
            text=text,
            index=index,
        )
        if control is None:
            return {"success": False, "stage": "control_lookup", "error": "Control not found.", "target": asdict(target)}
        meta = {
            "name": self._name(control),
            "control_type": self._ctype(control),
            "automation_id": self._automation_id(control),
            "value": self._value(control)[:2000],
            "patterns": self._pattern_flags(control),
        }
        try:
            meta["enabled"] = bool(control.is_enabled())
        except Exception:
            meta["enabled"] = None
        try:
            meta["visible"] = bool(control.is_visible())
        except Exception:
            meta["visible"] = None
        try:
            meta["selected"] = bool(control.is_selected())
        except Exception:
            meta["selected"] = None
        try:
            meta["toggle_state"] = int(control.get_toggle_state())
        except Exception:
            meta["toggle_state"] = None
        return {"success": True, "target": asdict(target), "control": meta}

    def invoke_control(
        self,
        target_id: str = "",
        control_id: str = "",
        control_name: str = "",
        automation_id: str = "",
        control_type: str = "",
        text: str = "",
        index: int = 0,
    ):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, control_id, control_name, automation_id, control_type, text, index)
        if control is None:
            return {"success": False, "error": "Control not found."}
        self._focus_verified(target, wrapper)
        try:
            inv = getattr(control, "invoke", None)
            if callable(inv):
                inv()
            else:
                control.click_input()
            return {"success": True, "action": "invoke", "control": {"name": self._name(control), "type": self._ctype(control)}}
        except Exception as exc:
            try:
                control.click_input()
                return {"success": True, "action": "click_input", "control": {"name": self._name(control), "type": self._ctype(control)}}
            except Exception as exc2:
                return {"success": False, "error": str(exc2), "primary_error": str(exc)}

    def toggle_control(
        self,
        target_id: str = "",
        control_id: str = "",
        control_name: str = "",
        automation_id: str = "",
        control_type: str = "CheckBox",
        text: str = "",
        index: int = 0,
        desired: bool | None = None,
    ):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, control_id, control_name, automation_id, control_type, text, index)
        if control is None:
            return {"success": False, "error": "Toggle control not found."}
        try:
            before = int(control.get_toggle_state())
        except Exception:
            before = None
        try:
            if desired is not None and before is not None:
                is_on = before == 1
                if bool(desired) != is_on:
                    control.toggle()
            else:
                control.toggle()
            time.sleep(0.08)
            after = None
            try:
                after = int(control.get_toggle_state())
            except Exception:
                pass
            return {"success": True, "before": before, "after": after, "control": {"name": self._name(control), "type": self._ctype(control)}}
        except Exception as exc:
            try:
                control.click_input()
                time.sleep(0.08)
                after = None
                try:
                    after = int(control.get_toggle_state())
                except Exception:
                    pass
                return {"success": True, "method": "click_input", "before": before, "after": after}
            except Exception as exc2:
                return {"success": False, "error": str(exc2), "fallback_error": str(exc)}

    def select_control(
        self,
        target_id: str = "",
        control_id: str = "",
        control_name: str = "",
        automation_id: str = "",
        control_type: str = "",
        text: str = "",
        index: int = 0,
        item: str | int | None = None,
    ):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, control_id, control_name, automation_id, control_type, text, index)
        if control is None:
            return {"success": False, "error": "Selection control not found."}

        desired = item if item is not None else text
        try:
            select_fn = getattr(control, "select", None)
            if callable(select_fn):
                if desired not in (None, ""):
                    select_fn(desired)
                else:
                    select_fn()
            else:
                children = []
                try:
                    children = control.descendants()
                except Exception:
                    children = []
                chosen = None
                if desired not in (None, ""):
                    if isinstance(desired, int):
                        idx = int(desired)
                        chosen = children[idx] if 0 <= idx < len(children) else None
                    else:
                        for child in children:
                            if self._name(child).casefold() == str(desired).casefold() or self._value(child).casefold() == str(desired).casefold():
                                chosen = child
                                break
                else:
                    chosen = control
                if chosen is None:
                    return {"success": False, "error": "Selection item not found."}
                chosen.select()
            time.sleep(0.08)
            return {"success": True, "action": "select", "item": desired, "control": {"name": self._name(control), "type": self._ctype(control)}, "value": self._value(control)}
        except Exception as exc:
            # Visible keyboard fallback for standard combo/list controls only.
            try:
                control.click_input()
                if desired not in (None, ""):
                    pyperclip.copy(str(desired))
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.hotkey("ctrl", "v")
                    pyautogui.press("enter")
                else:
                    pyautogui.press("space")
                return {"success": True, "method": "visible_fallback", "item": desired}
            except Exception as exc2:
                return {"success": False, "error": str(exc2), "fallback_error": str(exc)}

    def expand_control(self, target_id: str = "", control_name: str = "", text: str = "", index: int = 0):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, name=control_name, text=text, index=index)
        if control is None:
            return {"success": False, "error": "Control not found."}
        try:
            control.expand()
            return {"success": True, "action": "expand", "control": {"name": self._name(control), "type": self._ctype(control)}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def collapse_control(self, target_id: str = "", control_name: str = "", text: str = "", index: int = 0):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, name=control_name, text=text, index=index)
        if control is None:
            return {"success": False, "error": "Control not found."}
        try:
            control.collapse()
            return {"success": True, "action": "collapse", "control": {"name": self._name(control), "type": self._ctype(control)}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def scroll_control_into_view(self, target_id: str = "", control_name: str = "", text: str = "", index: int = 0):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, name=control_name, text=text, index=index)
        if control is None:
            return {"success": False, "error": "Control not found."}
        try:
            control.scroll_into_view()
            return {"success": True, "action": "scroll_into_view"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_range_value(self, value: float, target_id: str = "", control_name: str = "", automation_id: str = "", control_type: str = "Slider", index: int = 0):
        target, wrapper = self._resolve_window(target_id=target_id)
        if not target or not wrapper:
            return {"success": False, "error": "Target window not found."}
        control = self._resolve_control_with_meta(wrapper, name=control_name, automation_id=automation_id, control_type=control_type, index=index)
        if control is None:
            return {"success": False, "error": "Range control not found."}
        try:
            control.set_value(float(value))
            return {"success": True, "value": float(value)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_control_state(self, target_id: str = "", control_id: str = "", control_name: str = "", automation_id: str = "", control_type: str = "", text: str = "", index: int = 0):
        return self.inspect_control(
            target_id=target_id,
            control_id=control_id,
            control_name=control_name,
            automation_id=automation_id,
            control_type=control_type,
            text=text,
            index=index,
        )

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "open_app": "Launch an app and bind to its target window.",
                "list_windows": "Enumerate top-level Windows windows.",
                "active_window": "Read foreground HWND/PID/process/title.",
                "focus_window": "Focus a positively identified window.",
                "inspect": "Inspect UIA controls and register target IDs.",
                "set_text": "Set Unicode text into a specific UI control and verify it.",
                "click_control": "Click/invoke a named UI control.",
                "click": "Visible coordinate click.",
                "double_click": "Visible double-click.",
                "move": "Visible mouse move.",
                "scroll": "Visible mouse wheel scroll.",
                "type_text": "Visible Unicode clipboard input without implicit Ctrl+A.",
                "hotkey": "Visible keyboard shortcut.",
                "press": "Visible key press.",
                "wait": "Wait for UI stabilization.",
                "screenshot": "Capture desktop.",
                "save_file": "Verified Save As dialog workflow.",
                "verify_file": "Verify file existence and exact content.",
                "close_window": "Close a specific target window; requires confirm=true.",
                "inspect_control": "Inspect one control and discover supported UI Automation capabilities.",
                "invoke_control": "Invoke a control using the Invoke pattern, with safe click fallback.",
                "toggle_control": "Toggle or set a toggle-capable control such as CheckBox.",
                "select_control": "Select an item/control using SelectionItem or a compatible visible fallback.",
                "expand_control": "Expand an ExpandCollapse-capable control.",
                "collapse_control": "Collapse an ExpandCollapse-capable control.",
                "scroll_control_into_view": "Scroll a control into view using ScrollItem capability.",
                "set_range_value": "Set a RangeValue-capable control such as Slider.",
                "get_control_state": "Read control state and supported UI Automation patterns.",
            },
        }

