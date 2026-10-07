from __future__ import annotations

import json
import re
from typing import Any, Iterable


class Planner:
    """Deterministic-first planner with a capability-driven fallback brain."""

    TOOL_ALIASES = {
        "execute_browser_action": "browser",
        "browser_action": "browser",
        "filesystem_tool": "filesystem",
        "memory_tool": "memory",
        "computer": "desktop",
        "pc": "desktop",
        "windows": "desktop",
    }

    ACTION_ALIASES = {
        "navigate": "open_url",
        "navigate_url": "open_url",
        "open": "open_url",
        "inspect_page": "inspect",
        "inspect_current_page": "inspect",
        "type": "type_text",
        "input_text": "type_text",
        "key": "press_key",
    }

    def __init__(self, brain=None, local_brain=None):
        if brain is None and local_brain is not None:
            brain = local_brain
        if brain is None:
            try:
                from brain.local_brain import LocalBrain
                brain = LocalBrain()
            except Exception:
                brain = None
        self.brain = brain

    def plan(self, user_message: str = "", context: Any = None, analysis: Any = None, goal_state: Any = None, tools: Any = None, history: Any = None, **kwargs):
        deterministic = self._plan_from_goal_state(goal_state, analysis, context)
        if deterministic is not None:
            return deterministic
        deterministic = self._plan_from_analysis(analysis)
        if deterministic is not None:
            return deterministic

        if isinstance(analysis, dict) and str(analysis.get("mode", "")).lower() == "chat":
            answer = str(analysis.get("answer") or analysis.get("content") or "").strip()
            if answer:
                return {"type": "chat", "content": answer}

        if self.brain is None:
            return {"type": "chat", "content": "محتاج مخ التخطيط المحلي شغال علشان أقرر الخطوة التالية."}

        prompt = self._build_prompt(user_message, context, analysis, goal_state, tools, history)
        raw = self.brain.ask(prompt)
        parsed = self._parse_json(raw)
        if not parsed:
            return {"type": "chat", "content": str(raw or "").strip()}
        return self._normalize_plan(parsed)

    def _plan_from_goal_state(self, goal_state, analysis, context):
        if goal_state is None:
            return None
        ready = self._next_ready_step(goal_state)
        if ready is None:
            if self._goal_complete(goal_state):
                return {"type": "chat", "content": "تم تنفيذ الطلب بنجاح."}
            return None
        call = self._step_to_call(ready, analysis, context)
        return {"type": "tool_calls", "calls": [call]} if call else None

    def _plan_from_analysis(self, analysis):
        if not isinstance(analysis, dict):
            return None
        steps = analysis.get("steps") or []
        for step in steps:
            if not step or not step.get("required", True):
                continue
            if str(step.get("status", "")).lower() in {"done", "completed", "success", "succeeded"}:
                continue
            tool, action = self._normalize_tool_action(step.get("tool"), step.get("action"))
            if not tool or not action:
                continue
            args = dict(step.get("arguments") or {})
            return {"type": "tool_calls", "calls": [{"tool": tool, "action": action, "arguments": args}]}
        return None

    def _next_ready_step(self, goal_state):
        for name in ("next_ready_step", "get_next_ready_step", "next_step"):
            fn = getattr(goal_state, name, None)
            if callable(fn):
                try:
                    out = fn()
                except TypeError:
                    out = None
                if out is not None:
                    return self._coerce_step(out)
        ready = getattr(goal_state, "ready_steps", None)
        if callable(ready):
            try: ready = ready()
            except TypeError: ready = None
        if isinstance(ready, Iterable) and not isinstance(ready, (str, bytes, dict)):
            for x in ready:
                if self._coerce_step(x):
                    return self._coerce_step(x)
        steps = getattr(goal_state, "steps", None)
        if callable(steps):
            try: steps = steps()
            except TypeError: steps = None
        if isinstance(steps, dict):
            steps = list(steps.values())
        if not isinstance(steps, list):
            return None
        completed = self._completed_step_ids(goal_state, steps)
        for raw in steps:
            step = self._coerce_step(raw)
            if not step or not step.get("required", True):
                continue
            sid = str(step.get("id") or "")
            if sid and sid in completed:
                continue
            deps = [str(x) for x in (step.get("depends_on") or [])]
            if not all(dep in completed for dep in deps):
                continue
            return step
        return None

    def _completed_step_ids(self, goal_state, steps):
        for candidate in (getattr(goal_state, "completed_steps", None), getattr(goal_state, "completed", None), getattr(goal_state, "done_steps", None)):
            if callable(candidate):
                try: candidate = candidate()
                except TypeError: continue
            if isinstance(candidate, (list, tuple, set)):
                return {str(x) for x in candidate}
            if isinstance(candidate, dict):
                return {str(k) for k, v in candidate.items() if v}
        return {str((self._coerce_step(x) or {}).get("id")) for x in steps if str((self._coerce_step(x) or {}).get("status", "")).lower() in {"done", "completed", "success", "succeeded"}}

    def _goal_complete(self, goal_state):
        for name in ("is_complete", "complete", "completed"):
            value = getattr(goal_state, name, None)
            if callable(value):
                try: value = value()
                except TypeError: continue
            if isinstance(value, bool):
                return value
        return False

    def _step_to_call(self, step, analysis, context):
        tool, action = self._normalize_tool_action(step.get("tool"), step.get("action"))
        if not tool or not action:
            return None
        args = dict(step.get("arguments") or {})
        return {"tool": tool, "action": action, "arguments": args}

    def _build_prompt(self, user_message, context, analysis, goal_state, tools, history):
        payload = {
            "user": user_message,
            "context": context,
            "analysis": analysis,
            "goal_state": self._safe(goal_state),
            "tools": tools or {},
            "recent_history": (history or [])[-10:],
        }
        rules = """
You are KAREEM_AGENT's execution brain. Choose exactly ONE next action or a concise completion response.
The agent can operate BOTH the live Chrome session and the Windows desktop.
WEB RULES:
- For websites, use browser, not web, when the user asked you to visibly navigate/interact.
- Before interacting with a new page, inspect it using browser.inspect.
- Use semantic targets: visible text, role/name, or a UID from the latest snapshot. Never invent UIDs.
- For forms, prefer browser.fill or browser.fill_form when available; then verify the resulting state.
- After a click/navigation that changes the page, inspect again before acting on the new state.
- If a popup/cookie banner blocks the target, handle the blocker first when safe.
- If the same action fails repeatedly, stop looping and choose a different recovery path.
- Never bypass CAPTCHA/MFA/security verification.
DESKTOP RULES:
- Use desktop for native Windows applications or when the user explicitly asks for screen/mouse/keyboard control.
- Prefer window discovery/focus before coordinate clicks.
- Use screenshots only as a verification aid; do not hallucinate coordinates.
- Do not use desktop to change Registry/services/firewall/drivers; those belong to SystemTool's approval boundary.
GENERAL RULES:
- Use filesystem for local file operations.
- Never invent tool names or actions.
- One action per turn when later actions depend on the result.
- Never claim success without evidence from a tool result.
Return JSON only.
"""
        return rules + "\nPAYLOAD:\n" + json.dumps(payload, ensure_ascii=False, default=str, indent=2)

    def _normalize_tool_action(self, tool, action):
        t, a = str(tool or "").strip(), str(action or "").strip()
        if not t and "." in a:
            t, a = a.split(".", 1)
        elif "." in t and not a:
            t, a = t.split(".", 1)
        t = self.TOOL_ALIASES.get(t.lower(), t)
        a = self.ACTION_ALIASES.get(a.lower(), a)
        return (t or None), (a or None)

    def _normalize_plan(self, data):
        if data.get("type") == "chat":
            return {"type": "chat", "content": str(data.get("content") or "")}
        calls = data.get("calls") or data.get("tool_calls") or []
        out = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            t, a = self._normalize_tool_action(call.get("tool"), call.get("action"))
            if t and a:
                out.append({"tool": t, "action": a, "arguments": dict(call.get("arguments") or {})})
        if not out:
            return {"type": "chat", "content": str(data.get("content") or "")}
        return {"type": "tool_calls", "calls": out[:1]}

    def _parse_json(self, raw):
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try: return json.loads(text[start:end+1])
            except Exception: pass
        return None

    def _coerce_step(self, step):
        if isinstance(step, dict):
            return dict(step)
        if hasattr(step, "__dict__"):
            return dict(step.__dict__)
        return None

    def _safe(self, obj):
        if obj is None or isinstance(obj, (str, int, float, bool)): return obj
        if isinstance(obj, dict): return {str(k): self._safe(v) for k, v in list(obj.items())[:80]}
        if isinstance(obj, (list, tuple)): return [self._safe(x) for x in obj[:80]]
        return str(obj)
