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
from core.handoff import ToolHandoffRouter


class CognitiveRuntime:
    """Persistent goal -> perception -> world-state -> verification context."""

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
        self.page = {}
        self.state = {}
        self.page_history = []
        self.reflection_note = {}
        return self.goal

    def update_page(self, snapshot: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.page = self.page_perception.perceive(snapshot, self.goal)
        fp = str(self.page.get("fingerprint") or "")
        if fp:
            self.page_history.append(fp)
        self.state = self.state_reasoner.reason(self.goal, self.page, history or [])
        return self.state

    def observe(self, result: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        snapshot = result.get("snapshot") or result.get("text")
        if not snapshot:
            return None
        return self.update_page(str(snapshot), history)

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
            "page_history_tail": self.page_history[-8:],
        }

    def candidate_action_hints(self, history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        history = history or []
        g, p, s = self.goal, self.page, self.state
        hints: list[dict[str, Any]] = []
        handoff = ToolHandoffRouter(g, history)

        if s.get("complete"):
            return []
        # Once the state machine has a deterministic completion proof, never emit
        # another browser action even if an LLM perception pass is stale.
        if s.get("completion_proof"):
            return []

        # First-class Web -> Browser handoff.
        # A failed browser.open_url is never considered a successful handoff.
        last_failed_open = any(
            isinstance(h, dict)
            and h.get("role") == "tool"
            and h.get("tool") == "browser"
            and h.get("action") == "open_url"
            and not bool((h.get("result") or {}).get("success"))
            for h in history[-6:]
        )
        url = handoff.discovery_handoff()
        if url and (last_failed_open or not any(
            h.get("role") == "tool" and h.get("tool") == "browser" and h.get("action") == "open_url" and bool((h.get("result") or {}).get("success")) and str((h.get("arguments") or {}).get("url") or "").rstrip("/").casefold() == url.rstrip("/").casefold()
            for h in history
        )):
            return [{"tool": "browser", "action": "open_url", "arguments": {"url": url}, "why": "Web discovery found the target; hand off to the interactive browser."}]

        if not p.get("url"):
            if g.get("start_url"):
                return [{"tool": "browser", "action": "open_url", "arguments": {"url": g["start_url"]}, "why": "Open the explicit target URL."}]
            if g.get("site") and not handoff.searched_same_query():
                return [{"tool": "web", "action": "search", "arguments": {"query": f"{g.get('site')} official {g.get('country') or ''} website".strip(), "max_results": 5}, "why": "Discover the target website and region."}]

        if s.get("status") == "wrong_context":
            # One fresh perception pass is useful; after that, let the LLM reason over
            # the already-inspected state instead of looping inspect forever.
            last_browser = handoff.last_browser_action()
            last_fp = self.page.get("fingerprint")
            if not (last_browser and last_browser.get("action") == "inspect" and last_fp):
                hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Inspect the current context once to locate a regional/currency fix."})
        elif s.get("status") == "needs_navigation_or_inspection":
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Need current page semantics before acting."})
        elif s.get("status") == "ready_for_search":
            field = (p.get("search_fields") or [{"name": "search"}])[0]
            value = g.get("query") or ""
            current_value = str(field.get("value") or "")
            if current_value.strip() == str(value).strip() and value.strip():
                hints.append({"tool": "browser", "action": "press_key", "arguments": {"page_id": p.get("page_id"), "key": "Enter"}, "why": "The search field already contains the target query; submit instead of refilling."})
            else:
                hints.append({"tool": "browser", "action": "fill", "arguments": {"uid": field.get("uid"), "target": field.get("name") or "search", "value": value}, "why": "Fill only the semantic search query."})
        elif s.get("status") == "results_ready" and g.get("requires_first_result"):
            hints.append({"tool": "browser", "action": "click", "arguments": {"first_result": True}, "why": "The first organic result is the user's requested next action."})
        elif s.get("status") in {"results_ready", "collecting"}:
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Re-perceive the result page and collect evidence before completion."})
        else:
            hints.append({"tool": "browser", "action": "inspect", "arguments": {}, "why": "Refresh world state."})
        return hints

    def proof(self) -> dict[str, Any]:
        return {"goal": self.goal, "state": self.state, "page": self.page, "proof": self.state.get("complete", False)}

    def record_experience(self, user_message: str, outcome: dict[str, Any], history: list[dict[str, Any]], reflection: dict[str, Any] | None = None) -> None:
        self.experience.add({
            "user_message": user_message,
            "goal": self.goal,
            "outcome": outcome,
            "reflection": reflection or self.reflection_note,
            "history": history[-60:],
        })
