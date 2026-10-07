from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from brain.goal_understanding import GoalUnderstanding
from brain.page_perception import PagePerception
from brain.reflection import ReflectionEngine
from brain.state_reasoner import StateReasoner
from learning.experience import ExperienceStore


class CognitiveRuntime:
    """Persistent perception -> reasoning -> verification context for one run."""

    def __init__(self, brain=None):
        self.goal_understanding = GoalUnderstanding(brain=brain)
        self.page_perception = PagePerception(brain=brain)
        self.state_reasoner = StateReasoner()
        self.reflection = ReflectionEngine(brain=brain)
        self.experience = ExperienceStore()
        self.goal: dict[str, Any] = {}
        self.page: dict[str, Any] = {}
        self.state: dict[str, Any] = {}
        self.reflection_note: dict[str, Any] = {}
        self.page_history: list[str] = []

    def start(self, user_message: str) -> dict[str, Any]:
        self.goal = self.goal_understanding.understand(user_message)
        return self.goal

    def update_page(self, snapshot: str) -> dict[str, Any]:
        self.page = self.page_perception.perceive(snapshot, self.goal)
        self.page_history.append(str(self.page.get("fingerprint") or ""))
        self.state = self.state_reasoner.reason(self.goal, self.page, [])
        return self.state

    def observe(self, result: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        snapshot = result.get("snapshot") or result.get("text")
        if not snapshot:
            return None
        self.update_page(str(snapshot))
        return self.state

    def on_failure(self, error: Any, history: list[dict[str, Any]]) -> dict[str, Any]:
        self.reflection_note = self.reflection.reflect(self.goal, self.state, history, error)
        return self.reflection_note

    def compact(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "page": {
                k: self.page.get(k)
                for k in ["url", "title", "domain", "page_type", "country", "currency", "search_fields", "result_links", "price_lines", "fingerprint", "llm"]
            },
            "state": self.state,
            "reflection": self.reflection_note,
            "page_history_tail": self.page_history[-6:],
        }

    def candidate_action_hints(self) -> list[dict[str, Any]]:
        g = self.goal
        p = self.page
        s = self.state
        hints: list[dict[str, Any]] = []
        url = str(p.get("url") or "")
        if s.get("complete"):
            return []
        if not url:
            hints.append({"tool": "browser", "action": "open_url", "arguments": {"url": g.get("start_url")}, "why": "No current page."})
            return [x for x in hints if x["arguments"].get("url")]
        if s.get("mismatches"):
            site = g.get("site") or urlparse(url).netloc
            country = g.get("country") or ""
            hints.append({"tool": "web", "action": "search", "arguments": {"query": f"{site} official {country} website", "max_results": 5}, "why": "Resolve the requested regional context before acting."})
        elif s.get("status") == "needs_navigation_or_inspection":
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Need current page semantics."})
        elif s.get("status") == "ready_for_search":
            field = (p.get("search_fields") or [{"name": "search"}])[0]
            hints.append({"tool": "browser", "action": "fill", "arguments": {"uid": field.get("uid"), "target": field.get("name") or "search", "value": g.get("query") or ""}, "why": "Fill the actual search field with the semantic query only."})
        elif s.get("status") == "results_ready" and g.get("requires_first_result"):
            hints.append({"tool": "browser", "action": "click", "arguments": {"first_result": True}, "why": "Open the first result in the search-result context."})
        elif s.get("status") in {"collecting", "results_ready"}:
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Collect and verify visible result evidence before completion."})
        else:
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Refresh the perception model."})
        return hints

    def proof(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "state": self.state,
            "page": self.page,
            "proof": self.state.get("complete", False),
        }

    def record_experience(self, user_message: str, outcome: dict[str, Any], history: list[dict[str, Any]], reflection: dict[str, Any] | None = None) -> None:
        self.experience.add({
            "user_message": user_message,
            "goal": self.goal,
            "outcome": outcome,
            "reflection": reflection or self.reflection_note,
            "history": history[-40:],
        })
