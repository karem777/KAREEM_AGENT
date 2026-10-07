import json
from typing import Any

from brain.complete_brain import CompleteBrain


class CompletePlanner:
    """State-first planner. It emits executable JSON, not prose."""

    def __init__(self, brain=None):
        self.brain = brain or CompleteBrain()

    def plan(self, goal: dict[str, Any], world: dict[str, Any], history: list[dict[str, Any]], tools: dict[str, Any], recovery: dict[str, Any] | None = None, experiences: list[dict[str, Any]] | None = None):
        recent = history[-6:]
        compact_tools = tools
        prompt = f'''
You are KAREEM_AGENT COMPLETE, an autonomous local agent using Qwen3:8b.
You are operating a real Windows machine and a real Chrome session.
Return JSON only. Never return planning prose.

Your job is to choose the NEXT useful action based on verified world state.
You have up to 80 cycles, so spend cycles on observation, verification, recovery, and deeper research when needed.
Never repeat a successful action merely because it is familiar.
Never call a target webpage's arbitrary textbox "search" unless world facts prove it is a search field.
Never declare completion without evidence from the world/tool result.
For browser work, treat URL/origin/navigation as hard facts; page-type guesses are advisory.
For system changes, respect approval_required responses and never bypass them.

GOAL CONTRACT:
{json.dumps(goal, ensure_ascii=False)}

CURRENT WORLD:
{json.dumps(world, ensure_ascii=False)}

RECENT HISTORY:
{json.dumps(recent, ensure_ascii=False)}

RECOVERY SIGNAL:
{json.dumps(recovery or {}, ensure_ascii=False)}

RECALLED EXPERIENCE:
{json.dumps(experiences or [], ensure_ascii=False)}

AVAILABLE TOOLS:
{json.dumps(compact_tools, ensure_ascii=False)}

Output exactly one of:
{{"type":"tool_call","tool":"...","action":"...","arguments":{{...}},"reason":"...","expected":"..."}}
{{"type":"finish","answer":"...","evidence":[...]}}
{{"type":"ask_user","question":"..."}}

Choose a real tool action. Prefer inspect/read/verify before guessing. For a complex task, take one meaningful step at a time; multiple independent safe tool calls are allowed only if no dependency exists between them.
'''
        fallback = {"type": "tool_call", "tool": "browser", "action": "inspect", "arguments": {}, "reason": "Refresh world state before acting.", "expected": "Fresh page observation"}
        return self.brain.json(prompt, fallback=fallback)
