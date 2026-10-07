from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class ExperienceStore:
    """Append-only episodic trajectory memory for continual learning.

    Each record is suitable for retrieval, reflection, and later supervised /
    preference-dataset export. No model-weight update is required.
    """

    def __init__(self, root: str | Path = "data/experiences"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "trajectories.jsonl"

    def add(self, record: dict[str, Any]) -> dict[str, Any]:
        item = {"id": uuid.uuid4().hex, "ts": time.time(), **record}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        return item

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        out = []
        for line in lines[-int(limit):]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    out.append(item)
            except Exception:
                continue
        return out

    def export_dataset(self, destination: str | Path = "data/experiences/training_dataset.jsonl") -> str:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for item in self.recent(100000):
            goal = item.get("goal") or {}
            reflections = item.get("reflection") or ""
            outcome = item.get("outcome") or {}
            rows.append({
                "instruction": item.get("user_message", ""),
                "input": json.dumps({"goal": goal, "outcome": outcome}, ensure_ascii=False),
                "response": reflections,
            })
        with destination.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(destination)
