import json
import re
from typing import Any

from brain.complete_brain import CompleteBrain


class GoalContract:
    """Turns natural language into a stable, site-agnostic executable contract."""

    def __init__(self, brain=None):
        self.brain = brain or CompleteBrain()

    def compile(self, user_request: str) -> dict[str, Any]:
        prompt = f'''
You are the goal compiler for an autonomous Windows + Web agent.
Convert the user request to JSON only.
Do not invent a website-specific selector or fixed workflow.
Describe the desired outcome and what evidence proves completion.

JSON schema:
{{
  "goal": string,
  "domain": "web"|"windows"|"mixed"|"research"|"coding"|"general",
  "targets": [string],
  "actions_allowed": [string],
  "required_outcomes": [string],
  "verification": [string],
  "research_needed": boolean,
  "risk_level": "low"|"medium"|"high",
  "success_definition": string
}}

USER:
{user_request}
'''
        fallback = self._heuristic(user_request)
        value = self.brain.json(prompt, fallback=fallback)
        if not isinstance(value, dict):
            return fallback
        for key, default in fallback.items():
            value.setdefault(key, default)
        return value

    def _heuristic(self, request: str) -> dict[str, Any]:
        low = request.lower()
        research = any(w in low for w in ["ابحث", "مشاريع", "قارن", "research", "github", "دور"])
        windows = any(w in low for w in ["ويندوز", "الجهاز", "النظام", "powershell", "برنامج", "ملف", "خدمة", "process"])
        web = any(w in low for w in ["ادخل", "افتح", "موقع", "جوجل", "بحث", "متجر", "website", "google"])
        domain = "mixed" if windows and web else "research" if research and not web else "windows" if windows else "web" if web else "general"
        return {
            "goal": request,
            "domain": domain,
            "targets": [],
            "actions_allowed": ["inspect", "search", "navigate", "click", "fill", "read", "compare", "execute", "verify"],
            "required_outcomes": [request],
            "verification": ["evidence matches the user's requested outcome"],
            "research_needed": research,
            "risk_level": "medium" if windows else "low",
            "success_definition": "The requested outcome is evidenced by actual observations, not a model claim.",
        }
