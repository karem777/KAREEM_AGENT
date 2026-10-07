from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.local_computer import LocalComputerTool


def wait_for_pass(tool, target_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        probe = tool.inspect_control(target_id=target_id, control_type="Text", text="PASS")
        if probe.get("success"):
            return True
        time.sleep(0.15)
    return False


def main() -> int:
    if os.name != "nt":
        print("LIVE SELF-TEST REQUIRES WINDOWS")
        return 2

    os.environ["KAREEM_EXECUTION_MODE"] = "visible"
    tool = LocalComputerTool()
    lab = ROOT / "tools" / "ui_lab.py"
    target_id = ""

    try:
        print("SELFTEST: launch KAREEM UI LAB")
        opened = tool.open_app(
            sys.executable,
            args=[str(lab)],
            wait_seconds=5.0,
            process_hint="python.exe",
            title_hint="KAREEM UI LAB",
            require_new_window=True,
        )
        print("OPENED:", opened)
        if not opened.get("success"):
            return 10

        target_id = str((opened.get("target") or {}).get("target_id") or "")
        if not target_id:
            return 11

        print("SELFTEST: inspect universal control tree")
        inspected = tool.inspect(target_id=target_id, max_controls=250)
        print("INSPECTED:", inspected)
        if not inspected.get("success"):
            return 12

        print("SELFTEST: set generic Edit/Entry")
        typed = tool.set_text("KAREEM_UNIVERSAL_OK", target_id=target_id, control_type="Edit", index=0, replace=True, verify=True)
        print("EDIT:", typed)
        if not typed.get("success"):
            return 13

        print("SELFTEST: toggle CheckBox")
        toggled = tool.toggle_control(target_id=target_id, control_type="CheckBox", index=0, desired=True)
        print("CHECKBOX:", toggled)
        if not toggled.get("success"):
            return 14

        print("SELFTEST: select ComboBox")
        selected_combo = tool.select_control(target_id=target_id, control_type="ComboBox", index=0, item="Expert")
        print("COMBO:", selected_combo)
        if not selected_combo.get("success"):
            return 15

        print("SELFTEST: select RadioButton")
        selected_radio = tool.select_control(target_id=target_id, control_type="RadioButton", index=1)
        print("RADIO:", selected_radio)
        if not selected_radio.get("success"):
            return 16

        print("SELFTEST: select ListItem")
        selected_item = tool.select_control(target_id=target_id, control_type="ListItem", text="Gamma")
        print("LIST:", selected_item)
        if not selected_item.get("success"):
            return 17

        print("SELFTEST: switch Tab")
        selected_tab = tool.select_control(target_id=target_id, control_type="TabItem", text="Advanced")
        print("TAB:", selected_tab)
        if not selected_tab.get("success"):
            return 18

        print("SELFTEST: set RangeValue/Slider")
        slider = tool.set_range_value(75, target_id=target_id, control_type="Slider", index=0)
        print("SLIDER:", slider)
        if not slider.get("success"):
            return 19

        print("SELFTEST: return to Basic tab")
        basic_tab = tool.select_control(target_id=target_id, control_type="TabItem", text="Basic")
        print("TAB BASIC:", basic_tab)
        if not basic_tab.get("success"):
            return 20

        print("SELFTEST: invoke universal test button")
        invoked = tool.invoke_control(target_id=target_id, control_type="Button", text="Run Universal Test")
        print("BUTTON:", invoked)
        if not invoked.get("success"):
            return 21

        if not wait_for_pass(tool, target_id, timeout=5.0):
            print("FAIL: UI Lab did not report PASS")
            tool.inspect(target_id=target_id, max_controls=250)
            return 22

        print("")
        print("KAREEM_AGENT WINDOWS UNIVERSAL SELF-TEST: PASS")
        print("Target binding: PASS")
        print("Invoke: PASS")
        print("Text/Value: PASS")
        print("Toggle: PASS")
        print("SelectionItem: PASS")
        print("RangeValue: PASS")
        print("Tab selection: PASS")
        print("Capability-driven control model: PASS")
        return 0

    finally:
        if target_id:
            try:
                tool.close_window(target_id=target_id, confirm=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())



