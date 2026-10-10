from __future__ import annotations

import os
import subprocess
import time
from typing import Any


class DesktopTool:
    """Windows desktop control with a safe, capability-driven interface.

    The tool prefers pywinauto/pyautogui when installed and falls back to
    standard Windows process launching for opening applications.
    It never changes Registry/services/firewall/drivers; those stay in the
    existing SystemTool approval boundary.
    """

    name = "desktop"

    description = (
        "Control the Windows desktop: inspect/open/focus windows, mouse, keyboard, "
        "scroll, screenshots, and application launching. Use this for native apps "
        "or when browser accessibility control is insufficient."
    )

    def __init__(self):
        self._pyautogui = None
        self._gw = None
        self._psutil = None
        self._load_optional()

    def _load_optional(self):
        try:
            import pyautogui  # type: ignore
            self._pyautogui = pyautogui
        except Exception:
            self._pyautogui = None
        try:
            import pygetwindow as gw  # type: ignore
            self._gw = gw
        except Exception:
            self._gw = None
        try:
            import psutil  # type: ignore
            self._psutil = psutil
        except Exception:
            self._psutil = None

    def _need_gui(self):
        if self._pyautogui is None:
            return {
                "success": False,
                "error": "Desktop GUI backend is not installed.",
                "install": "pip install pyautogui pygetwindow psutil pywinauto",
            }
        return None

    def screen_size(self):
        err = self._need_gui()
        if err:
            return err
        w, h = self._pyautogui.size()
        return {"success": True, "width": int(w), "height": int(h)}

    def screenshot(self, path: str | None = None):
        err = self._need_gui()
        if err:
            return err
        try:
            img = self._pyautogui.screenshot()
            if path:
                path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                img.save(path)
                return {"success": True, "path": path}
            # Avoid trying to serialize the image into the planner context.
            return {"success": True, "size": list(img.size), "image_available": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def click(self, x: int, y: int, clicks: int = 1, interval: float = 0.08, button: str = "left"):
        err = self._need_gui()
        if err:
            return err
        x, y = int(x), int(y)
        width, height = self._pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            return {"success": False, "error": "Coordinates are outside the primary screen.", "screen": [int(width), int(height)]}
        if int(clicks) < 1 or int(clicks) > 3:
            return {"success": False, "error": "clicks must be between 1 and 3."}
        if str(button).lower() not in {"left", "right", "middle"}:
            return {"success": False, "error": "button must be left, right, or middle."}
        self._pyautogui.click(x, y, clicks=int(clicks), interval=max(0.0, min(float(interval), 1.0)), button=str(button).lower())
        return {"success": True, "x": int(x), "y": int(y), "clicks": int(clicks), "button": str(button)}

    def double_click(self, x: int, y: int):
        return self.click(x, y, clicks=2)

    def move(self, x: int, y: int, duration: float = 0.15):
        err = self._need_gui()
        if err:
            return err
        x, y = int(x), int(y)
        width, height = self._pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            return {"success": False, "error": "Coordinates are outside the primary screen.", "screen": [int(width), int(height)]}
        self._pyautogui.moveTo(x, y, duration=max(0.0, min(float(duration), 2.0)))
        return {"success": True, "x": int(x), "y": int(y)}

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None):
        err = self._need_gui()
        if err:
            return err
        if x is not None and y is not None:
            self._pyautogui.moveTo(int(x), int(y), duration=0.05)
        self._pyautogui.scroll(int(clicks))
        return {"success": True, "clicks": int(clicks)}

    def type_text(self, text: str, interval: float = 0.01):
        err = self._need_gui()
        if err:
            return err
        text = str(text)
        if len(text) > 2000:
            return {"success": False, "error": "Text input is limited to 2000 characters per action."}
        self._pyautogui.write(text, interval=max(0.0, min(float(interval), 0.1)))
        return {"success": True, "text_length": len(text)}

    def hotkey(self, *keys: str):
        err = self._need_gui()
        if err:
            return err
        keys = tuple(str(k).strip().lower() for k in keys if str(k).strip())
        allowed = {"ctrl", "control", "alt", "shift", "win", "command", "enter", "tab", "esc", "escape", "space", "backspace", "delete", "home", "end", "pageup", "pagedown", "up", "down", "left", "right", "insert"} | {f"f{i}" for i in range(1, 13)} | {chr(i) for i in range(97, 123)} | {str(i) for i in range(10)}
        if len(keys) > 4 or any(k not in allowed for k in keys):
            return {"success": False, "error": "Hotkey contains unsupported keys or more than four keys."}
        if not keys:
            return {"success": False, "error": "No keys supplied."}
        self._pyautogui.hotkey(*keys)
        return {"success": True, "keys": list(keys)}

    def press(self, key: str, presses: int = 1, interval: float = 0.05):
        err = self._need_gui()
        if err:
            return err
        self._pyautogui.press(str(key), presses=int(presses), interval=float(interval))
        return {"success": True, "key": str(key), "presses": int(presses)}

    def open_app(self, command: str, args: list[str] | None = None, wait_seconds: float = 1.0):
        command = str(command or "").strip()
        if not command:
            return {"success": False, "error": "command is required"}
        if len(command) > 260 or any(ord(ch) < 32 for ch in command):
            return {"success": False, "error": "Invalid application command."}
        if len(args or []) > 20:
            return {"success": False, "error": "Too many application arguments."}
        argv = [command] + [str(x) for x in (args or [])]
        try:
            proc = subprocess.Popen(argv, shell=False)
            if wait_seconds > 0:
                time.sleep(min(float(wait_seconds), 5.0))
            return {"success": True, "pid": proc.pid, "command": argv}
        except FileNotFoundError:
            # Windows can resolve many apps through start.exe.
            try:
                proc = subprocess.Popen(["cmd", "/c", "start", "", command, *(args or [])], shell=False)
                time.sleep(min(float(wait_seconds), 5.0))
                return {"success": True, "pid": proc.pid, "command": argv, "via": "start.exe"}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def list_windows(self):
        if self._gw is not None:
            try:
                rows = []
                for w in self._gw.getAllWindows():
                    title = (w.title or "").strip()
                    if title:
                        rows.append({
                            "title": title,
                            "left": getattr(w, "left", None),
                            "top": getattr(w, "top", None),
                            "width": getattr(w, "width", None),
                            "height": getattr(w, "height", None),
                            "visible": bool(getattr(w, "isVisible", lambda: True)()),
                        })
                return {"success": True, "windows": rows[:200]}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        return {"success": False, "error": "pygetwindow is not installed.", "install": "pip install pygetwindow"}

    def active_window(self):
        if self._gw is None:
            return {"success": False, "error": "pygetwindow is not installed."}
        try:
            w = self._gw.getActiveWindow()
            return {"success": True, "title": (w.title or "").strip() if w else None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def focus_window(self, title: str):
        if self._gw is None:
            return {"success": False, "error": "pygetwindow is not installed.", "install": "pip install pygetwindow"}
        needle = str(title or "").strip().casefold()
        if not needle:
            return {"success": False, "error": "title is required"}
        try:
            candidates = [w for w in self._gw.getAllWindows() if needle in (w.title or "").casefold()]
            if not candidates:
                return {"success": False, "error": f"No window matched: {title}"}
            w = candidates[0]
            try:
                if getattr(w, "isMinimized", lambda: False)():
                    w.restore()
            except Exception:
                pass
            w.activate()
            return {"success": True, "title": (w.title or "").strip()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def wait(self, seconds: float = 1.0):
        delay = max(0.0, min(float(seconds), 30.0))
        time.sleep(delay)
        return {"success": True, "waited_seconds": delay}

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "screen_size": {"description": "Get the primary screen size.", "parameters": {}},
                "screenshot": {"description": "Capture the Windows desktop without returning image bytes to the planner.", "parameters": {"path": {"type": "string", "required": False}}},
                "click": {"description": "Click a screen coordinate.", "parameters": {"x": {"type": "integer", "required": True}, "y": {"type": "integer", "required": True}, "clicks": {"type": "integer", "required": False}, "interval": {"type": "number", "required": False}, "button": {"type": "string", "required": False}}},
                "double_click": {"description": "Double-click a screen coordinate.", "parameters": {"x": {"type": "integer", "required": True}, "y": {"type": "integer", "required": True}}},
                "move": {"description": "Move the mouse to a coordinate.", "parameters": {"x": {"type": "integer", "required": True}, "y": {"type": "integer", "required": True}, "duration": {"type": "number", "required": False}}},
                "scroll": {"description": "Scroll the active window.", "parameters": {"clicks": {"type": "integer", "required": True}, "x": {"type": "integer", "required": False}, "y": {"type": "integer", "required": False}}},
                "type_text": {"description": "Type text into the focused Windows control.", "parameters": {"text": {"type": "string", "required": True}, "interval": {"type": "number", "required": False}}},
                "hotkey": {"description": "Press a keyboard shortcut such as ctrl+s.", "parameters": {"keys": {"type": "array", "required": True}}},
                "press": {"description": "Press a single keyboard key.", "parameters": {"key": {"type": "string", "required": True}, "presses": {"type": "integer", "required": False}, "interval": {"type": "number", "required": False}}},
                "open_app": {"description": "Launch a Windows application or executable without changing system settings.", "parameters": {"command": {"type": "string", "required": True}, "args": {"type": "array", "required": False}, "wait_seconds": {"type": "number", "required": False}}},
                "list_windows": {"description": "List visible desktop windows.", "parameters": {}},
                "active_window": {"description": "Return the active window title.", "parameters": {}},
                "focus_window": {"description": "Focus the first window whose title contains the provided text.", "parameters": {"title": {"type": "string", "required": True}}},
                "wait": {"description": "Pause briefly and let the UI settle.", "parameters": {"seconds": {"type": "number", "required": False}}},
            },
        }
