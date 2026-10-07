from pathlib import Path
import shutil
import py_compile

ROOT = Path.cwd()

def backup(p):
    if p.exists():
        b = p.with_suffix(p.suffix + ".bak_1.2.0")
        shutil.copy2(p, b)
        print("[BACKUP]", b)

def write(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    backup(p)
    p.write_text(text, encoding="utf-8")
    print("[WRITE]", path)

# ============================================================
# Local Windows UI Automation tool
# ============================================================

write("tools/local_computer.py", r'''
from __future__ import annotations

import os
import subprocess
import time
from typing import Any

class LocalComputerTool:
    """
    Local-first Windows Computer Operator.

    Background mode uses Windows UI Automation where supported.
    Visible mode may fall back to real mouse/keyboard input.
    No external control API is used.
    """

    name = "computer"
    description = (
        "Control local Windows applications using UI Automation first, "
        "with optional visible mouse/keyboard fallback."
    )

    def __init__(self):
        self._desktop = None
        self._pyautogui = None
        self._load()

    def _load(self):
        try:
            from pywinauto import Desktop
            self._desktop = Desktop
        except Exception:
            self._desktop = None

        try:
            import pyautogui
            self._pyautogui = pyautogui
        except Exception:
            self._pyautogui = None

    def _uia_required(self):
        if self._desktop is None:
            return {
                "success": False,
                "error": "pywinauto UI Automation is not installed.",
                "install": "pip install pywinauto",
            }
        return None

    def _windows(self):
        err = self._uia_required()
        if err:
            return err

        try:
            return self._desktop(backend="uia").windows(
                visible_only=True
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def _window(self, title_contains=""):
        windows = self._windows()

        if isinstance(windows, dict):
            return windows, None

        needle = str(title_contains or "").strip().casefold()

        for w in windows:
            try:
                title = (w.window_text() or "").strip()

                if not needle or needle in title.casefold():
                    return None, w
            except Exception:
                continue

        return {
            "success": False,
            "error": f"No window matched: {title_contains}",
        }, None

    @staticmethod
    def _control_info(c, depth=0):
        try:
            rect = c.rectangle()

            return {
                "name": (c.window_text() or "").strip(),
                "control_type": c.element_info.control_type,
                "automation_id": c.element_info.automation_id,
                "class_name": c.element_info.class_name,
                "enabled": bool(c.is_enabled()),
                "visible": bool(c.is_visible()),
                "depth": depth,
                "rectangle": {
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                },
            }
        except Exception as exc:
            return {
                "error": str(exc),
                "depth": depth,
            }

    def inspect(
        self,
        window_title="",
        max_depth=3,
        max_controls=250,
    ):
        error, window = self._window(window_title)

        if error:
            return error

        result = {
            "success": True,
            "window": self._control_info(window),
            "controls": [],
            "mode_capability": {
                "background": True,
                "visible": self._pyautogui is not None,
            },
        }

        try:
            descendants = window.descendants()

            for c in descendants:
                try:
                    info = self._control_info(c)
                    if info.get("depth", 0) <= int(max_depth):
                        result["controls"].append(info)

                    if len(result["controls"]) >= int(max_controls):
                        break
                except Exception:
                    continue

        except Exception as exc:
            result["warning"] = str(exc)

        return result

    def find(
        self,
        name="",
        control_type="",
        automation_id="",
        window_title="",
    ):
        error, window = self._window(window_title)

        if error:
            return error

        wanted_name = str(name or "").casefold()
        wanted_type = str(control_type or "").casefold()
        wanted_id = str(automation_id or "").casefold()

        try:
            candidates = [window] + list(window.descendants())
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        matches = []

        for c in candidates:
            try:
                current_name = (c.window_text() or "").strip()
                current_type = str(c.element_info.control_type or "")
                current_id = str(c.element_info.automation_id or "")

                if wanted_name and wanted_name not in current_name.casefold():
                    continue

                if wanted_type and wanted_type != current_type.casefold():
                    continue

                if wanted_id and wanted_id != current_id.casefold():
                    continue

                matches.append(self._control_info(c))

                if len(matches) >= 50:
                    break

            except Exception:
                continue

        return {
            "success": True,
            "count": len(matches),
            "matches": matches,
        }

    def _resolve(
        self,
        name="",
        control_type="",
        automation_id="",
        window_title="",
    ):
        error, window = self._window(window_title)

        if error:
            return error, None

        wanted_name = str(name or "").casefold()
        wanted_type = str(control_type or "").casefold()
        wanted_id = str(automation_id or "").casefold()

        try:
            candidates = [window] + list(window.descendants())
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }, None

        for c in candidates:
            try:
                current_name = (c.window_text() or "").strip()
                current_type = str(c.element_info.control_type or "")
                current_id = str(c.element_info.automation_id or "")

                if wanted_name and wanted_name not in current_name.casefold():
                    continue

                if wanted_type and wanted_type != current_type.casefold():
                    continue

                if wanted_id and wanted_id != current_id.casefold():
                    continue

                return None, c

            except Exception:
                continue

        return {
            "success": False,
            "error": "No matching UI element found.",
        }, None

    def click(
        self,
        name="",
        control_type="",
        automation_id="",
        window_title="",
        mode="visible",
    ):
        error, control = self._resolve(
            name,
            control_type,
            automation_id,
            window_title,
        )

        if error:
            return error

        mode = str(mode or "visible").lower()

        try:
            if mode == "background":
                # Prefer a non-input UIA invocation.
                try:
                    control.invoke()
                    return {
                        "success": True,
                        "mode": "background",
                        "method": "uia.invoke",
                        "element": self._control_info(control),
                    }
                except Exception:
                    try:
                        control.click()
                        return {
                            "success": True,
                            "mode": "background",
                            "method": "uia.click",
                            "element": self._control_info(control),
                        }
                    except Exception as exc:
                        return {
                            "success": False,
                            "requires_visible": True,
                            "error": str(exc),
                            "reason": "This control does not support background invocation.",
                        }

            control.click_input()

            return {
                "success": True,
                "mode": "visible",
                "method": "mouse.click_input",
                "element": self._control_info(control),
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def set_text(
        self,
        text,
        name="",
        control_type="Edit",
        automation_id="",
        window_title="",
        mode="background",
    ):
        error, control = self._resolve(
            name,
            control_type,
            automation_id,
            window_title,
        )

        if error:
            return error

        try:
            # This is the preferred true-background operation.
            control.set_edit_text(str(text))

            return {
                "success": True,
                "mode": "background",
                "method": "uia.set_edit_text",
                "length": len(str(text)),
                "element": self._control_info(control),
            }

        except Exception as background_exc:
            if str(mode).lower() != "visible":
                return {
                    "success": False,
                    "requires_visible": True,
                    "error": str(background_exc),
                    "reason": "Text control rejected background set_edit_text.",
                }

            try:
                control.click_input()
                if self._pyautogui is None:
                    return {
                        "success": False,
                        "error": "pyautogui is not installed.",
                    }

                self._pyautogui.hotkey("ctrl", "a")
                self._pyautogui.write(str(text), interval=0.01)

                return {
                    "success": True,
                    "mode": "visible",
                    "method": "mouse_keyboard",
                    "length": len(str(text)),
                }

            except Exception as exc:
                return {
                    "success": False,
                    "error": str(exc),
                }

    def select(
        self,
        value,
        name="",
        control_type="ComboBox",
        automation_id="",
        window_title="",
    ):
        error, control = self._resolve(
            name,
            control_type,
            automation_id,
            window_title,
        )

        if error:
            return error

        try:
            control.select(str(value))

            return {
                "success": True,
                "mode": "background",
                "method": "uia.select",
                "value": str(value),
            }

        except Exception as exc:
            return {
                "success": False,
                "requires_visible": True,
                "error": str(exc),
            }

    def close_window(self, title_contains=""):
        error, window = self._window(title_contains)

        if error:
            return error

        try:
            window.close()

            return {
                "success": True,
                "window": title_contains,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def launch(
        self,
        command,
        args=None,
        wait_seconds=1.0,
    ):
        command = str(command or "").strip()

        if not command:
            return {
                "success": False,
                "error": "command is required",
            }

        argv = [command] + [str(x) for x in (args or [])]

        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
            )

            delay = min(max(float(wait_seconds), 0), 5)
            if delay:
                time.sleep(delay)

            return {
                "success": True,
                "pid": proc.pid,
                "command": argv,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "inspect": {
                    "description": "Inspect the local Windows UI tree.",
                    "parameters": {
                        "window_title": {"type": "string", "required": False},
                        "max_depth": {"type": "integer", "required": False},
                        "max_controls": {"type": "integer", "required": False},
                    },
                },
                "find": {
                    "description": "Find a local UI element by name/type/AutomationId.",
                    "parameters": {
                        "name": {"type": "string", "required": False},
                        "control_type": {"type": "string", "required": False},
                        "automation_id": {"type": "string", "required": False},
                        "window_title": {"type": "string", "required": False},
                    },
                },
                "click": {
                    "description": "Click a local Windows UI element.",
                    "parameters": {
                        "name": {"type": "string", "required": False},
                        "control_type": {"type": "string", "required": False},
                        "automation_id": {"type": "string", "required": False},
                        "window_title": {"type": "string", "required": False},
                        "mode": {"type": "string", "required": False},
                    },
                },
                "set_text": {
                    "description": "Set text in a local Windows edit control.",
                    "parameters": {
                        "text": {"type": "string", "required": True},
                        "name": {"type": "string", "required": False},
                        "control_type": {"type": "string", "required": False},
                        "automation_id": {"type": "string", "required": False},
                        "window_title": {"type": "string", "required": False},
                        "mode": {"type": "string", "required": False},
                    },
                },
                "select": {
                    "description": "Select an item in a local Windows combo box.",
                    "parameters": {
                        "value": {"type": "string", "required": True},
                        "name": {"type": "string", "required": False},
                        "control_type": {"type": "string", "required": False},
                        "automation_id": {"type": "string", "required": False},
                        "window_title": {"type": "string", "required": False},
                    },
                },
                "close_window": {
                    "description": "Close a local application window.",
                    "parameters": {
                        "title_contains": {"type": "string", "required": True},
                    },
                },
                "launch": {
                    "description": "Launch a local Windows application.",
                    "parameters": {
                        "command": {"type": "string", "required": True},
                        "args": {"type": "array", "required": False},
                        "wait_seconds": {"type": "number", "required": False},
                    },
                },
            },
        }
''')

# ============================================================
# Register local computer operator
# ============================================================

registry = ROOT / "tools" / "complete_registry.py"
backup(registry)

reg = registry.read_text(encoding="utf-8")

if "tools.local_computer" not in reg:
    reg = reg.replace(
        '        self._register_optional("desktop", "tools.desktop", "DesktopTool")\n',
        '        self._register_optional("desktop", "tools.desktop", "DesktopTool")\n'
        '        self._register_optional("computer", "tools.local_computer", "LocalComputerTool")\n',
        1,
    )

registry.write_text(reg, encoding="utf-8")

# ============================================================
# Dependencies
# ============================================================

req = ROOT / "requirements.txt"
backup(req)

lines = [
    x.strip()
    for x in req.read_text(encoding="utf-8", errors="ignore").splitlines()
    if x.strip()
]

required = [
    "pywinauto",
    "pyautogui",
    "pygetwindow",
    "Pillow",
]

existing = {
    x.split("==")[0].split(">=")[0].split("<=")[0].lower()
    for x in lines
}

for item in required:
    if item.lower() not in existing:
        lines.append(item)

req.write_text("\n".join(lines) + "\n", encoding="utf-8")

# ============================================================
# Validation
# ============================================================

files = [
    ROOT / "tools" / "local_computer.py",
    ROOT / "tools" / "complete_registry.py",
]

for p in files:
    py_compile.compile(str(p), doraise=True)

print()
print("=" * 72)
print("KAREEM_AGENT 1.2 LOCAL COMPUTER OPERATOR READY")
print("=" * 72)
print("No external application-control API was added.")
print("Backups: *.bak_1.2.0")
