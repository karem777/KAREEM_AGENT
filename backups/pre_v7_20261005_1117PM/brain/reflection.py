from __future__ import annotations

import json
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.local_brain import LocalBrain


class ReflectionEngine:
    """Reflexion-style failure analysis without changing model weights."""

    def __init__(self, brain: LocalBrain | None = None):
        if brain is None:
            from brain.local_brain import LocalBrain
            brain = LocalBrain()
        self.brain = brain

    def reflect(self, goal: dict[str, Any], state: dict[str, Any], history: list[dict[str, Any]], error: Any = None) -> dict[str, Any]:
        prompt = f"""
You are the failure-analysis module of KAREEM_AGENT.
Review the failed trajectory and produce one practical lesson that can change
future behavior. Do not invent facts not present in the trajectory.

GOAL:
{json.dumps(goal, ensure_ascii=False)}

STATE:
{json.dumps(state, ensure_ascii=False)}

ERROR:
{json.dumps(error, ensure_ascii=False, default=str)}

RECENT HISTORY:
{json.dumps(history[-10:], ensure_ascii=False, default=str)}

Return JSON only:
{{"mistake":"...","lesson":"...","next_strategy":"...","avoid":"..."}}
"""
        try:
            value = json.loads(str(self.brain.ask(prompt)).strip())
            return value if isinstance(value, dict) else {}
        except Exception:
            return {
                "mistake": str(error or "unknown failure"),
                "lesson": "Reinspect the current state before repeating the failed action.",
                "next_strategy": "Change action or gather more evidence.",
                "avoid": "Blindly repeating the same action.",
            }
