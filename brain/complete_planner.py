import json
from typing import Any

from brain.complete_brain import CompleteBrain


class CompletePlanner:
    """Supervisor brain: converse naturally or select one agent action."""

    def __init__(self, brain=None):
        self.brain = brain or CompleteBrain()

    def _build_prompt(
        self,
        goal,
        world,
        history,
        tools,
        recovery,
        experiences,
        conversation=None,
    ):
        return f"""
You are KAREEM_AGENT, a local conversational AI supervisor with the ability to control a computer.

You have TWO valid outcomes:
1. CHAT: answer naturally when the user is asking, discussing, explaining, planning, or giving context.
2. ACT: when the user wants something done, choose exactly ONE next action from LIVE TOOLS, observe its result, then reason again.

You are not a fixed workflow. The model decides behavior from the user's intent, conversation, current world, tools, memory, and observations.

Rules:
- Understand follow-ups using CONVERSATION and current state.
- Do not ask the user to restate an actionable request.
- Do not invent IDs, coordinates, controls, URLs, files, or unseen UI state.
- Inspect before interacting with unknown targets.
- After an action, use the newest observation.
- On failure, diagnose the result and choose a different recovery action.
- Never blindly repeat an action on an unchanged state.
- Never claim task completion without evidence.
- Use relevant experience and learned knowledge when useful.
- User corrections and new instructions override stale assumptions.
- Ask a question only when the missing information is genuinely necessary and cannot be obtained with available tools.
- Never return ask_user as a machine action.

Return exactly one JSON object:
{{"type":"chat","content":"..."}}
OR
{{"type":"tool_call","tool":"...","action":"...","arguments":{{}}}}
OR
{{"type":"finish","answer":"...","evidence":[]}}

USER MESSAGE:
{json.dumps(goal.get("goal", ""), ensure_ascii=False)}

CONVERSATION:
{json.dumps((conversation or [])[-10:], ensure_ascii=False)}

CURRENT WORLD:
{json.dumps(world, ensure_ascii=False)}

RECENT AGENT HISTORY:
{json.dumps(history[-4:], ensure_ascii=False)}

RECOVERY:
{json.dumps(recovery or {}, ensure_ascii=False)}

RELEVANT EXPERIENCE:
{json.dumps(experiences or [], ensure_ascii=False)}

LIVE TOOLS:
{json.dumps(tools, ensure_ascii=False)}

For ACT, choose only a real tool/action from LIVE TOOLS.
For CHAT, answer the user directly without pretending an action happened.
""".strip()

    def plan(
        self,
        goal: dict[str, Any],
        world: dict[str, Any],
        history: list[dict[str, Any]],
        tools: dict[str, Any],
        recovery=None,
        experiences=None,
        conversation=None,
    ):
        prompt = self._build_prompt(
            goal, world, history, tools, recovery, experiences, conversation
        )

        try:
            value = self.brain.json(prompt, fallback=None)
            if not isinstance(value, dict):
                return {"type": "invalid_plan", "reason": "Planner returned a non-object decision."}

            if value.get("type") == "ask_user":
                return {
                    "type": "invalid_plan",
                    "reason": "Planner attempted clarification instead of using conversation or tools.",
                }

            ptype = str(value.get("type") or "").strip().lower()
            if ptype == "chat":
                return {"type": "chat", "content": str(value.get("content") or "").strip()}
            if ptype == "finish":
                return {
                    "type": "finish",
                    "answer": str(value.get("answer") or ""),
                    "evidence": value.get("evidence") or [],
                }
            if ptype == "tool_call":
                args = value.get("arguments")
                return {
                    "type": "tool_call",
                    "tool": str(value.get("tool") or "").strip(),
                    "action": str(value.get("action") or "").strip(),
                    "arguments": args if isinstance(args, dict) else {},
                }

            return {"type": "invalid_plan", "reason": f"Unknown planner outcome: {ptype}"}
        except Exception as exc:
            return {"type": "invalid_plan", "reason": f"Planner decision failed: {exc}"}
