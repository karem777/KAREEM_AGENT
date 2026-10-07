from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ConversationStore:
    """Small local chat memory used by the supervisor/talker layer."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "conversation.jsonl"

    def append(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        item = {
            "ts": time.time(),
            "role": str(role),
            "content": str(content),
            "metadata": metadata or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines()[-int(limit):]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
        return rows

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
