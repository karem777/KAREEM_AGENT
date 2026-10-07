from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.local_computer import LocalComputerTool


def print_summary(label, inspected):
    controls = inspected.get("controls") or []
    counts = {}
    for c in controls:
        kind = str(c.get("control_type") or "")
        counts[kind] = counts.get(kind, 0) + 1

    print(f"{label} CONTROL COUNT: {len(controls)}")
    print(f"{label} CONTROL TYPES: {counts}")


def run_notepad(tool):
    print("")
    print("=== REAL APP: NOTEPAD ===")

    opened = tool.open_app(
        "notepad.exe",
        wait_seconds=2.0,
        process_hint="Notepad.exe",
        title_hint="Notepad|Untitled|المفكرة",
        require_new_window=True,
    )
    print("OPEN:", opened)

    if not opened.get("success"):
        return False

    target_id = str((opened.get("target") or {}).get("target_id") or "")
    try:
        inspected = tool.inspect(target_id=target_id, max_controls=200)
        print("INSPECT:", inspected)
        if not inspected.get("success"):
            return False

        print_summary("NOTEPAD", inspected)

        print("NOTEPAD: visible type")
        typed = tool.type_text("KAREEM REAL APP TEST")
        print("TYPE:", typed)
        if not typed.get("success"):
            return False

        print("NOTEPAD: clear test text")
        cleared = tool.hotkey(["ctrl", "a"])
        print("CTRL+A:", cleared)
        if not cleared.get("success"):
            return False

        cleared = tool.press("backspace")
        print("BACKSPACE:", cleared)
        if not cleared.get("success"):
            return False

        print("NOTEPAD: close")
        closed = tool.close_window(target_id=target_id, confirm=True)
        print("CLOSE:", closed)

        if not closed.get("success"):
            print("CLOSE FALLBACK: invoke title-bar Close button")
            fallback = tool.invoke_control(
                target_id=target_id,
                control_type="Button",
                text="Close",
            )
            print("CLOSE FALLBACK:", fallback)
            time.sleep(0.8)

            closed = {
                "success": not tool.window_exists(
                    int((opened.get("target") or {}).get("hwnd") or 0)
                )
            }
            print("CLOSE VERIFY:", closed)

        return bool(closed.get("success"))

    except Exception as exc:
        print("NOTEPAD EXCEPTION:", type(exc).__name__, exc)
        try:
            tool.close_window(target_id=target_id, confirm=True)
        except Exception:
            pass
        return False


def run_paint(tool):
    print("")
    print("=== REAL APP: PAINT ===")

    opened = tool.open_app(
        "mspaint.exe",
        wait_seconds=2.0,
        process_hint="mspaint.exe",
        title_hint="Paint|الرسام",
        require_new_window=True,
    )
    print("OPEN:", opened)

    if not opened.get("success"):
        return False

    target_id = str((opened.get("target") or {}).get("target_id") or "")
    try:
        inspected = tool.inspect(target_id=target_id, max_controls=300)
        print("INSPECT:", inspected)
        if not inspected.get("success"):
            return False

        print_summary("PAINT", inspected)

        # Safe interaction: select Pencil instead of opening Save/Share dialogs.
        print("PAINT: invoke Pencil")
        invoked = tool.invoke_control(
            target_id=target_id,
            control_type="Button",
            text="Pencil",
        )
        print("INVOKE:", invoked)

        print("PAINT: close")
        closed = tool.close_window(target_id=target_id, confirm=True)
        print("CLOSE:", closed)

        if not closed.get("success"):
            print("CLOSE FALLBACK: invoke title-bar Close button")
            fallback = tool.invoke_control(
                target_id=target_id,
                control_type="Button",
                text="Close",
            )
            print("CLOSE FALLBACK:", fallback)
            time.sleep(0.8)

            closed = {
                "success": not tool.window_exists(
                    int((opened.get("target") or {}).get("hwnd") or 0)
                )
            }
            print("CLOSE VERIFY:", closed)

        return bool(closed.get("success"))

    except Exception as exc:
        print("PAINT EXCEPTION:", type(exc).__name__, exc)
        try:
            tool.close_window(target_id=target_id, confirm=True)
        except Exception:
            pass
        return False


def run_task_manager(tool):
    print("")
    print("=== REAL APP: TASK MANAGER ===")

    opened = tool.open_app(
        "taskmgr.exe",
        wait_seconds=2.0,
        process_hint="Taskmgr.exe",
        title_hint="Task Manager|إدارة المهام",
        require_new_window=True,
    )
    print("OPEN:", opened)

    if not opened.get("success"):
        return False

    target_id = str((opened.get("target") or {}).get("target_id") or "")
    try:
        inspected = tool.inspect(target_id=target_id, max_controls=400)
        print("INSPECT:", inspected)
        if not inspected.get("success"):
            return False

        print_summary("TASK MANAGER", inspected)

        # Verify the generic inspection registry can expose actual controls
        # from a complex Windows app.
        controls = inspected.get("controls") or []
        usable = [
            c for c in controls
            if c.get("name") or c.get("automation_id") or c.get("value")
        ]
        print("TASK MANAGER USABLE CONTROLS:", len(usable))

        print("TASK MANAGER: close")
        closed = tool.close_window(target_id=target_id, confirm=True)
        print("CLOSE:", closed)

        if not closed.get("success"):
            print("CLOSE FALLBACK: invoke title-bar Close button")
            fallback = tool.invoke_control(
                target_id=target_id,
                control_type="Button",
                text="Close",
            )
            print("CLOSE FALLBACK:", fallback)
            time.sleep(0.8)

            closed = {
                "success": not tool.window_exists(
                    int((opened.get("target") or {}).get("hwnd") or 0)
                )
            }
            print("CLOSE VERIFY:", closed)

        return bool(closed.get("success"))

    except Exception as exc:
        print("TASK MANAGER EXCEPTION:", type(exc).__name__, exc)
        try:
            tool.close_window(target_id=target_id, confirm=True)
        except Exception:
            pass
        return False


def main():
    if os.name != "nt":
        print("REAL APP TEST REQUIRES WINDOWS")
        return 2

    tool = LocalComputerTool()
    results = {
        "notepad": run_notepad(tool),
        "paint": run_paint(tool),
        "task_manager": run_task_manager(tool),
    }

    print("")
    print("========================================")
    print(" REAL WINDOWS APPS SMOKE SUMMARY")
    print("========================================")
    for name, ok in results.items():
        print(f"{name.upper()}: {'PASS' if ok else 'FAIL'}")

    if all(results.values()):
        print("")
        print("KAREEM_AGENT REAL WINDOWS APPS SMOKE: PASS")
        return 0

    print("")
    print("KAREEM_AGENT REAL WINDOWS APPS SMOKE: PARTIAL/FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

