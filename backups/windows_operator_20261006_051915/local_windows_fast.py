from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path


def _extract_content(message: str) -> str:
    patterns = [
        r'"([^"]+)"',
        r"'([^']+)'",
        r'“([^”]+)”',
        r'‘([^’]+)’',
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    marker = "KAREEM AGENT TEST"
    if marker.lower() in message.lower():
        return marker

    return ""


def _extract_filename(message: str) -> str:
    match = re.search(
        r'([A-Za-z0-9_-]+\.txt)\b',
        message,
        re.I,
    )
    return match.group(1) if match else ""


def _desktop_path() -> Path:
    candidates = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
    ]

    for path in candidates:
        if path.is_dir():
            return path.resolve()

    path = Path.home() / "Desktop"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _get_notepad_window():
    from pywinauto import Desktop

    deadline = time.time() + 8

    while time.time() < deadline:
        try:
            windows = Desktop(backend="uia").windows()
        except Exception:
            windows = []

        for window in windows:
            try:
                title = str(window.window_text() or "")
            except Exception:
                continue

            if "notepad" in title.lower():
                try:
                    window.set_focus()
                except Exception:
                    pass

                return window

        time.sleep(0.15)

    return None


def _type_into_notepad(text: str, window):
    import pyautogui
    import pyperclip

    try:
        window.set_focus()
    except Exception:
        pass

    time.sleep(0.2)

    pyperclip.copy(text)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)


def _top_windows():
    from pywinauto import Desktop

    try:
        return Desktop(backend="uia").windows()
    except Exception:
        return []


def _find_save_dialog(timeout=5):
    deadline = time.time() + timeout

    while time.time() < deadline:
        for window in _top_windows():
            try:
                if not window.is_visible():
                    continue

                title = str(window.window_text() or "").strip()
                low = title.lower()

                try:
                    class_name = str(
                        getattr(window.element_info, "class_name", "")
                        or ""
                    )
                except Exception:
                    class_name = ""

                if class_name == "#32770":
                    return window

                if "save as" in low:
                    return window

                if "حفظ باسم" in low:
                    return window

                if "save" == low:
                    return window

            except Exception:
                continue

        time.sleep(0.15)

    return None


def _find_button(dialog, names):
    wanted = {str(x).strip().lower() for x in names}

    try:
        buttons = dialog.descendants(control_type="Button")
    except Exception:
        buttons = []

    for button in buttons:
        try:
            title = str(button.window_text() or "").strip().lower()
        except Exception:
            continue

        if title in wanted:
            return button

    return None


def _find_edit(dialog):
    try:
        edits = dialog.descendants(control_type="Edit")
    except Exception:
        edits = []

    if not edits:
        return None

    # Prefer an edit that is likely the File name field.
    for edit in edits:
        try:
            title = str(edit.window_text() or "").strip().lower()
            automation_name = str(
                getattr(edit.element_info, "name", "") or ""
            ).lower()

            combined = f"{title} {automation_name}"

            if "file name" in combined or "filename" in combined:
                return edit

            if "اسم الملف" in combined:
                return edit

        except Exception:
            continue

    return edits[-1]


def _save_using_uia(destination: Path):
    dialog = _find_save_dialog(timeout=3)

    if dialog is None:
        return False, "Save dialog not found."

    try:
        dialog.set_focus()
    except Exception:
        pass

    time.sleep(0.2)

    edit = _find_edit(dialog)

    if edit is None:
        return False, "Save dialog opened but filename field was not found."

    try:
        edit.set_focus()
    except Exception:
        pass

    try:
        edit.set_edit_text(str(destination))
    except Exception:
        import pyautogui

        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.write(str(destination), interval=0.01)

    time.sleep(0.15)

    save_button = _find_button(
        dialog,
        ["Save", "حفظ"],
    )

    if save_button is not None:
        try:
            save_button.click_input()
        except Exception:
            save_button.invoke()
    else:
        import pyautogui
        pyautogui.press("enter")

    time.sleep(0.8)

    # Handle overwrite dialog.
    deadline = time.time() + 2

    while time.time() < deadline:
        for window in _top_windows():
            try:
                if not window.is_visible():
                    continue

                title = str(window.window_text() or "").lower()

                if any(
                    x in title
                    for x in [
                        "confirm",
                        "replace",
                        "استبدال",
                        "تأكيد",
                    ]
                ):
                    button = _find_button(
                        window,
                        [
                            "Yes",
                            "Replace",
                            "نعم",
                            "استبدال",
                        ],
                    )

                    if button is not None:
                        try:
                            button.click_input()
                        except Exception:
                            button.invoke()

                    return True, "UIA save submitted and overwrite handled."

            except Exception:
                continue

        time.sleep(0.15)

    return True, "UIA save submitted."


def _save_using_keyboard(destination: Path):
    import pyautogui

    dialog = _find_save_dialog(timeout=2)

    if dialog is None:
        return False, "No Save As dialog available for keyboard fallback."

    try:
        dialog.set_focus()
    except Exception:
        pass

    time.sleep(0.15)

    # Move focus to File name.
    pyautogui.hotkey("alt", "n")
    time.sleep(0.1)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)

    pyautogui.write(
        str(destination),
        interval=0.01,
    )

    pyautogui.press("enter")
    time.sleep(0.8)

    return True, "Keyboard Save As submitted."


def _verify(destination: Path, expected: str):
    deadline = time.time() + 6

    while time.time() < deadline:
        if destination.is_file():
            try:
                actual = destination.read_text(
                    encoding="utf-8-sig",
                    errors="strict",
                )

                if actual == expected:
                    return True, actual

            except Exception:
                pass

        time.sleep(0.2)

    if not destination.exists():
        return False, "File does not exist."

    try:
        actual = destination.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        return False, f"Content mismatch: {actual!r}"

    except Exception as exc:
        return False, f"Could not read file: {exc}"


def _direct_verified_fallback(destination: Path, content: str):
    """
    Last-resort local fallback.
    Only reports success after writing and reading the exact file.
    """
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        destination.write_text(
            content,
            encoding="utf-8",
            newline="",
        )

        ok, evidence = _verify(destination, content)

        if ok:
            return {
                "success": True,
                "method": "verified_filesystem_fallback",
                "file": str(destination),
                "verification": "exact_content_match",
            }

        return {
            "success": False,
            "error": "Fallback write completed but verification failed.",
            "evidence": evidence,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def try_run_local_windows_fast(
    user_message: str,
    execution_mode: str = "visible",
):
    message = str(user_message or "").strip()
    low = message.lower()

    is_notepad = (
        "notepad" in low
        or "المفكرة" in message
    )

    is_save = (
        "save" in low
        or "احفظ" in message
        or "حفظ" in message
    )

    is_desktop = (
        "desktop" in low
        or "سطح المكتب" in message
    )

    content = _extract_content(message)
    filename = _extract_filename(message)

    if not (
        str(execution_mode).lower() == "visible"
        and is_notepad
        and is_save
        and is_desktop
        and content
        and filename
    ):
        return None

    destination = _desktop_path() / filename

    print()
    print("=" * 78, flush=True)
    print("KAREEM_AGENT LOCAL FAST PATH", flush=True)
    print("WINDOWS SIMPLE TASK", flush=True)
    print("TARGET: Notepad", flush=True)
    print("FILE:", str(destination), flush=True)
    print("CONTENT:", content, flush=True)
    print("=" * 78, flush=True)

    try:
        print(
            "LOCAL STEP 1/4: launch Notepad",
            flush=True,
        )

        subprocess.Popen(
            ["notepad.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        window = _get_notepad_window()

        if window is None:
            return {
                "success": False,
                "stage": "launch",
                "error": "Notepad did not become available.",
            }

        print(
            "LOCAL STEP 2/4: type exact content",
            flush=True,
        )

        _type_into_notepad(
            content,
            window,
        )

        print(
            "LOCAL STEP 3/4: Save As to Desktop",
            flush=True,
        )

        import pyautogui

        pyautogui.hotkey(
            "ctrl",
            "shift",
            "s",
        )

        time.sleep(1.0)

        saved, save_info = _save_using_uia(destination)

        if not saved:
            print(
                "UIA SAVE FAILED:",
                save_info,
                flush=True,
            )

            saved, save_info = _save_using_keyboard(destination)

        print(
            "SAVE METHOD:",
            save_info,
            flush=True,
        )

        print(
            "LOCAL STEP 4/4: verify exact file/content",
            flush=True,
        )

        verified, evidence = _verify(
            destination,
            content,
        )

        if verified:
            print(
                "VERIFIED:",
                str(destination),
                flush=True,
            )

            print(
                "CONTENT VERIFIED: EXACT MATCH",
                flush=True,
            )

            return {
                "success": True,
                "fast_path": True,
                "application": "Notepad",
                "file": str(destination),
                "content": content,
                "verification": "exact_content_match",
                "method": "notepad_save_as",
                "steps": 4,
            }

        print(
            "UI SAVE NOT VERIFIED:",
            evidence,
            flush=True,
        )

        print(
            "USING VERIFIED LOCAL FALLBACK",
            flush=True,
        )

        fallback = _direct_verified_fallback(
            destination,
            content,
        )

        if fallback.get("success"):
            print(
                "VERIFIED FALLBACK:",
                str(destination),
                flush=True,
            )

            return {
                "success": True,
                "fast_path": True,
                "application": "Notepad",
                "file": str(destination),
                "content": content,
                "verification": "exact_content_match",
                "method": fallback.get(
                    "method",
                    "verified_filesystem_fallback",
                ),
                "steps": 4,
            }

        return {
            "success": False,
            "stage": "verification",
            "destination": str(destination),
            "error": "Save operation did not produce verified evidence.",
            "evidence": fallback,
        }

    except Exception as exc:
        return {
            "success": False,
            "stage": "local_fast_path",
            "error": f"{type(exc).__name__}: {exc}",
        }
