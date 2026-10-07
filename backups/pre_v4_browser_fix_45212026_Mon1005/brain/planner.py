from __future__ import annotations

import json
import re

from core.browser_goal import BrowserGoalController


class Planner:
    """Universal planner with deterministic state guardrails plus LLM reasoning."""

    TOOL_ALIASES = {
        "computer": "desktop", "pc": "desktop", "windows": "desktop",
        "file": "filesystem", "files": "filesystem", "fs": "filesystem",
        "memory_tool": "memory", "web_tool": "web", "browser_tool": "browser",
        "code": "engineering", "coder": "engineering", "programming": "engineering",
        "selfrepair": "repair", "debug": "repair", "diagnostics": "security",
    }
    ACTION_ALIASES = {
        "open": "open_url", "navigate": "open_url", "inspect_page": "inspect",
        "type": "type_text", "key": "press_key", "mkdir": "create_directory",
        "create_folder": "create_directory", "create_file": "write_file", "read": "read_file",
        "ls": "list_directory", "run_test": "run_tests", "test": "run_tests",
        "learn": "learn_site", "teach_site": "learn_site",
    }

    def __init__(self, brain=None):
        if brain is None:
            try:
                from brain.local_brain import LocalBrain
                brain = LocalBrain()
            except Exception:
                brain = None
        self.brain = brain
        self.browser_controller = BrowserGoalController()

    def _normalize(self, call: dict) -> dict | None:
        if not isinstance(call, dict):
            return None
        tool = str(call.get("tool") or "").strip()
        action = str(call.get("action") or "").strip()
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        if "." in tool and not action:
            tool, action = tool.split(".", 1)
        tool = self.TOOL_ALIASES.get(tool.lower(), tool)
        action = self.ACTION_ALIASES.get(action.lower(), action)
        return {"tool": tool, "action": action, "arguments": args} if tool and action else None

    def _deterministic_browser_plan(self, user_message: str, history: list[dict]) -> dict | None:
        """Handle generic search->first-result chains deterministically.

        The controller is intentionally independent of individual shopping or
        social sites. It only enforces the logical preconditions between browser
        actions, preventing accidental clicks before a search exists.
        """
        action = self.browser_controller.next_action(user_message, history)
        if not action:
            return None
        if action.get("type") == "chat":
            return {"type": "chat", "content": str(action.get("content") or "")}
        return {
            "type": "tool_call",
            "tool": action["tool"],
            "action": action["action"],
            "arguments": action.get("arguments") or {},
        }

    def plan(self, user_message: str, history: list[dict], tools: dict, memory: list[dict] | None = None, knowledge: list[dict] | None = None) -> dict:
        deterministic = self._deterministic_browser_plan(user_message, history)
        if deterministic:
            return deterministic

        tool_schema = json.dumps(tools, ensure_ascii=False, default=str)
        recent = json.dumps(history[-8:], ensure_ascii=False, default=str)
        mem = json.dumps((memory or [])[-8:], ensure_ascii=False, default=str)
        know = json.dumps((knowledge or [])[-8:], ensure_ascii=False, default=str)
        prompt = f"""
You are KAREEM_AGENT V4, a universal local execution agent.
You solve arbitrary web, Windows, programming, debugging, learning, and defensive cybersecurity tasks.

RETURN CONTRACT:
- Return EXACTLY ONE valid JSON object.
- Either {{"type":"tool_call","tool":"...","action":"...","arguments":{{...}}}}
  or {{"type":"chat","content":"..."}}.
- Never output markdown, comments, multiple JSON objects, or explanatory text outside the object.

EXECUTION RULES:
1) Use ONE tool action per turn when the next action depends on the observation.
2) Treat every tool result as ground truth about the current state.
3) Never invent page contents, files, prices, URLs, or successful actions.
4) Before a browser click, inspect the current page when the target is not already proven.
5) Never interpret a generic phrase like "first result" as "first link on the page". It means the first result of the user's requested search/query context.
6) Never click a result before a search has actually been submitted and the resulting page has been observed.
7) If an action fails, diagnose the exact error and change strategy instead of repeating blindly.
8) For visible website interaction, use browser. Use web for public research when direct browser interaction is unnecessary.
9) For coding, prefer inspect -> change -> test -> verify. For Windows, collect evidence before changing state.
10) Do not bypass CAPTCHA/MFA/security controls.
11) Keep high-risk Registry/service/firewall/driver/system changes behind approval boundaries.
12) Learned knowledge is guidance, not proof; verify current state before acting.
13) Do not claim completion until the user's goal is proven by an observation.

USER GOAL:
{user_message}

AVAILABLE TOOLS:
{tool_schema}

RECENT HISTORY:
{recent}

RELEVANT MEMORY:
{mem}

LEARNED KNOWLEDGE:
{know}
""".strip()

        if self.brain is None:
            return {"type": "chat", "content": "العقل المحلي غير متاح."}

        raw = self.brain.ask(prompt)
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()
        try:
            data = json.loads(text)
        except Exception:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end + 1])
                except Exception:
                    return {"type": "chat", "content": "تعذر فهم خطة التنفيذ من العقل المحلي."}
            else:
                return {"type": "chat", "content": "تعذر فهم خطة التنفيذ من العقل المحلي."}

        if not isinstance(data, dict):
            return {"type": "chat", "content": "تعذر فهم خطة التنفيذ من العقل المحلي."}
        if str(data.get("type") or "").lower() == "chat":
            return {"type": "chat", "content": str(data.get("content") or "")}
        call = self._normalize(data.get("call") or data)
        if call:
            return {"type": "tool_call", **call}
        calls = data.get("calls") or data.get("tool_calls") or []
        if calls:
            c = self._normalize(calls[0])
            if c:
                return {"type": "tool_call", **c}
        return {"type": "chat", "content": "تعذر تحويل قرار العقل المحلي إلى أداة قابلة للتنفيذ."}
