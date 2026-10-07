from __future__ import annotations

import json
import re
from typing import Any


class Planner:
    """Universal planner: no site-specific workflows; acts one observable step at a time."""

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

    def plan(self, user_message: str, history: list[dict], tools: dict, memory: list[dict] | None = None, knowledge: list[dict] | None = None) -> dict:
        tool_schema = json.dumps(tools, ensure_ascii=False, default=str)
        recent = json.dumps(history[-8:], ensure_ascii=False, default=str)
        mem = json.dumps((memory or [])[-8:], ensure_ascii=False, default=str)
        know = json.dumps((knowledge or [])[-8:], ensure_ascii=False, default=str)
        prompt = f"""
You are KAREEM_AGENT V4, a universal local execution agent.
You are NOT a site-specific macro. You must solve arbitrary web, Windows, programming,
debugging, learning, and defensive cybersecurity tasks by using tools dynamically.

RULES:
1) Return EXACTLY ONE JSON object.
2) Either {{"type":"tool_call","tool":"...","action":"...","arguments":{{...}}}} or {{"type":"chat","content":"..."}}.
3) Use ONE action per turn when the next action depends on the observation.
4) After an action, inspect/observe and adapt. Do not assume.
5) Never claim completion unless the evidence proves the user's goal is satisfied.
6) If an error occurs, diagnose the error and choose a recovery action; do not blindly repeat the same failed call.
7) For visible website interaction, prefer browser over web.
8) For reading public docs or facts without interaction, web is acceptable; for learning a site, use learning.learn_site.
9) For coding bugs, use engineering/repair tools: inspect -> identify -> patch -> test -> verify.
10) For Windows issues, use security diagnostics for evidence and system/desktop for approved changes.
11) Do not bypass CAPTCHA/MFA or security checks.
12) High-risk Registry/service/firewall/driver/system changes must stay behind the existing SystemTool approval boundary.
13) Learned knowledge may be used as guidance, but verify current state with tools before acting.

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
                    return {"type": "chat", "content": text}
            else:
                return {"type": "chat", "content": text}
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
        return {"type": "chat", "content": text}
