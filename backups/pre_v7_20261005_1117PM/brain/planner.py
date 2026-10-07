from __future__ import annotations

import json
import re
from typing import Any

from core.browser_goal import BrowserGoalController
from core.handoff import ToolHandoffRouter


class Planner:
    """Goal-aware action selector with explicit discovery->browser handoff."""

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
        rows = result.get("results") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            return None
        site = str(goal.get("site") or "").casefold()
        country = str(goal.get("country") or "").casefold()
        ranked: list[tuple[int, str]] = []
        country_tokens = {
            "saudi arabia": ["saudi", "ksa", "arabia", "السعود"],
            "united arab emirates": ["uae", "emirates", "dubai", "الإمارات", "الامارات"],
            "egypt": ["egypt", "مصر", "egyp"],
        }.get(country, [country] if country else [])
        for item in rows:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").casefold()
            url = str(item.get("url") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue
            hay = title + " " + url.casefold()
            score = 0
            if site and site in hay:
                score += 20
            if any(t and t in hay for t in country_tokens):
                score += 12
            if country == "saudi arabia" and "saudi-en" in hay:
                score += 8
            if country == "united arab emirates" and "uae-en" in hay:
                score += 8
            if "login" in url or "/help" in url:
                score -= 8
            ranked.append((score, url))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None

    def _deterministic_cognitive(self, cognition: dict[str, Any] | None, history: list[dict[str, Any]]) -> dict | None:
        if not cognition:
            return None
        goal = cognition.get("goal") or {}
        state = cognition.get("state") or {}
        page = cognition.get("page") or {}
        handoff = ToolHandoffRouter(goal, history)

        if state.get("complete"):
            return {"type": "chat", "content": "__VERIFIED_COMPLETE__"}

        # CRITICAL: a successful web discovery must hand off to the browser BEFORE
        # considering another discovery search. This prevents the V5 search loop.
        handoff_url = handoff.discovery_handoff()
        if handoff_url and not self._same_url_already_opened(history, handoff_url):
            return {
                "type": "tool_call",
                "tool": "browser",
                "action": "open_url",
                "arguments": {"url": handoff_url},
            }

        # Start discovery only once when no browser/page exists yet.
        if not page.get("url") and goal.get("site") and not goal.get("start_url"):
            if not handoff.searched_same_query():
                return {
                    "type": "tool_call", "tool": "web", "action": "search",
                    "arguments": {"query": f"{goal.get('site')} official {goal.get('country') or ''} website".strip(), "max_results": 5},
                }
            # Search already succeeded but its result was somehow not usable.
            return {
                "type": "tool_call", "tool": "browser", "action": "inspect", "arguments": {},
            }

        hints = cognition.get("hints") or []
        if hints:
            hint = self._normalize(hints[0])
            if hint:
                return {"type": "tool_call", **hint}
        return None

    @staticmethod
    def _same_url_already_opened(history: list[dict[str, Any]], url: str) -> bool:
        target = str(url or "").rstrip("/").casefold()
        for h in history:
            if h.get("role") != "tool" or h.get("tool") != "browser" or h.get("action") != "open_url":
                continue
            args = h.get("arguments") or {}
            opened = str(args.get("url") or "").rstrip("/").casefold()
            if opened == target:
                return True
        return False

    def plan(self, user_message: str, history: list[dict] | None = None, tools: dict | None = None, memory: list[dict] | None = None,
             knowledge: list[dict] | None = None, cognition: dict[str, Any] | None = None,
             analysis: dict[str, Any] | None = None, goal_state: Any = None, **_: Any) -> dict:
        history = history or []
        tools = tools or {}

        # Legacy deterministic GoalState remains compatible for callers that explicitly
        # provide it without the V6 cognition context. Once cognition exists, V6
        # perception/state selection has authority so stale DAGs cannot force loops.
        if goal_state is not None and cognition is None:
            try:
                if hasattr(goal_state, "ready_steps"):
                    ready = goal_state.ready_steps()
                else:
                    steps = getattr(goal_state, "steps", []) or []
                    by_id = {s.get("id"): s for s in steps if isinstance(s, dict)}
                    ready = []
                    for step in steps:
                        if not isinstance(step, dict) or step.get("status") != "pending":
                            continue
                        deps = step.get("depends_on", []) or []
                        if all(by_id.get(dep, {}).get("status") == "done" for dep in deps):
                            ready.append(step)
                if ready:
                    step = ready[0]
                    call = {
                        "tool": step.get("tool"),
                        "action": step.get("action"),
                        "arguments": step.get("arguments") or {},
                    }
                    return {"type": "tool_calls", "calls": [call]}
            except Exception:
                pass

        deterministic = self._deterministic_cognitive(cognition, history)
        if deterministic:
            return deterministic

        # Legacy BrowserGoalController is retained as a fallback for simple goals,
        # but it never overrides the perception/state machine above.
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
        recent = json.dumps(history[-12:], ensure_ascii=False, default=str)
        mem = json.dumps((memory or [])[-6:], ensure_ascii=False, default=str)
        know = json.dumps((knowledge or [])[-6:], ensure_ascii=False, default=str)
        cog = json.dumps(cognition or {}, ensure_ascii=False, default=str)
        prompt = f"""
You are KAREEM_AGENT V6, a universal action-selection and world-state reasoning layer.
You are NOT a fixed A->B script executor.
Every action must be chosen from CURRENT PERCEPTION and CURRENT STATE.

RETURN EXACTLY ONE JSON OBJECT:
{{"type":"tool_call","tool":"...","action":"...","arguments":{{...}}}}
or
{{"type":"chat","content":"..."}}

CORE RULES:
1. Goal constraints are separate from semantic search queries.
2. If web.search just returned a usable target URL, HAND OFF to browser.open_url; never repeat the same discovery search.
3. Browser is the interaction executor for websites. Web is for public research/discovery, not page clicking.
4. After navigation or mutation, rely on the newest inspection/page state.
5. Do not invent UIDs, URLs, prices, products, or page states.
6. A completion claim is forbidden unless CURRENT STATE.complete is true.
7. A data-collection task is not complete until the requested fields and constraints have proof.
8. If state did not change after an action, change strategy rather than repeating the same call.
9. Never paste price/count/output constraints into a website search box.
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
