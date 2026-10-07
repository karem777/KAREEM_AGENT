from __future__ import annotations

import json
import re
from typing import Any

from core.browser_goal import BrowserGoalController


class Planner:
    """Universal action planner backed by the new perception/reasoning runtime."""

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

    @staticmethod
    def _best_web_result(goal: dict[str, Any], result: dict[str, Any]) -> str | None:
        results = result.get("results") if isinstance(result, dict) else None
        if not isinstance(results, list):
            return None
        site = str(goal.get("site") or "").casefold()
        country = str(goal.get("country") or "").casefold()
        ranked = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").casefold()
            url = str(item.get("url") or "")
            score = 0
            if site and site in title + " " + url.casefold():
                score += 10
            if country and any(x in title + " " + url.casefold() for x in ["saudi", "ksa", "arabia", "السعود"]):
                score += 5
            if url.startswith(("https://", "http://")):
                score += 1
            ranked.append((score, url))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None

    def _deterministic_cognitive(self, cognition: dict[str, Any] | None, history: list[dict[str, Any]]) -> dict | None:
        if not cognition:
            return None
        goal = cognition.get("goal") or {}
        state = cognition.get("state") or {}
        page = cognition.get("page") or {}

        if state.get("complete"):
            return {"type": "chat", "content": "__VERIFIED_COMPLETE__"}

        # Resolve site/region through the generic web tool rather than site-specific hardcoding.
        if page.get("llm") is None and not page.get("url") and goal.get("site") and not goal.get("start_url"):
            return {
                "type": "tool_call", "tool": "web", "action": "search",
                "arguments": {"query": f"{goal.get('site')} official {goal.get('country') or ''} website".strip(), "max_results": 5},
            }

        last_tool = next((h for h in reversed(history) if h.get("role") == "tool"), None)
        if last_tool and last_tool.get("tool") == "web" and last_tool.get("action") == "search":
            result = last_tool.get("result") or {}
            url = self._best_web_result(goal, result)
            if url:
                return {"type": "tool_call", "tool": "browser", "action": "open_url", "arguments": {"url": url}}

        hints = cognition.get("hints") or []
        if hints:
            return {"type": "tool_call", **self._normalize(hints[0])}
        return None

    def plan(self, user_message: str, history: list[dict] | None = None, tools: dict | None = None, memory: list[dict] | None = None,
             knowledge: list[dict] | None = None, cognition: dict[str, Any] | None = None,
             analysis: dict[str, Any] | None = None, goal_state: Any = None, **_: Any) -> dict:
        history = history or []
        tools = tools or {}
        if goal_state is not None:
            try:
                if hasattr(goal_state, "ready_steps"):
                    ready = goal_state.ready_steps()
                else:
                    steps = getattr(goal_state, "steps", []) or []
                    by_id = {s.get("id"): s for s in steps if isinstance(s, dict)}
                    ready = []
                    for s in steps:
                        if not isinstance(s, dict) or s.get("status") != "pending":
                            continue
                        deps = s.get("depends_on", []) or []
                        if all(by_id.get(d, {}).get("status") == "done" for d in deps):
                            ready.append(s)
                if ready:
                    step = ready[0]
                    call = {"tool": step.get("tool"), "action": step.get("action"), "arguments": step.get("arguments") or {}}
                    if analysis is not None:
                        return {"type": "tool_calls", "calls": [call]}
                    return {"type": "tool_call", **call}
            except Exception:
                pass
        deterministic = self._deterministic_cognitive(cognition, history)
        if deterministic:
            return deterministic

        deterministic_browser = self.browser_controller.next_action(user_message, history)
        if deterministic_browser:
            if deterministic_browser.get("type") == "chat":
                return {"type": "chat", "content": str(deterministic_browser.get("content") or "")}
            return {
                "type": "tool_call",
                "tool": deterministic_browser["tool"],
                "action": deterministic_browser["action"],
                "arguments": deterministic_browser.get("arguments") or {},
            }

        tool_schema = json.dumps(tools, ensure_ascii=False, default=str)
        recent = json.dumps(history[-10:], ensure_ascii=False, default=str)
        mem = json.dumps((memory or [])[-6:], ensure_ascii=False, default=str)
        know = json.dumps((knowledge or [])[-6:], ensure_ascii=False, default=str)
        cog = json.dumps(cognition or {}, ensure_ascii=False, default=str)
        prompt = f"""
You are KAREEM_AGENT V5, the action-selection layer of a universal local agent.
The agent does NOT blindly follow a fixed A->B script. It repeatedly observes the current
world, interprets it, compares it with the user's goal, and chooses one next action.

RETURN EXACTLY ONE JSON OBJECT:
{{"type":"tool_call","tool":"...","action":"...","arguments":{{...}}}}
or
{{"type":"chat","content":"..."}}

NON-NEGOTIABLE RULES:
1. Treat CURRENT PERCEPTION and CURRENT STATE as the truth about what is visible now.
2. Before clicking, use a currently observed element. Never invent a UID, URL, price, or field.
3. Search queries contain only the semantic query; output constraints (price, count, fields) are NOT pasted into the search box.
4. A completion claim is forbidden unless CURRENT STATE.complete is true.
5. When country/currency is mismatched or unknown, fix the context before collecting results.
6. When a web search result is available for site/region resolution, open the best matching official result.
7. When a step fails, change strategy or collect more evidence. Never repeat the same failed action verbatim.
8. For website tasks, use browser for interaction; use web only for public research or resolving an unknown target URL.
9. Return one action at a time when the next choice depends on the observation.
10. Never bypass MFA/CAPTCHA/security controls.

USER GOAL:
{user_message}

COGNITIVE STATE:
{cog}

AVAILABLE TOOLS:
{tool_schema}

RECENT HISTORY:
{recent}

MEMORY:
{mem}

KNOWLEDGE:
{know}
""".strip()

        if self.brain is None:
            return {"type": "chat", "content": "العقل المحلي غير متاح."}
        try:
            raw = self.brain.ask(prompt)
            text = str(raw or "").strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text).strip()
            try:
                data = json.loads(text)
            except Exception:
                start, end = text.find("{"), text.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(text[start:end + 1])
                else:
                    return {"type": "chat", "content": "تعذر فهم قرار التنفيذ من العقل المحلي."}
        except Exception as exc:
            return {"type": "chat", "content": f"تعذر تشغيل طبقة التخطيط: {exc}"}

        if not isinstance(data, dict):
            return {"type": "chat", "content": "تعذر فهم قرار التنفيذ."}
        if str(data.get("type") or "").lower() == "chat":
            return {"type": "chat", "content": str(data.get("content") or "")}
        call = self._normalize(data.get("call") or data)
        if call:
            return {"type": "tool_call", **call}
        return {"type": "chat", "content": "تعذر تحويل القرار إلى أداة قابلة للتنفيذ."}
