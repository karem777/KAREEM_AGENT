import json
import re
from typing import Any

from brain.complete_brain import CompleteBrain


class CompletePlanner:
    """State-first planner with hard local-Windows routing."""

    def __init__(self, brain=None):
        self.brain = brain or CompleteBrain()

    @staticmethod
    def _ok(result):
        return isinstance(result, dict) and result.get("success") is not False

    @staticmethod
    def _extract_text(goal_text):
        text = str(goal_text or "")

        patterns = [
            r'[\"“](.+?)[\"”]',
            r"'(.+?)'",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for value in matches:
                value = str(value).strip()
                if value and len(value) >= 3 and not value.lower().endswith(".txt"):
                    return value

        return ""

    @staticmethod
    def _extract_filename(goal_text):
        text = str(goal_text or "")
        match = re.search(r'([A-Za-z0-9_\-]+\.txt)\b', text, re.I)
        return match.group(1) if match else ""

    def _windows_route(self, goal, history):
        domain = str(goal.get("domain", "")).strip().lower()
        goal_text = str(goal.get("goal", ""))

        if domain not in {"windows", "desktop", "local", "system"}:
            return None

        recent = [x for x in history if isinstance(x, dict)]
        computer = [x for x in recent if x.get("tool") == "computer" and self._ok(x.get("result") or {})]
        filesystem = [x for x in recent if x.get("tool") == "filesystem" and self._ok(x.get("result") or {})]

        target_app = ""
        for t in goal.get("targets", []) or []:
            t = str(t or "").strip()
            if t and t.lower() not in {"desktop", "سطح المكتب"}:
                target_app = t
                break

        low = goal_text.lower()

        # Strong local routing: never send an explicit Windows task to browser.
        if not computer:
            return {
                "type": "tool_call",
                "tool": "computer",
                "action": "inspect",
                "arguments": {},
                "reason": "This is a Windows/local-computer task. Inspect the real desktop first.",
                "expected": "Current local Windows UI and windows.",
            }

        has_launch = any(x.get("action") == "launch" for x in computer)
        if target_app and ("open" in low or "افتح" in goal_text or "تشغيل" in goal_text) and not has_launch:
            return {
                "type": "tool_call",
                "tool": "computer",
                "action": "launch",
                "arguments": {"app": target_app},
                "reason": "Open the requested local application before interacting with it.",
                "expected": f"{target_app} is open.",
            }

        wants_text = any(
            k in low or k in goal_text
            for k in ["write", "type", "اكتب", "اكتب", "اكتب داخل"]
        )

        text_value = self._extract_text(goal_text)

        has_set_text = any(
            x.get("action") in {"set_text", "type_text"}
            for x in computer
        )

        if wants_text and text_value and not has_set_text:
            title_re = ".*Notepad.*"
            if target_app and "notepad" not in target_app.lower():
                title_re = re.escape(target_app) + ".*"

            return {
                "type": "tool_call",
                "tool": "computer",
                "action": "set_text",
                "arguments": {
                    "text": text_value,
                    "title_re": title_re,
                    "control_type": "Edit",
                },
                "reason": "Write the requested content into the local application using UI Automation.",
                "expected": "The requested text is present in the application.",
            }

        wants_save = any(
            k in low or k in goal_text
            for k in ["save", "احفظ", "حفظ", "باسم"]
        )

        filename = self._extract_filename(goal_text)

        has_saved = any(
            x.get("action") == "save_file"
            for x in computer
        )

        if wants_save and filename and not has_saved:
            return {
                "type": "tool_call",
                "tool": "computer",
                "action": "save_file",
                "arguments": {
                    "filename": filename,
                },
                "reason": "Save the local application's current content using its native Save dialog.",
                "expected": f"The file {filename} has been saved.",
            }

        # Verify the requested file through the local filesystem.
        if wants_save and filename and not filesystem:
            return {
                "type": "tool_call",
                "tool": "filesystem",
                "action": "read_file",
                "arguments": {
                    "path": f"desktop/{filename}",
                },
                "reason": "Verify the file exists locally and contains the requested content.",
                "expected": "The saved file exists and can be read.",
            }

        return None

    def plan(
        self,
        goal: dict[str, Any],
        world: dict[str, Any],
        history: list[dict[str, Any]],
        tools: dict[str, Any],
        recovery: dict[str, Any] | None = None,
        experiences: list[dict[str, Any]] | None = None,
    ):
        routed = self._windows_route(goal, history)
        if routed:
            return routed

        recent = history[-6:]
        prompt = f'''
You are KAREEM_AGENT COMPLETE, an autonomous local agent using Qwen3:8b.
You operate a real Windows machine and a real Chrome session.
Return JSON only.

Choose the NEXT useful action based on verified state.

IMPORTANT:
- Windows/local/desktop goals MUST use the "computer" tool.
- Never use "browser" for a Windows application task.
- Never click a browser page merely because browser state exists.
- Use computer.inspect before guessing a local UI.
- Use computer.launch to open local applications.
- Use computer.set_text / click / hotkey / press for local UI.
- Use filesystem to verify local files.
- Never declare completion without evidence.
- For system changes, respect approval_required responses.

GOAL:
{json.dumps(goal, ensure_ascii=False)}

WORLD:
{json.dumps(world, ensure_ascii=False)}

RECENT HISTORY:
{json.dumps(recent, ensure_ascii=False)}

RECOVERY:
{json.dumps(recovery or {}, ensure_ascii=False)}

EXPERIENCES:
{json.dumps(experiences or [], ensure_ascii=False)}

TOOLS:
{json.dumps(tools, ensure_ascii=False)}

Output exactly one JSON object:
{{"type":"tool_call","tool":"...","action":"...","arguments":{{...}},"reason":"...","expected":"..."}}
or
{{"type":"finish","answer":"...","evidence":[...]}}
or
{{"type":"ask_user","question":"..."}}
'''

        fallback = {
            "type": "tool_call",
            "tool": "computer",
            "action": "inspect",
            "arguments": {},
            "reason": "Refresh local machine state.",
            "expected": "Fresh Windows UI state.",
        }

        return self.brain.json(prompt, fallback=fallback)
