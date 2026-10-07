from __future__ import annotations

from urllib.parse import urlparse

from learning.learner import SiteLearner
from learning.skill_builder import SkillBuilder
from knowledge.store import KnowledgeStore


class LearningTool:
    name = "learning"
    description = "Learn from public websites/docs and the currently open browser page, then build reusable local skills."

    def __init__(self, knowledge: KnowledgeStore | None = None, browser=None):
        self.knowledge = knowledge or KnowledgeStore()
        self.browser = browser
        self.learner = SiteLearner(self.knowledge)
        self.skills = SkillBuilder(self.knowledge)

    def learn_site(self, url: str, max_pages: int = 12) -> dict:
        return self.learner.learn_site(url, max_pages=max_pages)

    def learn_current_page(self, topic: str = "current page") -> dict:
        if self.browser is None:
            return {"success": False, "error": "Browser capability is not connected to the learning tool."}
        result = self.browser.inspect()
        if not isinstance(result, dict) or not result.get("success"):
            return {"success": False, "error": "Could not inspect current browser page.", "details": result}
        snapshot = str(result.get("snapshot") or result.get("text") or "").strip()
        if len(snapshot) < 80:
            return {"success": False, "error": "Current page did not expose enough readable content."}
        # Pull the most useful URL from the current page/list result if available.
        url = str(result.get("url") or "").strip() or "browser://current"
        domain = urlparse(url).netloc
        source_id = self.knowledge.add_document(
            url=url,
            title=f"Browser page: {topic}",
            text=snapshot,
            domain=domain,
            metadata={"learner": "current_browser_page", "topic": topic},
        )
        return {"success": True, "source_id": source_id, "url": url, "chars": len(snapshot), "topic": topic}

    def search_knowledge(self, query: str, limit: int = 8) -> dict:
        return {"success": True, "results": self.knowledge.search(query, limit=limit)}

    def build_skill(self, topic: str, name: str = "") -> dict:
        return self.skills.build_skill(topic, name=name or None)

    def list_skills(self) -> dict:
        return {"success": True, "skills": self.knowledge.list_skills()}

    def list_sources(self, limit: int = 50) -> dict:
        return {"success": True, "sources": self.knowledge.list_sources(limit=limit)}

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "learn_site": {"description": "Crawl and learn from a public website/docs site.", "parameters": {"url": {"type": "string", "required": True}, "max_pages": {"type": "integer", "required": False, "default": 12}}},
                "learn_current_page": {"description": "Store readable content from the currently selected Chrome page as knowledge.", "parameters": {"topic": {"type": "string", "required": False, "default": "current page"}}},
                "search_knowledge": {"description": "Search locally learned knowledge.", "parameters": {"query": {"type": "string", "required": True}, "limit": {"type": "integer", "required": False, "default": 8}}},
                "build_skill": {"description": "Turn learned knowledge into a reusable local skill.", "parameters": {"topic": {"type": "string", "required": True}, "name": {"type": "string", "required": False}}},
                "list_skills": {"description": "List learned skills.", "parameters": {}},
                "list_sources": {"description": "List learned source pages.", "parameters": {"limit": {"type": "integer", "required": False, "default": 50}}},
            },
        }
