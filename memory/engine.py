from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from knowledge.store import KnowledgeStore


class LongTermMemory:
    """Mem0-first memory with a local SQLite fallback.

    Mem0 is optional so the agent remains usable even before its extra packages
    finish installing or when a vector backend is unavailable.
    """

    def __init__(self, root: str | Path = "data/memory") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fallback = KnowledgeStore(self.root / "fallback")
        self._mem0 = None
        self.backend = "sqlite"
        self._try_mem0()

    def _try_mem0(self) -> None:
        try:
            from mem0 import Memory  # type: ignore
            cfg = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": os.getenv("KAREEM_MEM0_COLLECTION", "kareem_agent_memory"),
                        "host": os.getenv("KAREEM_QDRANT_HOST", "localhost"),
                        "port": int(os.getenv("KAREEM_QDRANT_PORT", "6333")),
                    },
                },
                "llm": {
                    "provider": "ollama",
                    "config": {
                        "model": os.getenv("KAREEM_MEM0_LLM", "qwen3:8b"),
                        "ollama_base_url": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                    },
                },
                "embedder": {
                    "provider": "ollama",
                    "config": {
                        "model": os.getenv("KAREEM_MEM0_EMBEDDER", "nomic-embed-text"),
                        "ollama_base_url": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                    },
                },
            }
            self._mem0 = Memory.from_config(cfg)
            self.backend = "mem0+qdrant"
        except Exception:
            self._mem0 = None
            self.backend = "sqlite"

    def remember(self, text: str, user_id: str = "kareem", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = str(text or "").strip()
        if not payload:
            return {"success": False, "error": "Empty memory"}
        if self._mem0 is not None:
            try:
                out = self._mem0.add(payload, user_id=user_id, metadata=metadata or {})
                return {"success": True, "backend": self.backend, "result": out}
            except Exception as exc:
                self.backend = "sqlite"
                self._mem0 = None
        try:
            self.fallback.add_document(
                url=f"memory://{user_id}/{hash(payload)}",
                title="KAREEM_AGENT memory",
                text=payload,
                domain="memory",
                metadata={"user_id": user_id, **(metadata or {})},
            )
            return {"success": True, "backend": "sqlite"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search(self, query: str, user_id: str = "kareem", limit: int = 8) -> list[dict[str, Any]]:
        if self._mem0 is not None:
            try:
                out = self._mem0.search(query, user_id=user_id, limit=limit)
                if isinstance(out, dict):
                    out = out.get("results", out.get("memories", []))
                return out if isinstance(out, list) else [out]
            except Exception:
                pass
        return self.fallback.search(query, limit=limit)

    def describe(self) -> dict[str, Any]:
        return {"backend": self.backend}
