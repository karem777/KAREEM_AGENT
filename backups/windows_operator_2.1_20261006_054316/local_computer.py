from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

import pyautogui
import pyperclip
from pywinauto import Desktop


class LocalComputerTool:
    """
    Universal local Windows operator.

    UIA is preferred for control discovery and direct control manipulation.
    Win32 is used as a second discovery backend.
    pyautogui/clipboard is used only when visible interaction is required.

    Mutating actions try to return evidence instead of treating an input event
    as proof that the requested state was actually reached.
    """

    name = "computer"

    description = (
        "Universal local Windows operator. Launch/focus apps, inspect controls, "
        "click/type/keys, interact with dialogs, save files, screenshots, and verify state."
    )

    def __init__(self, workspace=None):
        self.workspace = Path(workspace or os.getcwd()).resolve()

        self.mode = os.getenv(
            "KAREEM_EXECUTION_MODE",
            "visible",
        ).lower()

        if self.mode not in {"visible", "background"}:
            self.mode = "visible"

    # ============================================================
    # Window primitives
    # ============================================================

    @staticmethod
    def _fg_hwnd():
        try:
            return int(
                ctypes.windll.user32.GetForegroundWindow()
            )
        except Exception:
            return 0

    @staticmethod
    def _fg_title():
        hwnd = LocalComputerTool._fg_hwnd()

        if not hwnd:
            return ""

        try:
            buffer = ctypes.create_unicode_buffer(512)

            ctypes.windll.user32.GetWindowTextW(
                hwnd,
                buffer,
                511,
            )

            return buffer.value.strip()

        except Exception:
            return ""

    @staticmethod
    def _title(window):
        try:
            return str(
                window.window_text() or ""
            ).strip()

        except Exception:
            return ""

    @staticmethod
    def _control_type(window):
        try:
            return str(
                window.element_info.control_type or ""
            )

        except Exception:
            return ""

    @staticmethod
    def _name(window):
        try:
            return str(
                window.element_info.name or ""
            )

        except Exception:
            return ""

    @staticmethod
    def _read(window):
        for method_name in (
            "get_value",
            "window_text",
        ):
            try:
                method = getattr(
                    window,
                    method_name,
                )

                value = method()

                if value is not None:
                    return str(value)

            except Exception:
                pass

        try:
            return str(
                window.element_info.name or ""
            )

        except Exception:
            return ""

    def _windows(self):
        """
        Discover windows using both UIA and Win32.
        """

        seen = {}

        for backend in (
            "uia",
            "win32",
        ):
            try:
                desktop = Desktop(
                    backend=backend
                )

                for window in desktop.windows():

                    try:
                        key = int(
                            window.handle
                        )

                    except Exception:
                        key = id(window)

                    seen.setdefault(
                        key,
                        window,
                    )

            except Exception:
                pass

        return list(seen.values())

    def _find_window(self, title="", pid=None, hwnd=None):
        needle = str(title or "").strip().casefold()
        target_pid = int(pid) if pid is not None else None
        target_hwnd = int(hwnd) if hwnd is not None else None

        candidates = []

        for window in self._windows():

            try:
                if not window.is_visible():
                    continue
            except Exception:
                pass

            try:
                current_hwnd = int(window.handle)
            except Exception:
                current_hwnd = None

            if target_hwnd is not None:
                if current_hwnd == target_hwnd:
                    return window
                continue

            if target_pid is not None:
                try:
                    current_pid = int(window.process_id())
                except Exception:
                    current_pid = None

                if current_pid != target_pid:
                    continue

            current_title = self._title(window)

            if not needle:
                candidates.append(window)
                continue

            if needle in current_title.casefold():
                candidates.append(window)

        if candidates:
            # Prefer a titled window over hidden/utility children.
            candidates.sort(
                key=lambda w: (
                    0 if self._title(w) else 1,
                    len(self._title(w)),
                )
            )

            return candidates[0]

        return None

    @staticmethod
    def _focus(window):
        try:
            window.restore()
        except Exception:
            pass

        try:
            window.set_focus()
            return True

        except Exception:
            return False

    # ============================================================
    # Control discovery
    # ============================================================

    def _editable_controls(self, window):
        controls = []

        for control_type in (
            "Edit",
            "Document",
        ):
            try:
                controls.extend(
                    window.descendants(
                        control_type=control_type
                    )
                )
            except Exception:
                pass

        return controls

    def _verify_control_text(
        self,
        control,
        expected,
        timeout=2.5,
    ):
        expected = str(expected)

        deadline = (
            time.time()
            + float(timeout)
        )

        last = ""

        while time.time() < deadline:

            last = self._read(
                control
            )

            if (
                last == expected
                or expected in last
            ):
                return True, last

            time.sleep(0.12)

        return False, last

    # ============================================================
    # Applications / Windows
    # ============================================================

    def open_app(
        self,
        command,
        args=None,
        wait_seconds=0.8,
    ):
        command = str(
            command or ""
        ).strip()

        if not command:
            return {
                "success": False,
                "error": "command is required",
            }

        argv = [
            command,
            *[
                str(x)
                for x in (args or [])
            ],
        ]

        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except FileNotFoundError:
            try:
                process = subprocess.Popen(
                    [
                        "cmd",
                        "/c",
                        "start",
                        "",
                        command,
                        *(args or []),
                    ],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            except Exception as exc:
                return {
                    "success": False,
                    "error": str(exc),
                }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        deadline = time.time() + max(
            2.0,
            min(float(wait_seconds) + 3.0, 8.0),
        )

        target = None

        while time.time() < deadline:
            target = self._find_window(
                pid=process.pid
            )

            if target is not None:
                break

            time.sleep(0.12)

        if target is None:
            return {
                "success": False,
                "pid": process.pid,
                "command": argv,
                "error": (
                    "Application launched, but "
                    "no top-level window belonging "
                    "to the launched PID was found."
                ),
                "foreground": self._fg_title(),
            }

        target_title = self._title(target)

        focused = self._focus(target)

        time.sleep(0.15)

        try:
            target_hwnd = int(target.handle)
        except Exception:
            target_hwnd = None

        foreground_hwnd = self._fg_hwnd()

        attached = (
            target_hwnd is not None
            and foreground_hwnd == target_hwnd
        )

        return {
            "success": True,
            "pid": process.pid,
            "hwnd": target_hwnd,
            "window": target_title,
            "command": argv,
            "focused": bool(focused),
            "attached": attached,
            "foreground": self._fg_title(),
            "foreground_hwnd": foreground_hwnd,
        }

    def list_windows(self, limit=120):
        rows = []

        for window in self._windows():

            title = self._title(
                window
            )

            if not title:
                continue

            try:
                hwnd = int(
                    window.handle
                )
            except Exception:
                hwnd = None

            try:
                pid = window.process_id()
            except Exception:
                pid = None

            rows.append(
                {
                    "title": title,
                    "hwnd": hwnd,
                    "pid": pid,
                    "control_type": self._control_type(
                        window
                    ),
                }
            )

            if len(rows) >= int(limit):
                break

        return {
            "success": True,
            "foreground": self._fg_title(),
            "windows": rows,
        }

    def active_window(self):
        return {
            "success": bool(
                self._fg_hwnd()
            ),
            "hwnd": self._fg_hwnd(),
            "title": self._fg_title(),
        }

    def focus_window(self, title):
        window = self._find_window(
            title,
            pid=pid,
            hwnd=hwnd,
        )

        if window is None:
            return {
                "success": False,
                "error": (
                    f"Window not found: {title}"
                ),
            }

        focused = self._focus(
            window
        )

        time.sleep(
            0.15
        )

        return {
            "success": focused,
            "window": self._title(
                window
            ),
            "foreground": self._fg_title(),
        }

    def inspect(
        self,
        title="",
        max_controls=80,
    ):
        window = self._find_window(
            title,
            pid=pid,
            hwnd=hwnd,
        )

        if window is None:
            return {
                "success": False,
                "error": (
                    f"Window not found: "
                    f"{title or '<foreground>'}"
                ),
            }

        controls = []

        try:
            items = window.descendants()
        except Exception:
            items = []

        for item in items:

            name = self._name(
                item
            )

            text = self._read(
                item
            )

            control_type = self._control_type(
                item
            )

            if (
                name
                or text
                or control_type
            ):
                controls.append(
                    {
                        "name": name,
                        "text": text[:500],
                        "control_type": control_type,
                    }
                )

            if len(controls) >= int(
                max_controls
            ):
                break

        return {
            "success": True,
            "window": self._title(
                window
            ),
            "foreground": self._fg_title(),
            "controls": controls,
        }

    # ============================================================
    # Native controls
    # ============================================================

    def click_control(
        self,
        title="",
        name="",
        control_type="",
        index=0,
    ):
        window = self._find_window(
            title,
            pid=pid,
            hwnd=hwnd,
        )

        if window is None:
            return {
                "success": False,
                "error": (
                    f"Window not found: {title}"
                ),
            }

        wanted_name = str(
            name or ""
        ).casefold()

        wanted_type = str(
            control_type or ""
        ).casefold()

        matches = []

        try:
            items = window.descendants()
        except Exception:
            items = []

        for item in items:

            item_name = self._name(
                item
            ).casefold()

            item_type = self._control_type(
                item
            ).casefold()

            if (
                wanted_name
                and wanted_name not in item_name
            ):
                continue

            if (
                wanted_type
                and wanted_type not in item_type
            ):
                continue

            matches.append(
                item
            )

        if not matches:
            return {
                "success": False,
                "error": "Matching control not found.",
                "window": self._title(
                    window
                ),
            }

        control = matches[
            min(
                int(index),
                len(matches) - 1,
            )
        ]

        self._focus(
            window
        )

        try:
            control.click_input()

        except Exception:

            try:
                control.invoke()

            except Exception as exc:

                return {
                    "success": False,
                    "error": str(exc),
                }

        time.sleep(
            0.15
        )

        return {
            "success": True,
            "window": self._title(
                window
            ),
            "control": self._name(
                control
            ),
            "control_type": self._control_type(
                control
            ),
        }

    def set_text(
        self,
        text,
        title="",
        control_name="",
        verify=True,
        pid=None,
        hwnd=None,
    ):
        expected = str(
            text
        )

        window = self._find_window(
            title,
            pid=pid,
            hwnd=hwnd,
        )

        if window is None:
            return {
                "success": False,
                "error": (
                    f"Window not found: "
                    f"{title or '<foreground>'}"
                ),
            }

        if self.mode == "visible":
            self._focus(
                window
            )

        control = None

        if control_name:

            wanted = str(
                control_name
            ).casefold()

            try:
                for item in window.descendants():

                    if (
                        wanted
                        in self._name(
                            item
                        ).casefold()
                    ):
                        control = item
                        break

            except Exception:
                pass

        if control is None:

            edits = self._editable_controls(
                window
            )

            if edits:
                control = edits[0]

        if control is None:
            return {
                "success": False,
                "error": (
                    "No editable control found."
                ),
                "window": self._title(
                    window
                ),
            }

        try:
            control.set_focus()
        except Exception:
            pass

        applied = False

        for method_name in (
            "set_edit_text",
            "set_value",
        ):
            try:
                getattr(
                    control,
                    method_name,
                )(expected)

                applied = True
                break

            except Exception:
                pass

        if not applied:

            if self.mode == "background":
                return {
                    "success": False,
                    "error": (
                        "Target control has no "
                        "background text/value setter."
                    ),
                }

            try:

                pyperclip.copy(
                    expected
                )

                pyautogui.hotkey(
                    "ctrl",
                    "a",
                )

                pyautogui.hotkey(
                    "ctrl",
                    "v",
                )

                applied = True

            except Exception as exc:

                return {
                    "success": False,
                    "error": (
                        "Unicode keyboard fallback failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

        time.sleep(
            0.25
        )

        if verify:

            verified, actual = (
                self._verify_control_text(
                    control,
                    expected,
                )
            )

            if not verified:

                return {
                    "success": False,
                    "stage": "verification",
                    "error": (
                        "Text was sent but the "
                        "target control did not "
                        "confirm it."
                    ),
                    "expected": expected,
                    "actual": actual,
                    "window": self._title(
                        window
                    ),
                }

        return {
            "success": True,
            "window": self._title(
                window
            ),
            "text_length": len(
                expected
            ),
            "verification": (
                "control_text_match"
                if verify
                else "not_requested"
            ),
        }

    # ============================================================
    # Visible keyboard
    # ============================================================

    def type_text(
        self,
        text,
        verify_window="",
        interval=0.01,
    ):
        if self.mode == "background":
            return {
                "success": False,
                "error": (
                    "type_text is visible-input only. "
                    "Use set_text for background mode."
                ),
            }

        expected = str(
            text
        )

        if verify_window:

            window = self._find_window(
                verify_window
            )

            if window is None:
                return {
                    "success": False,
                    "error": (
                        f"Window not found: "
                        f"{verify_window}"
                    ),
                }

            self._focus(
                window
            )

        pyperclip.copy(
            expected
        )

        pyautogui.hotkey(
            "ctrl",
            "a",
        )

        pyautogui.hotkey(
            "ctrl",
            "v",
        )

        time.sleep(
            max(
                0.1,
                min(
                    float(interval)
                    * max(
                        len(expected),
                        1,
                    ),
                    1.0,
                ),
            )
        )

        return {
            "success": True,
            "text_length": len(
                expected
            ),
            "foreground": self._fg_title(),
        }

    def hotkey(self, keys):
        if self.mode == "background":
            return {
                "success": False,
                "error": (
                    "hotkey is visible-input only."
                ),
            }

        values = [
            str(k).strip().lower()
            for k in (keys or [])
            if str(k).strip()
        ]

        if not values:
            return {
                "success": False,
                "error": "keys required",
            }

        pyautogui.hotkey(
            *values
        )

        time.sleep(
            0.12
        )

        return {
            "success": True,
            "keys": values,
            "foreground": self._fg_title(),
        }

    def press(
        self,
        key,
        presses=1,
        interval=0.05,
    ):
        if self.mode == "background":
            return {
                "success": False,
                "error": (
                    "press is visible-input only."
                ),
            }

        value = str(
            key
        )

        pyautogui.press(
            value,
            presses=int(
                presses
            ),
            interval=float(
                interval
            ),
        )

        time.sleep(
            0.1
        )

        return {
            "success": True,
            "key": value,
            "presses": int(
                presses
            ),
            "foreground": self._fg_title(),
        }

    def wait(
        self,
        seconds=0.5,
    ):
        delay = max(
            0.0,
            min(
                float(seconds),
                30.0,
            ),
        )

        time.sleep(
            delay
        )

        return {
            "success": True,
            "waited_seconds": delay,
            "foreground": self._fg_title(),
        }

    def screenshot(
        self,
        path="",
    ):
        if not path:
            path = str(
                self.workspace
                / "agent_memory"
                / "screenshots"
                / f"desktop_{int(time.time() * 1000)}.png"
            )

        target = (
            Path(path)
            .expanduser()
            .resolve()
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            pyautogui.screenshot().save(
                str(target)
            )

            return {
                "success": True,
                "path": str(
                    target
                ),
            }

        except Exception as exc:

            return {
                "success": False,
                "error": str(exc),
            }

    # ============================================================
    # Save / verification
    # ============================================================

    def save_file(
        self,
        path,
        window_title="",
        timeout=7,
        overwrite=True,
    ):
        if self.mode == "background":
            return {
                "success": False,
                "error": (
                    "save_file currently needs "
                    "visible dialog interaction."
                ),
            }

        destination = (
            Path(path)
            .expanduser()
            .resolve()
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        application = (
            self._find_window(
                window_title
            )
            if window_title
            else None
        )

        before_title = (
            self._title(application)
            if application
            else self._fg_title()
        )

        if application:
            self._focus(
                application
            )

        pyautogui.hotkey(
            "ctrl",
            "shift",
            "s",
        )

        deadline = (
            time.time()
            + float(timeout)
        )

        dialog = None

        while time.time() < deadline:

            current_title = self._fg_title()

            # Critical safety rule:
            # never type a path until the foreground
            # window is known to be different from the app.
            if (
                current_title
                and before_title
                and current_title.casefold()
                != before_title.casefold()
            ):
                dialog = self._find_window(
                    current_title
                )

                if dialog:
                    break

            for window in self._windows():

                title = self._title(
                    window
                )

                low = title.casefold()

                if (
                    title
                    and title.casefold()
                    != before_title.casefold()
                    and (
                        "save as" in low
                        or "حفظ باسم" in low
                        or "replace" in low
                        or "confirm" in low
                        or "استبدال" in low
                        or "تأكيد" in low
                    )
                ):
                    dialog = window
                    break

            if dialog:
                break

            time.sleep(
                0.12
            )

        if dialog is None:
            return {
                "success": False,
                "stage": "dialog_detection",
                "error": (
                    "Save dialog was not detected. "
                    "No file path was typed into the app."
                ),
                "foreground": self._fg_title(),
            }

        self._focus(
            dialog
        )

        edits = []

        try:
            edits = dialog.descendants(
                control_type="Edit"
            )
        except Exception:
            pass

        filename_edit = None

        for item in edits:

            haystack = (
                f"{self._name(item)} "
                f"{self._read(item)}"
            ).casefold()

            if (
                "file name" in haystack
                or "filename" in haystack
                or "اسم الملف" in haystack
            ):
                filename_edit = item
                break

        if filename_edit is None and edits:
            filename_edit = edits[-1]

        pyperclip.copy(
            str(destination)
        )

        if filename_edit is not None:

            try:
                filename_edit.set_focus()
            except Exception:
                pass

            placed = False

            for method_name in (
                "set_edit_text",
                "set_value",
            ):
                try:

                    getattr(
                        filename_edit,
                        method_name,
                    )(
                        str(destination)
                    )

                    placed = True
                    break

                except Exception:
                    pass

            if not placed:

                pyautogui.hotkey(
                    "ctrl",
                    "a",
                )

                pyautogui.hotkey(
                    "ctrl",
                    "v",
                )

        else:

            pyautogui.hotkey(
                "ctrl",
                "a",
            )

            pyautogui.hotkey(
                "ctrl",
                "v",
            )

        pyautogui.press(
            "enter"
        )

        time.sleep(
            0.8
        )

        if (
            overwrite
            and destination.exists()
        ):

            for _ in range(20):

                for window in self._windows():

                    title = self._title(
                        window
                    ).casefold()

                    if any(
                        token in title
                        for token in (
                            "replace",
                            "confirm",
                            "استبدال",
                            "تأكيد",
                        )
                    ):

                        self._focus(
                            window
                        )

                        pyautogui.press(
                            "left"
                        )

                        pyautogui.press(
                            "enter"
                        )

                        time.sleep(
                            0.6
                        )

                        break

                time.sleep(
                    0.08
                )

        return {
            "success": destination.exists(),
            "path": str(
                destination
            ),
            "dialog": self._title(
                dialog
            ),
            "foreground": self._fg_title(),
        }

    def verify_file(
        self,
        path,
        expected_text=None,
    ):
        target = (
            Path(path)
            .expanduser()
            .resolve()
        )

        if not target.is_file():
            return {
                "success": False,
                "exists": False,
                "path": str(
                    target
                ),
                "error": (
                    "File does not exist."
                ),
            }

        result = {
            "success": True,
            "exists": True,
            "path": str(
                target
            ),
            "size": target.stat().st_size,
        }

        if expected_text is not None:

            try:
                actual = target.read_text(
                    encoding="utf-8-sig"
                )

            except Exception:

                actual = target.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

            result[
                "content_match"
            ] = (
                actual
                == str(
                    expected_text
                )
            )

            result[
                "content_length"
            ] = len(
                actual
            )

            result[
                "expected_length"
            ] = len(
                str(
                    expected_text
                )
            )

            if (
                actual
                != str(
                    expected_text
                )
            ):

                result[
                    "success"
                ] = False

                result[
                    "actual_preview"
                ] = actual[:1000]

        return result

    # ============================================================
    # Tool schema
    # ============================================================

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "open_app": "Launch a Windows app.",
                "list_windows": "List top-level windows.",
                "active_window": "Read the foreground window.",
                "focus_window": "Focus a window by title.",
                "inspect": "Inspect accessible controls.",
                "click_control": "Click an accessible UI control.",
                "set_text": "Set Unicode text and verify the target control.",
                "type_text": "Paste Unicode text into the focused control.",
                "hotkey": "Send a keyboard shortcut.",
                "press": "Press a key.",
                "wait": "Wait for UI state.",
                "screenshot": "Capture the desktop.",
                "save_file": "Use Save As and verify the destination.",
                "verify_file": "Verify file existence and optional exact content.",
            },
        }

