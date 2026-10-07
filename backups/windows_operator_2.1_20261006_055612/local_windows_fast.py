
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

