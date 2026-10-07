from __future__ import annotations

import re
from pathlib import Path

from tools.local_computer import LocalComputerTool


APP_MAP = {
    "notepad": "notepad.exe",
    "المفكرة": "notepad.exe",
    "calculator": "calc.exe",
    "الحاسبة": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "الرسام": "mspaint.exe",
    "explorer": "explorer.exe",
    "مستكشف الملفات": "explorer.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "vscode": "code.exe",
    "visual studio code": "code.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
}


def _quoted(text):
    patterns = (
        r'"([^"]+)"',
        r"'([^']+)'",
        r'“([^”]+)”',
        r'‘([^’]+)’',
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match and match.group(1).strip():
            return match.group(1).strip()

    return ""


def _filename(text):
    match = re.search(
        r'([A-Za-z0-9_-]+\.[A-Za-z0-9]{1,8})\b',
        text,
    )

    return (
        match.group(1)
        if match
        else ""
    )


def _resolve_app(text):
    low = text.casefold()

    for name, command in sorted(
        APP_MAP.items(),
        key=lambda x: len(x[0]),
        reverse=True,
    ):
        if (
            name.casefold()
            in low
        ):
            return name, command

    return None, None


def _desktop():
    candidates = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
    ]

    for path in candidates:

        if path.is_dir():
            return path.resolve()

    path = (
        Path.home()
        / "Desktop"
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path.resolve()


def try_run_local_windows_fast(
    user_message: str,
    execution_mode="visible",
):
    message = str(
        user_message or ""
    ).strip()

    low = message.casefold()

    wants_open = any(
        token in low
        for token in (
            "افتح",
            "شغّل",
            "شغل",
            "open",
            "launch",
        )
    )

    wants_type = any(
        token in low
        for token in (
            "اكتب",
            "اكتب فيها",
            "اكتب في",
            "type",
            "write",
            "paste",
        )
    )

    wants_save = any(
        token in low
        for token in (
            "احفظ",
            "حفظ",
            "save",
            "save as",
        )
    )

    wants_desktop = (
        "desktop" in low
        or "سطح المكتب" in message
    )

    app_name, command = (
        _resolve_app(
            message
        )
    )

    content = _quoted(
        message
    )

    filename = _filename(
        message
    )

    if (
        str(
            execution_mode
        ).casefold()
        != "visible"
        or not app_name
        or not wants_open
    ):
        return None

    if not (
        wants_type
        or wants_save
    ):
        return None

    if (
        wants_save
        and (
            not wants_desktop
            or not filename
        )
    ):
        return None

    if (
        wants_type
        and not content
    ):
        return {
            "success": False,
            "stage": "input_parsing",
            "error": (
                "A quoted text value "
                "was not found."
            ),
        }

    destination = (
        _desktop()
        / filename
        if filename
        else None
    )

    computer = LocalComputerTool()

    print()
    print(
        "=" * 78,
        flush=True,
    )
    print(
        "KAREEM_AGENT LOCAL WINDOWS OPERATOR",
        flush=True,
    )
    print(
        "APP:",
        app_name,
        "| COMMAND:",
        command,
        flush=True,
    )

    if destination:
        print(
            "DESTINATION:",
            str(destination),
            flush=True,
        )

    print(
        "=" * 78,
        flush=True,
    )

    try:

        print(
            "WINDOW STEP 1: launch",
            flush=True,
        )

        launched = computer.open_app(
            command,
            wait_seconds=0.8,
        )

        print(
            "OBSERVE:",
            launched,
            flush=True,
        )

        if not launched.get(
            "success"
        ):
            return {
                "success": False,
                "stage": "launch",
                "evidence": launched,
            }

        print(
            "WINDOW STEP 2: detect/focus TARGET PID",
            flush=True,
        )

        target_pid = launched.get("pid")
        target_hwnd = launched.get("hwnd")
        title = str(
            launched.get("window")
            or ""
        ).strip()

        print(
            "TARGET:",
            {
                "pid": target_pid,
                "hwnd": target_hwnd,
                "window": title,
                "attached": launched.get("attached"),
            },
            flush=True,
        )

        if not title or not target_pid:
            return {
                "success": False,
                "stage": "window_detection",
                "error": (
                    "The launched application "
                    "did not produce a verified "
                    "target window."
                ),
                "evidence": launched,
            }

        # Re-acquire the exact window belonging to the launched PID.
        target_window = computer._find_window(
            title=title,
            pid=target_pid,
            hwnd=target_hwnd,
        )

        if target_window is None:
            return {
                "success": False,
                "stage": "window_attachment",
                "error": (
                    "Could not re-acquire the "
                    "launched window by PID/HWND."
                ),
                "evidence": launched,
            }

        computer._focus(target_window)

        time.sleep(0.2)

        verified_window = computer._find_window(
            title=title,
            pid=target_pid,
            hwnd=target_hwnd,
        )

        if verified_window is None:
            return {
                "success": False,
                "stage": "window_attachment",
                "error": (
                    "Target window disappeared "
                    "before interaction."
                ),
            }

        if wants_type:

            print(
                "WINDOW STEP 3: set text + verify",
                flush=True,
            )

            typed = computer.set_text(
                content,
                title=title,
                verify=True,
                pid=target_pid,
                hwnd=target_hwnd,
            )

            print(
                "OBSERVE:",
                typed,
                flush=True,
            )

            if not typed.get(
                "success"
            ):
                return {
                    "success": False,
                    "stage": "text_verification",
                    "error": (
                        "The requested text "
                        "was not verified "
                        "inside the target app."
                    ),
                    "evidence": typed,
                }

        if wants_save:

            print(
                "WINDOW STEP 4: Save As + dialog verification",
                flush=True,
            )

            saved = computer.save_file(
                str(
                    destination
                ),
                window_title=title,
                timeout=7,
                overwrite=True,
            )

            print(
                "OBSERVE:",
                saved,
                flush=True,
            )

            if not saved.get(
                "success"
            ):
                return {
                    "success": False,
                    "stage": "save",
                    "error": (
                        "Save As did not "
                        "produce the requested "
                        "destination file."
                    ),
                    "evidence": saved,
                }

            print(
                "WINDOW STEP 5: final file verification",
                flush=True,
            )

            verified = computer.verify_file(
                str(
                    destination
                ),
                expected_text=(
                    content
                    if wants_type
                    else None
                ),
            )

            print(
                "OBSERVE:",
                verified,
                flush=True,
            )

            if not verified.get(
                "success"
            ):
                return {
                    "success": False,
                    "stage": "file_verification",
                    "error": (
                        "The final file "
                        "evidence does not "
                        "match the requested state."
                    ),
                    "evidence": verified,
                }

        print(
            "WINDOW OPERATOR VERIFIED",
            flush=True,
        )

        return {
            "success": True,
            "fast_path": True,
            "application": app_name,
            "file": (
                str(destination)
                if destination
                else None
            ),
            "content": (
                content
                if content
                else None
            ),
            "verification": (
                "ui_state_and_file_evidence"
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "stage": "local_windows_operator",
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }

