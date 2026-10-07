from pathlib import Path
import re

path = Path(r".\core\complete_runner.py")

text = path.read_text(
    encoding="utf-8"
)

# ------------------------------------------------------------
# Fast path is OFF by default.
# ------------------------------------------------------------

text = text.replace(
    'os.getenv("KAREEM_FAST_MODE", "1")',
    'os.getenv("KAREEM_FAST_MODE", "0")',
    1,
)

# ------------------------------------------------------------
# Canonical tool aliases.
# ------------------------------------------------------------

old = """    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
        tool = self.registry.get(tool_name)
"""

new = """    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
        aliases = {
            "desktop": "computer",
            "pc": "computer",
            "windows_operator": "computer",
            "computer_tool": "computer",
        }

        raw_name = str(
            tool_name or ""
        ).strip()

        tool_name = aliases.get(
            raw_name.lower(),
            raw_name,
        )

        tool = self.registry.get(
            tool_name
        )
"""

if old not in text:
    raise RuntimeError(
        "Runner execute block not found"
    )

text = text.replace(
    old,
    new,
    1,
)

# ------------------------------------------------------------
# Replace perception helper with a dual browser/computer version.
# ------------------------------------------------------------

pattern = re.compile(
    r"    def _inspect_after\(.*?\n"
    r"    def _world_from_result",
    re.S,
)

replacement = """    def _inspect_after(
        self,
        tool: str,
        action: str,
        result: dict[str, Any],
        force=False,
    ):
        if not self._ok(result):
            return result

        # ----------------------------
        # Browser perception
        # ----------------------------

        if tool == "browser":

            if action == "inspect":
                return result

            browser = self.registry.get(
                "browser"
            )

            inspect = (
                getattr(
                    browser,
                    "inspect",
                    None,
                )
                if browser
                else None
            )

            if not callable(inspect):
                return result

            needs = force or action in {
                "click",
                "fill",
                "press_key",
                "navigate",
                "open_url",
                "type_text",
            }

            if not needs:
                self.world.observe(
                    result
                )
                return result

            try:
                perception = inspect()

                self.world.observe(
                    perception
                )

                return {
                    "action_result": result,
                    "auto_perception": perception,
                    "success": True,
                }

            except Exception:
                self.world.observe(
                    result
                )
                return result

        # ----------------------------
        # Native Windows perception
        # ----------------------------

        if tool == "computer":

            computer = self.registry.get(
                "computer"
            )

            inspect = (
                getattr(
                    computer,
                    "inspect",
                    None,
                )
                if computer
                else None
            )

            if not callable(inspect):
                return result

            needs = force or action in {
                "open_app",
                "click",
                "double_click",
                "click_control",
                "set_text",
                "type_text",
                "hotkey",
                "press",
                "invoke_control",
                "toggle_control",
                "select_control",
                "expand_control",
                "collapse_control",
                "close_window",
                "set_range_value",
            }

            if not needs:
                return result

            try:
                perception = inspect()

                return {
                    "action_result": result,
                    "auto_perception": perception,
                    "success": True,
                }

            except TypeError:
                return result

            except Exception:
                return result

        return result

    def _world_from_result"""

text, count = pattern.subn(
    replacement,
    text,
    count=1,
)

if count != 1:
    raise RuntimeError(
        "Runner perception block not found"
    )

# ------------------------------------------------------------
# Store computer observations in world facts.
# ------------------------------------------------------------

old_world = """        if tool == "browser":
            self.world.observe(result)
        elif tool == "windows" and self._ok(result):
"""

new_world = """        if tool == "browser":
            self.world.observe(result)

        elif tool == "computer" and self._ok(result):
            self.world.state.facts[
                "computer_last"
            ] = result

            target = (
                result.get("target")
                if isinstance(result, dict)
                else None
            )

            if isinstance(
                target,
                dict,
            ) and target.get(
                "target_id"
            ):
                self.world.state.facts[
                    "computer_target"
                ] = target

        elif tool == "windows" and self._ok(result):
"""

if old_world not in text:
    raise RuntimeError(
        "Runner world block not found"
    )

text = text.replace(
    old_world,
    new_world,
    1,
)

# ------------------------------------------------------------
# IMPORTANT:
# Main cognitive loop must NOT auto-finish from keyword rules.
#
# The planner decides when to call finish_task.
# ------------------------------------------------------------

old_success = """            if self._ok(result):
                deterministic, reason = self._deterministic_completion(contract, history)
                if deterministic:
                    return self._finish(task_id, user_message, step, "تم تنفيذ الطلب بنجاح.", history, reason)
                if self.verify_every_action:
                    done, reason, missing = self._verifier(contract, self.world, history)
                    if done:
                        return self._finish(task_id, user_message, step, "تم تنفيذ الطلب بنجاح.", history, reason)
                    recovery = {"type": "continue", "missing": missing}
                else:
                    recovery = {"type": "continue", "missing": ["continue toward goal"]}
"""

new_success = """            if self._ok(result):

                if self.verify_every_action:
                    done, reason, missing = self._verifier(
                        contract,
                        self.world,
                        history,
                    )

                    if done:
                        return self._finish(
                            task_id,
                            user_message,
                            step,
                            "تم تنفيذ الطلب بنجاح.",
                            history,
                            reason,
                        )

                    recovery = {
                        "type": "continue",
                        "missing": missing,
                    }

                else:
                    recovery = {
                        "type": "continue",
                        "last_successful_action": {
                            "tool": tool,
                            "action": action,
                        },
                        "message": (
                            "The action succeeded. "
                            "Observe the new state and "
                            "choose the next action."
                        ),
                    }
"""

if old_success not in text:
    raise RuntimeError(
        "Runner success block not found"
    )

text = text.replace(
    old_success,
    new_success,
    1,
)

path.write_text(
    text,
    encoding="utf-8",
)

print(
    "CompleteRunner patched successfully."
)
