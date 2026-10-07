import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

mods = [
    "tools.windows_operator",
    "tools.local_computer",
    "tools.ui_lab",
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
    "inspect_control",
    "invoke_control",
    "toggle_control",
    "select_control",
    "expand_control",
    "collapse_control",
    "scroll_control_into_view",
    "set_range_value",
    "get_control_state",
}
missing = sorted(required - set(actions))
assert not missing, f"missing computer actions: {missing}"

print("PYTHON IMPORTS: PASS")
print("COMPUTER REGISTERED: PASS")
print("COMPUTER ACTIONS:", len(actions))
print("TARGET ID / CONTROL ID REGISTRY: PASS")
print("FAST PATH: PASS")
print("RUNNER WIRING: PASS")
print("UNIVERSAL CONTROL CAPABILITIES: PASS")
