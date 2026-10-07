from __future__ import annotations

import json
import re

from brain.local_brain import LocalBrain


class AnalyticalBrain:
    """Generic natural-language goal analyzer kept for compatibility.

    Browser state sequencing is handled by the universal Planner/BrowserGoalController;
    this module deliberately contains no per-site workflow or site-specific routing.
    """

    def __init__(self):
        self.brain = LocalBrain()

    @staticmethod
    def _clean_json(raw):
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        return re.sub(r"\s*```$", "", text).strip()

    def analyze(self, user_message, available_tools=None, previous_goal=None):
        prompt = {
            "role": "goal_analyzer",
            "instruction": "Interpret the user's natural-language goal and return an ordered, site-agnostic task graph. Never invent site-specific workflows.",
            "user_message": str(user_message or ""),
            "available_tools": available_tools or {},
            "previous_goal": previous_goal or {},
        }
        raw = self.brain.ask(json.dumps(prompt, ensure_ascii=False))
        text = self._clean_json(raw)
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {"mode": "chat", "answer": text}
        except Exception:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    value = json.loads(match.group(0))
                    return value if isinstance(value, dict) else {"mode": "chat", "answer": text}
                except Exception:
                    pass
            return {"mode": "chat", "answer": text}
