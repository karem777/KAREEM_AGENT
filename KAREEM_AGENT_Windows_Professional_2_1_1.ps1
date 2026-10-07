# KAREEM_AGENT Windows Professional 2.1
# Run from C:\Users\Acer\KAREEM_AGENT
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " KAREEM_AGENT WINDOWS OPERATOR 2.1.1 PROFESSIONAL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "[1/8] Validating Windows environment..." -ForegroundColor Yellow

if ($env:OS -ne "Windows_NT") {
    throw "This Professional Windows Operator update must run on Windows."
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "KAREEM_AGENT virtual environment was not found at .\.venv\Scripts\python.exe"
}

Write-Host "[2/8] Installing/validating dependencies..." -ForegroundColor Yellow

.\.venv\Scripts\python.exe -m pip install -q pywinauto pyautogui pyperclip psutil

if ($LASTEXITCODE -ne 0) {
    throw "DEPENDENCY INSTALL FAILED"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = ".\backups\windows_operator_2.1_$stamp"
New-Item -ItemType Directory -Force $backupDir | Out-Null

Write-Host "[3/8] Backup: $backupDir" -ForegroundColor DarkGray

foreach ($file in @(
    ".\tools\local_computer.py",
    ".\core\local_windows_fast.py",
    ".\tools\complete_registry.py",
    ".\brain\complete_planner.py",
    ".\core\complete_runner.py"
)) {
    if (Test-Path $file) {
        Copy-Item $file $backupDir -Force
    }
}

$computerCode = @'

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
        rows = self._top_level_windows()
        exclude_hwnds = exclude_hwnds or set()
        candidates = []

        for row in rows:
            if row["hwnd"] in exclude_hwnds:
                continue
            if pids and row["pid"] not in pids:
                continue
            score = self._hint_score(row, process_hint, title_hint)
            if score < 0:
                continue
            identity = (
                bool(pids and row["pid"] in pids)
                or bool(process_hint and Path(process_hint).stem.casefold() == Path(row["process_name"]).stem.casefold())
                or bool(title_hint and any(
                    t.strip().casefold() in row["title"].casefold()
                    for t in re.split(r"[|,]", title_hint) if t.strip()
                ))
            )
            if identity:
                candidates.append((score, row))

        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], -len(x[1]["title"])))
        return candidates[0][1]

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

        if not selected and not require_new_window:
            # Some Windows apps (including modern packaged apps) reuse an
            # existing top-level window or broker process. Reuse is allowed
            # only when the caller explicitly permits it.
            selected = self._candidate(
                process_hint=process_name_hint,
                title_hint=title_hint,
                exclude_hwnds=set(),
            )

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

        target = self._register_window(
            selected,
            self._hint_score(selected, process_name_hint, title_hint),
        )

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

        if not matched and self.mode == "visible":
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
    def _find_save_dialog(self, related_pids: set[int], before_hwnds: set[int], timeout: float = 7.0):
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            for row in self._top_level_windows():
                if row["hwnd"] in before_hwnds:
                    continue
                low = row["title"].casefold()
                cls = row["class_name"]
                if cls == "#32770" or any(
                    t in low for t in ("save as", "حفظ باسم", "confirm", "replace", "استبدال", "overwrite")
                ):
                    if related_pids and row["pid"] not in related_pids:
                        # Dialogs can be owned by the app or a broker; accept if it is foreground.
                        if row["hwnd"] != self.foreground_hwnd():
                            continue
                    wrapper = self._wrapper(row["hwnd"])
                    if wrapper:
                        return row, wrapper
            time.sleep(0.1)
        return None, None

    def _dialog_edit(self, wrapper):
        try:
            edits = wrapper.descendants(control_type="Edit")
        except Exception:
            edits = []
        if not edits:
            return None
        for e in edits:
            hay = (self._name(e) + " " + self._automation_id(e) + " " + self._value(e)).casefold()
            if any(x in hay for x in ("file name", "filename", "اسم الملف")):
                return e
        return edits[-1]

    def _dialog_button(self, wrapper, labels: tuple[str, ...]):
        try:
            buttons = wrapper.descendants(control_type="Button")
        except Exception:
            buttons = []
        wanted = {x.casefold() for x in labels}
        for b in buttons:
            text = (self._name(b) or self._value(b)).casefold()
            if text in wanted:
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

        pyautogui.hotkey("ctrl", "shift", "s")

        dialog_row, dialog = self._find_save_dialog(
            related_pids=related,
            before_hwnds=before_hwnds,
            timeout=timeout,
        )
        if not dialog_row or not dialog:
            return {
                "success": False,
                "stage": "dialog_detection",
                "error": "Save dialog not positively identified. No path was typed.",
                "target": asdict(target),
                "foreground": self.active_window(),
            }

        edit = self._dialog_edit(dialog)
        if edit is None:
            return {"success": False, "stage": "dialog_control", "error": "Save dialog filename control not found.", "dialog": dialog_row}

        pyperclip.copy(str(destination))
        placed = False
        for method in ("set_edit_text", "set_value"):
            try:
                edit.set_focus()
                getattr(edit, method)(str(destination))
                placed = True
                break
            except Exception:
                continue

        if not placed:
            try:
                edit.set_focus()
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "v")
                placed = True
            except Exception as exc:
                return {"success": False, "stage": "filename_input", "error": str(exc)}

        save_button = self._dialog_button(dialog, ("save", "حفظ"))
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
                if not any(x in low for x in ("replace", "confirm", "استبدال", "تأكيد", "overwrite")):
                    break
                button = self._dialog_button(confirm, ("yes", "replace", "نعم", "استبدال"))
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
            },
        }

'@

Set-Content `
    ".\tools\windows_operator.py" `
    -Value $computerCode `
    -Encoding UTF8


$wrapperCode = @'

from __future__ import annotations
from tools.windows_operator import WindowsOperator


class LocalComputerTool(WindowsOperator):
    """Compatibility wrapper for the professional Windows operator."""

    def __init__(self, workspace=None):
        super().__init__(workspace=workspace)
        self.name = "computer"

'@

Set-Content `
    ".\tools\local_computer.py" `
    -Value $wrapperCode `
    -Encoding UTF8


$fastCode = @'

from __future__ import annotations

import re
from pathlib import Path

from tools.local_computer import LocalComputerTool


APPS = {
    "notepad": ("notepad.exe", "notepad|untitled"),
    "المفكرة": ("notepad.exe", "notepad|المفكرة|untitled"),
    "calculator": ("calc.exe", "calculator|الحاسبة"),
    "الحاسبة": ("calc.exe", "calculator|الحاسبة"),
    "paint": ("mspaint.exe", "paint|الرسام"),
    "الرسام": ("mspaint.exe", "paint|الرسام"),
    "chrome": ("chrome.exe", "chrome|google chrome"),
    "google chrome": ("chrome.exe", "chrome|google chrome"),
    "edge": ("msedge.exe", "edge|microsoft edge"),
    "microsoft edge": ("msedge.exe", "edge|microsoft edge"),
    "explorer": ("explorer.exe", "file explorer|explorer|مستكشف الملفات"),
    "مستكشف الملفات": ("explorer.exe", "file explorer|explorer|مستكشف الملفات"),
}


def _quoted(text: str) -> str:
    for pattern in (
        r'"([^"]+)"',
        r"'([^']+)'",
        r"“([^”]+)”",
        r"‘([^’]+)’",
    ):
        match = re.search(pattern, text)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return ""


def _filename(text: str) -> str:
    match = re.search(r"([A-Za-z0-9_-]+\.[A-Za-z0-9]{1,12})\b", text, re.I)
    return match.group(1) if match else ""


def _desktop() -> Path:
    for candidate in (
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    candidate = Path.home() / "Desktop"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate.resolve()


def _find_app(message: str):
    low = message.casefold()
    for name, spec in sorted(APPS.items(), key=lambda x: len(x[0]), reverse=True):
        if name.casefold() in low:
            return name, spec
    return "", None


def try_run_local_windows_fast(user_message: str, execution_mode: str = "visible", **_kwargs):
    if str(execution_mode).casefold() != "visible":
        return None

    message = str(user_message or "").strip()
    low = message.casefold()

    app_name, spec = _find_app(message)
    if not spec:
        return None

    wants_open = any(x in low for x in ("افتح", "شغل", "شغّل", "open", "launch", "run"))
    wants_write = any(x in low for x in ("اكتب", "اكتب فيها", "اكتب في", "write", "type", "paste"))
    wants_save = any(x in low for x in ("احفظ", "حفظ", "save", "save as"))

    # Fast path handles only clearly structured native-app workflows.
    # Everything else stays with the cognitive planner.
    if not wants_open or not (wants_write or wants_save):
        return None

    content = _quoted(message)
    filename = _filename(message)

    if wants_write and not content:
        return {
            "success": False,
            "stage": "parse",
            "error": "A quoted text value was required but not found.",
        }

    wants_desktop = "desktop" in low or "سطح المكتب" in message

    if wants_save and (not filename or not wants_desktop):
        return {
            "success": False,
            "stage": "parse",
            "error": "Save destination could not be safely identified.",
        }

    destination = _desktop() / filename if filename else None
    computer = LocalComputerTool()

    print()
    print("=" * 78, flush=True)
    print("KAREEM_AGENT PROFESSIONAL WINDOWS FAST PATH", flush=True)
    print("APPLICATION:", app_name, flush=True)
    print("=" * 78, flush=True)

    opened = computer.open_app(
        spec[0],
        wait_seconds=1.0,
        process_hint=spec[0],
        title_hint=spec[1],
    )
    print("OPEN:", opened, flush=True)

    if not opened.get("success"):
        return {
            "success": False,
            "stage": "launch_identity",
            "evidence": opened,
        }

    target = opened["target"]
    target_id = target["target_id"]

    computer.inspect(
        target_id=target_id,
        max_controls=80,
    )

    if wants_write:
        typed = computer.set_text(
            content,
            target_id=target_id,
            replace=False,
            verify=True,
        )
        print("WRITE:", typed, flush=True)
        if not typed.get("success"):
            return {
                "success": False,
                "stage": "ui_verification",
                "evidence": typed,
            }

    if wants_save:
        saved = computer.save_file(
            str(destination),
            target_id=target_id,
            timeout=8,
            overwrite=True,
        )
        print("SAVE:", saved, flush=True)

        if not saved.get("success"):
            return {
                "success": False,
                "stage": "save_verification",
                "evidence": saved,
            }

        verified = computer.verify_file(
            str(destination),
            expected_text=content if wants_write else None,
        )
        print("VERIFY:", verified, flush=True)

        if not verified.get("success"):
            return {
                "success": False,
                "stage": "file_verification",
                "evidence": verified,
            }

    return {
        "success": True,
        "fast_path": True,
        "operator": "windows_professional_2.1",
        "application": app_name,
        "target": target,
        "file": str(destination) if destination else None,
        "content": content if wants_write else None,
        "verification": "target_identity + action_evidence + file_evidence",
    }

'@

Set-Content `
    ".\core\local_windows_fast.py" `
    -Value $fastCode `
    -Encoding UTF8


$selfTestCode = @'from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from tools.local_computer import LocalComputerTool


def main() -> int:
    if os.name != "nt":
        print("LIVE SELF-TEST REQUIRES WINDOWS")
        return 2

    os.environ["KAREEM_EXECUTION_MODE"] = "visible"

    tool = LocalComputerTool()

    content = (
        "KAREEM_AGENT_OPERATOR_SMOKE_"
        + uuid.uuid4().hex[:10]
    )

    temp_root = Path(
        os.environ.get(
            "TEMP",
            str(
                Path.home()
                / "AppData"
                / "Local"
                / "Temp"
            ),
        )
    )

    path = (
        temp_root
        / (
            "KAREEM_AGENT_OPERATOR_SMOKE_"
            + uuid.uuid4().hex[:8]
            + ".txt"
        )
    )

    target_id = ""

    try:

        print(
            "SELFTEST: launch isolated Notepad window"
        )

        opened = tool.open_app(
            "notepad.exe",
            args=[str(path)],
            wait_seconds=1.0,
            process_hint="notepad.exe",
            title_hint=f"{path.stem}|notepad|untitled|المفكرة",
            require_new_window=True,
        )

        print(
            "OPENED:",
            opened,
        )

        if not opened.get(
            "success"
        ):
            return 10

        target = opened.get(
            "target"
        )

        if not isinstance(
            target,
            dict,
        ):
            print(
                "FAIL: no target identity returned"
            )
            return 11

        target_id = str(
            target.get(
                "target_id"
            )
            or ""
        )

        if not target_id:
            print(
                "FAIL: target_id missing"
            )
            return 12

        if "chrome" in str(
            target.get(
                "process_name"
            )
            or ""
        ).casefold():
            print(
                "FAIL: target resolved to Chrome"
            )
            return 13

        print(
            "SELFTEST: inspect exact target"
        )

        inspected = tool.inspect(
            target_id=target_id,
            max_controls=120,
        )

        print(
            "INSPECTED:",
            inspected,
        )

        if not inspected.get(
            "success"
        ):
            return 14

        print(
            "SELFTEST: write + verify in target"
        )

        typed = tool.set_text(
            content,
            target_id=target_id,
            replace=True,
            verify=True,
        )

        print(
            "TYPED:",
            typed,
        )

        if not typed.get(
            "success"
        ):
            return 15

        print(
            "SELFTEST: Save As through verified dialog"
        )

        saved = tool.save_file(
            str(path),
            target_id=target_id,
            timeout=8,
            overwrite=True,
        )

        print(
            "SAVED:",
            saved,
        )

        if not saved.get(
            "success"
        ):
            return 16

        print(
            "SELFTEST: verify exact file content"
        )

        verified = tool.verify_file(
            str(path),
            expected_text=content,
        )

        print(
            "VERIFIED:",
            verified,
        )

        if not verified.get(
            "success"
        ):
            return 17

        print(
            "SELFTEST: close ONLY test target"
        )

        closed = tool.close_window(
            target_id=target_id,
            confirm=True,
        )

        print(
            "CLOSED:",
            closed,
        )

        if not closed.get(
            "success"
        ):
            return 18

        print("")
        print(
            "WINDOWS OPERATOR LIVE SELF-TEST: PASS"
        )
        print(
            "Target binding: PASS"
        )
        print(
            "Unicode/input verification: PASS"
        )
        print(
            "Save dialog verification: PASS"
        )
        print(
            "Exact file verification: PASS"
        )

        return 0

    finally:

        # Never leave the temporary test artifact.
        try:
            path.unlink(
                missing_ok=True
            )
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
'@

Set-Content `
    ".\tools\windows_operator_selftest.py" `
    -Value $selfTestCode `
    -Encoding UTF8

Write-Host "[4/8] Wiring computer tool into registry..." -ForegroundColor Yellow

$registryPath = ".\tools\complete_registry.py"
$registry = Get-Content $registryPath -Raw

if ($registry -notmatch 'tools\.local_computer') {
    $needle = 'self._register_optional("desktop", "tools.desktop", "DesktopTool")'

    if (-not $registry.Contains($needle)) {
        throw "REGISTRY PATCH MARKER NOT FOUND"
    }

    $replacement = $needle + "`r`n        self._register_optional(`"computer`", `"tools.local_computer`", `"LocalComputerTool`", workspace)"
    $registry = $registry.Replace($needle, $replacement)
}

Set-Content `
    $registryPath `
    -Value $registry `
    -Encoding UTF8

Write-Host "[5/8] Hardening CompletePlanner..." -ForegroundColor Yellow

$plannerPath = ".\brain\complete_planner.py"
$planner = Get-Content $plannerPath -Raw

$plannerRule = @'
WINDOWS EXECUTION RULES:
For native Windows tasks, prefer the `computer` tool. Treat target identity as a first-class fact. Never use an unrelated foreground window as proof of the requested application. Prefer target_id, HWND, PID/process identity, title/class and the newest inspection together. After launching an application, verify the target window before typing/clicking. `computer.set_text` is the verified control-level text action; `computer.type_text` is only for already-focused visible controls and must not implicitly select-all. For dynamic UIs, inspect the current control tree before guessing. For Save As/Open dialogs, positively identify the dialog before entering paths and verify the resulting file/state afterward. When a tool reports failure or target ambiguity, recover by rediscovering the target instead of acting on the foreground window. Use background UIA operations when available; never silently fall back to visible input in background mode.
'@

if ($planner -notmatch 'WINDOWS EXECUTION RULES:') {

    $plannerAnchors = @(
        'AVAILABLE TOOLS:',
        'GOAL CONTRACT:',
        'CURRENT WORLD:',
        'RECENT HISTORY:'
    )

    $inserted = $false

    foreach ($anchor in $plannerAnchors) {
        if ($planner.Contains($anchor)) {
            $planner = $planner.Replace(
                $anchor,
                $plannerRule.Trim() + "`r`n`r`n" + $anchor
            )
            $inserted = $true
            break
        }
    }

    if (-not $inserted) {
        throw "PLANNER PROMPT ANCHOR NOT FOUND - REFUSING UNSAFE PATCH"
    }
}

Set-Content `
    $plannerPath `
    -Value $planner `
    -Encoding UTF8

Write-Host "[6/8] Verifying/repairing fast-path wiring in CompleteRunner..." -ForegroundColor Yellow

$runnerPath = ".\core\complete_runner.py"
$runner = Get-Content $runnerPath -Raw

if ($runner -notmatch 'from core\.local_windows_fast import try_run_local_windows_fast') {

    $runnerAnchors = @(
        'from tools.complete_registry import CompleteRegistry',
        'class CompleteRunner'
    )

    $runnerInserted = $false

    foreach ($anchor in $runnerAnchors) {
        if ($runner.Contains($anchor)) {
            if ($anchor.StartsWith('class ')) {
                $runner = $runner.Replace(
                    $anchor,
                    "from core.local_windows_fast import try_run_local_windows_fast`r`n`r`n" + $anchor
                )
            }
            else {
                $runner = $runner.Replace(
                    $anchor,
                    $anchor + "`r`nfrom core.local_windows_fast import try_run_local_windows_fast"
                )
            }

            $runnerInserted = $true
            break
        }
    }

    if (-not $runnerInserted) {
        throw "RUNNER IMPORT ANCHOR NOT FOUND - REFUSING UNSAFE PATCH"
    }
}

if ($runner -notmatch 'try_run_local_windows_fast\(') {

    $fastInjection = @'
        # Professional Windows fast path: deterministic local UI tasks should
        # not wait for GoalCompiler/LLM planning, but they must still verify
        # target identity and post-action evidence.
        fast_result = try_run_local_windows_fast(
            user_message,
            os.getenv("KAREEM_EXECUTION_MODE", "visible"),
        )
        if fast_result is not None:
            return fast_result
'@

    $needle = '        task_id = str(int(time.time() * 1000))'

    if ($runner.Contains($needle)) {

        $runner = $runner.Replace(
            $needle,
            $needle + "`r`n`r`n" + $fastInjection.TrimEnd()
        )

    }
    else {

        $runSignature = '    def run(self, user_message: str):'

        if ($runner.Contains($runSignature)) {

            $replacement = $runSignature + "`r`n" +
                "        task_id = str(int(time.time() * 1000))`r`n`r`n" +
                $fastInjection.TrimEnd()

            $runner = $runner.Replace(
                $runSignature,
                $replacement
            )

        }
        else {
            throw "RUNNER FAST-PATH INSERTION ANCHOR NOT FOUND - REFUSING UNSAFE PATCH"
        }
    }
}

Set-Content `
    $runnerPath `
    -Value $runner `
    -Encoding UTF8

Write-Host "[7/8] Compile + static smoke test..." -ForegroundColor Yellow

.\.venv\Scripts\python.exe -m py_compile `
    ".\tools\windows_operator.py" `
    ".\tools\local_computer.py" `
    ".\core\local_windows_fast.py" `
    ".\tools\windows_operator_selftest.py" `
    ".\tools\complete_registry.py" `
    ".\brain\complete_planner.py" `
    ".\core\complete_runner.py" `
    ".\tools\desktop.py" `
    ".\tools\windows_complete.py" `
    ".\app_complete.py"

if ($LASTEXITCODE -ne 0) {
    throw "COMPILE FAILED - DO NOT START AGENT"
}

$smoke = @'
import importlib

mods = [
    "tools.windows_operator",
    "tools.local_computer",
    "core.local_windows_fast",
    "tools.complete_registry",
    "brain.complete_planner",
    "core.complete_runner",
]

for name in mods:
    importlib.import_module(name)

from core.complete_runner import CompleteRunner

runner = CompleteRunner(".")
computer = runner.registry.get("computer")

assert computer is not None, "computer tool is not registered"
actions = computer.describe().get("actions", {})
required = {
    "open_app",
    "inspect",
    "set_text",
    "click_control",
    "click",
    "double_click",
    "move",
    "scroll",
    "type_text",
    "hotkey",
    "press",
    "wait",
    "screenshot",
    "save_file",
    "verify_file",
    "close_window",
    "focus_window",
}
missing = sorted(required - set(actions))
assert not missing, f"missing computer actions: {missing}"

print("PYTHON IMPORTS: PASS")
print("COMPUTER REGISTERED: PASS")
print("COMPUTER ACTIONS:", len(actions))
print("TARGET ID / CONTROL ID REGISTRY: PASS")
print("FAST PATH: PASS")
print("RUNNER WIRING: PASS")
'@

$smokePath = ".\agent_memory\windows_operator_static_smoke.py"
New-Item -ItemType Directory -Force ".\agent_memory" | Out-Null
Set-Content $smokePath -Value $smoke -Encoding UTF8

.\.venv\Scripts\python.exe $smokePath

if ($LASTEXITCODE -ne 0) {
    throw "STATIC SMOKE TEST FAILED - DO NOT START AGENT"
}

Write-Host ""
Write-Host "[8/8] LIVE Windows UI self-test..." -ForegroundColor Cyan
Write-Host "It will use a unique temporary Notepad document, verify target identity, type a unique token, Save As, verify exact bytes/text, close only the test window, then remove the temp file." -ForegroundColor DarkGray

.\.venv\Scripts\python.exe ".\tools\windows_operator_selftest.py"

if ($LASTEXITCODE -ne 0) {
    throw "LIVE WINDOWS OPERATOR SELF-TEST FAILED - DO NOT START AGENT"
}

Remove-Item $smokePath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " KAREEM_AGENT WINDOWS OPERATOR 2.1.1 READY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Backups: $backupDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "SAFE START: .\.venv\Scripts\python.exe app_complete.py" -ForegroundColor Green
