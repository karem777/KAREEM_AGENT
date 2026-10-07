from __future__ import annotations

import re
from pathlib import Path

from knowledge.store import KnowledgeStore


class SkillBuilder:
    def __init__(self, knowledge: KnowledgeStore, skills_root: str | Path = "data/skills") -> None:
        self.knowledge = knowledge
        self.root = Path(skills_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _llm_summarize(self, topic: str, results: list[dict]) -> str | None:
        try:
            from brain.local_brain import LocalBrain
            brain = LocalBrain()
            evidence = "\n\n".join(
                f"SOURCE: {r.get('url')}\nTITLE: {r.get('title')}\nTEXT: {r.get('text','')}"
                for r in results
            )[:22000]
            prompt = f"""
Create a reusable technical skill for an autonomous local agent.
Topic: {topic}
Use ONLY the supplied sources.
Return practical knowledge: concepts, procedures, conditions, common mistakes, verification steps.
Do not invent facts not supported by the sources.

{evidence}
""".strip()
            out = str(brain.ask(prompt) or "").strip()
            return out if len(out) > 80 else None
        except Exception:
            return None

    def build_skill(self, topic: str, name: str | None = None, max_sources: int = 8) -> dict:
        results = self.knowledge.search(topic, limit=max_sources)
        if not results:
            return {"success": False, "error": "No learned knowledge matched the topic."}
        safe = re.sub(r"[^a-z0-9_-]+", "-", (name or topic).lower()).strip("-") or "skill"
        generated = self._llm_summarize(topic, results)
        body_lines = [f"# Skill: {safe}", "", f"Topic: {topic}", ""]
        if generated:
            body_lines += ["## Agent Knowledge", "", generated, ""]
        body_lines += ["## Sources", ""]
        for r in results:
            body_lines.append(f"- {r.get('title') or r.get('url')} — {r.get('url')}")
        body = "\n".join(body_lines).strip() + "\n"
        self.knowledge.upsert_skill(
            name=safe,
            description=f"Learned knowledge for {topic}",
            body=body,
            metadata={"topic": topic, "source_count": len(results), "llm_synthesized": bool(generated)},
        )
        path = self.root / f"{safe}.md"
        path.write_text(body, encoding="utf-8")
        return {"success": True, "name": safe, "path": str(path), "source_count": len(results), "llm_synthesized": bool(generated)}
