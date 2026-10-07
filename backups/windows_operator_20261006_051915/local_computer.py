from __future__ import annotations

import re
import subprocess
import time


class LocalComputerTool:
    name = "computer"
    description = "Control the local Windows desktop and applications using UI Automation with visible mouse/keyboard fallback."

    def __init__(self, workspace=None):
        self.workspace = workspace

    @staticmethod
    def _desktop():
        from pywinauto import Desktop
        return Desktop(backend="uia")

    @staticmethod
    def _pyautogui():
        import pyautogui
        return pyautogui

    @staticmethod
    def _mode(mode):
        mode = str(mode or "visible").strip().lower()
        return "background" if mode == "background" else "visible"

    @staticmethod
    def _title_matches(title, title_re):
        if not title_re:
            return True
        try:
            return bool(re.search(str(title_re), str(title or ""), re.I))
        except re.error:
            return str(title_re).lower() in str(title or "").lower()

    def _window(self, title_re="", title=""):
        desktop = self._desktop()

        try:
            candidates = desktop.windows()
        except Exception:
            candidates = []

        if title:
            for w in candidates:
                try:
                    if w.window_text().strip().lower() == str(title).strip().lower():
                        return w
                except Exception:
                    pass

        for w in candidates:
            try:
                if self._title_matches(w.window_text(), title_re):
                    return w
            except Exception:
                pass

        if not title and not title_re:
            try:
                return desktop.active()
            except Exception:
                pass

        return None

    def _resolve_control(
        self,
        title_re="",
        window_title="",
        name="",
        control_type="",
        auto_id="",
        class_name="",
    ):
        window = self._window(title_re=title_re, title=window_title)

        if window is None:
            try:
                window = self._desktop().active()
            except Exception:
                return None, None

        try:
            kwargs = {}
            if name:
                kwargs["title"] = name
            if control_type:
                kwargs["control_type"] = control_type
            if auto_id:
                kwargs["auto_id"] = auto_id
            if class_name:
                kwargs["class_name"] = class_name

            if kwargs:
                return window, window.child_window(**kwargs)
        except Exception:
            pass

        try:
            controls = window.descendants()
        except Exception:
            controls = []

        for c in controls:
            try:
                info = c.element_info
                ct = str(getattr(info, "control_type", "") or "")
                aid = str(getattr(info, "automation_id", "") or "")
                cls = str(getattr(info, "class_name", "") or "")

                if name and c.window_text() != name:
                    continue
                if control_type and ct.lower() != control_type.lower():
                    continue
                if auto_id and aid != auto_id:
                    continue
                if class_name and cls != class_name:
                    continue

                return window, c
            except Exception:
                pass

        return window, None

    def inspect(self, title_re="", window_title="", max_controls=80, mode="visible"):
        try:
            window = self._window(title_re=title_re, title=window_title)

            if window is None:
                windows = []
                for w in self._desktop().windows():
                    try:
                        t = w.window_text().strip()
                        if t:
                            windows.append(t)
                    except Exception:
                        pass

                return {
                    "success": True,
                    "active_window": None,
                    "windows": windows[:50],
                    "controls": [],
                }

            title = window.window_text()
            controls = []

            try:
                descendants = window.descendants()
            except Exception:
                descendants = []

            for c in descendants[:int(max_controls)]:
                try:
                    info = c.element_info
                    controls.append({
                        "name": c.window_text(),
                        "control_type": str(getattr(info, "control_type", "") or ""),
                        "automation_id": str(getattr(info, "automation_id", "") or ""),
                        "class_name": str(getattr(info, "class_name", "") or ""),
                        "enabled": bool(c.is_enabled()),
                        "visible": bool(c.is_visible()),
                    })
                except Exception:
                    pass

            return {
                "success": True,
                "active_window": title,
                "windows": [title],
                "controls": controls,
            }

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def find(self, name="", title_re="", window_title="", control_type="", auto_id="", class_name=""):
        try:
            window, control = self._resolve_control(
                title_re=title_re,
                window_title=window_title,
                name=name,
                control_type=control_type,
                auto_id=auto_id,
                class_name=class_name,
            )

            if control is None:
                return {
                    "success": False,
                    "error": "Control not found.",
                    "window": window.window_text() if window else None,
                }

            info = control.element_info

            return {
                "success": True,
                "window": window.window_text() if window else None,
                "control": {
                    "name": control.window_text(),
                    "control_type": str(getattr(info, "control_type", "") or ""),
                    "automation_id": str(getattr(info, "automation_id", "") or ""),
                    "class_name": str(getattr(info, "class_name", "") or ""),
                },
            }

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def launch(self, app, mode="visible", wait=1.2):
        app = str(app or "").strip()

        aliases = {
            "notepad": "notepad.exe",
            "المفكرة": "notepad.exe",
            "calculator": "calc.exe",
            "الحاسبة": "calc.exe",
            "paint": "mspaint.exe",
            "الرسام": "mspaint.exe",
            "explorer": "explorer.exe",
        }

        command = aliases.get(app.lower(), app)

        try:
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            time.sleep(float(wait))

            focused = False

            # Prefer UI Automation to focus the new application.
            try:
                desktop = self._desktop()

                for w in desktop.windows():
                    try:
                        title = w.window_text()
                        if app.lower() in title.lower() or (
                            app.lower() == "notepad" and "notepad" in title.lower()
                        ):
                            try:
                                w.set_focus()
                            except Exception:
                                try:
                                    w.click_input()
                                except Exception:
                                    pass

                            focused = True
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            # Fallback to pygetwindow if available.
            if not focused:
                try:
                    import pygetwindow as gw

                    for w in gw.getAllWindows():
                        title = str(getattr(w, "title", "") or "")

                        if (
                            app.lower() in title.lower()
                            or (
                                app.lower() == "notepad"
                                and "notepad" in title.lower()
                            )
                        ):
                            try:
                                if w.isMinimized:
                                    w.restore()
                            except Exception:
                                pass

                            try:
                                w.activate()
                            except Exception:
                                pass

                            focused = True
                            break
                except Exception:
                    pass

            return {
                "success": True,
                "application": app,
                "command": command,
                "mode": self._mode(mode),
                "focused": focused,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"Could not launch application: {exc}",
            }

    def click(self, name="", title_re="", window_title="", control_type="", auto_id="", class_name="", mode="visible"):
        mode = self._mode(mode)

        try:
            window, control = self._resolve_control(
                title_re=title_re,
                window_title=window_title,
                name=name,
                control_type=control_type,
                auto_id=auto_id,
                class_name=class_name,
            )

            if control is None:
                return {"success": False, "error": "Control not found."}

            if mode == "background":
                for method_name in ("invoke", "click"):
                    try:
                        getattr(control, method_name)()
                        return {
                            "success": True,
                            "mode": "background",
                            "window": window.window_text() if window else None,
                            "control": control.window_text(),
                        }
                    except Exception:
                        pass

                return {
                    "success": False,
                    "requires_visible": True,
                    "error": "Background activation unavailable for this control.",
                }

            try:
                control.click_input()
            except Exception:
                try:
                    control.invoke()
                except Exception:
                    control.click()

            return {
                "success": True,
                "mode": "visible",
                "window": window.window_text() if window else None,
                "control": control.window_text(),
            }

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def set_text(
        self,
        text,
        name="",
        title_re="",
        window_title="",
        control_type="Edit",
        auto_id="",
        class_name="",
        mode="visible",
    ):
        mode = self._mode(mode)
        text = str(text or "")

        try:
            window, control = self._resolve_control(
                title_re=title_re,
                window_title=window_title,
                name=name,
                control_type=control_type,
                auto_id=auto_id,
                class_name=class_name,
            )

            # -----------------------------
            # UI Automation path
            # -----------------------------
            if control is not None:
                if mode == "background":
                    try:
                        control.set_edit_text(text)
                        return {
                            "success": True,
                            "mode": "background",
                            "window": window.window_text() if window else None,
                            "method": "uia.set_edit_text",
                            "text_length": len(text),
                        }
                    except Exception:
                        return {
                            "success": False,
                            "requires_visible": True,
                            "error": "Background text injection unavailable for this control.",
                        }

                try:
                    control.click_input()
                except Exception:
                    try:
                        control.set_focus()
                    except Exception:
                        pass

                pg = self._pyautogui()
                pg.hotkey("ctrl", "a")
                pg.write(text, interval=0.01)

                return {
                    "success": True,
                    "mode": "visible",
                    "window": window.window_text() if window else None,
                    "method": "uia+keyboard",
                    "text_length": len(text),
                }

            # -----------------------------
            # Visible fallback:
            # Some Windows applications such as modern Notepad expose
            # their document editor as Document/Custom rather than Edit.
            # In Visible mode we therefore use the real keyboard.
            # -----------------------------
            if mode == "visible" and window is not None:
                try:
                    window.set_focus()
                except Exception:
                    pass

                time.sleep(0.2)

                try:
                    rect = window.rectangle()

                    # Click roughly inside the main client area.
                    x = int((rect.left + rect.right) / 2)
                    y = int((rect.top + rect.bottom) / 2)

                    pg = self._pyautogui()
                    pg.click(x, y)
                    time.sleep(0.1)
                except Exception:
                    pg = self._pyautogui()

                pg.hotkey("ctrl", "a")
                pg.write(text, interval=0.01)

                return {
                    "success": True,
                    "mode": "visible",
                    "window": window.window_text(),
                    "method": "visible-keyboard-fallback",
                    "text_length": len(text),
                }

            if mode == "background":
                return {
                    "success": False,
                    "requires_visible": True,
                    "error": "Application does not expose an editable UI Automation control.",
                }

            return {
                "success": False,
                "error": "Editable control not found and no application window was resolved.",
            }

        except Exception as exc:
            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def type_text(self, text, mode="visible", interval=0.01):
        try:
            pg = self._pyautogui()
            text = str(text or "")
            pg.write(text, interval=float(interval))
            return {
                "success": True,
                "mode": self._mode(mode),
                "text_length": len(text),
            }
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def hotkey(self, keys, mode="visible"):
        try:
            pg = self._pyautogui()

            if isinstance(keys, str):
                keys = [x.strip() for x in keys.replace("+", " ").split() if x.strip()]

            keys = [str(x).strip().lower() for x in (keys or [])]

            if not keys:
                return {"success": False, "error": "No keys supplied."}

            pg.hotkey(*keys)

            return {
                "success": True,
                "mode": self._mode(mode),
                "keys": keys,
            }

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def press(self, key, mode="visible"):
        try:
            self._pyautogui().press(str(key))
            return {
                "success": True,
                "mode": self._mode(mode),
                "key": str(key),
            }
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def save_file(self, filename, mode="visible", wait=1.0):
        filename = str(filename or "").strip()

        if not filename:
            return {"success": False, "error": "Filename is required."}

        try:
            pg = self._pyautogui()
            pg.hotkey("ctrl", "s")
            time.sleep(float(wait))
            pg.write(filename, interval=0.02)
            pg.press("enter")
            time.sleep(float(wait))

            return {
                "success": True,
                "mode": self._mode(mode),
                "filename": filename,
            }

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def close_window(self, title_re="", window_title=""):
        try:
            window = self._window(title_re=title_re, title=window_title)

            if window is None:
                return {"success": False, "error": "Window not found."}

            title = window.window_text()
            window.close()

            return {"success": True, "window": title}

        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "inspect": {"description": "Inspect local Windows windows and UI controls."},
                "find": {"description": "Find a local UI control."},
                "launch": {"description": "Launch a local Windows application."},
                "click": {"description": "Click a local UI control."},
                "set_text": {"description": "Set text in a local editable control."},
                "type_text": {"description": "Type text with the local keyboard."},
                "hotkey": {"description": "Send a local keyboard hotkey."},
                "press": {"description": "Press a local keyboard key."},
                "save_file": {"description": "Save the active local application."},
                "close_window": {"description": "Close a local Windows window."},
            },
        }
