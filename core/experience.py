import json
import re
import time
from pathlib import Path
from typing import Any


class ExperienceStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "experiences.jsonl"

    def append(self, task: dict[str, Any]):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), **task}, ensure_ascii=False) + "\n")

    def recent(self, limit=6):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        out = []
        for line in lines:
            try: out.append(json.loads(line))
            except Exception: pass
        return out

    def search(self, query: str, limit=8):
        q = set(re.findall(r"[\w\u0600-\u06ff]+", query.lower()))
        scored = []
        if not self.path.exists(): return []
        for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try: item = json.loads(line)
            except Exception: continue
            text = json.dumps(item, ensure_ascii=False).lower()
            score = sum(1 for token in q if token in text)
            if score: scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:limit]]
