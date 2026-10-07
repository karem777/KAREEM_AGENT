from __future__ import annotations

from knowledge.store import KnowledgeStore


class KnowledgeTool:
    name = "knowledge"
    description = "Persistent local knowledge store and retrieval."

    def __init__(self):
        self.store = KnowledgeStore()

    def search(self, query: str, limit: int = 8):
        return {"success": True, "results": self.store.search(query, limit=limit)}

    def sources(self, limit: int = 50):
        return {"success": True, "sources": self.store.list_sources(limit=limit)}

    def skills(self):
        return {"success": True, "skills": self.store.list_skills()}

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search": {"description": "Search local knowledge.", "parameters": {"query": {"type": "string", "required": True}, "limit": {"type": "integer", "required": False, "default": 8}}},
                "sources": {"description": "List learned sources.", "parameters": {"limit": {"type": "integer", "required": False, "default": 50}}},
                "skills": {"description": "List reusable learned skills.", "parameters": {}},
            },
        }
