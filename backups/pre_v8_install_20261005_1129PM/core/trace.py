from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class TraceStore:
    def __init__(self, root: str | Path = "data/traces"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = self.root / f"run_{stamp}_{int(time.time()*1000)%1000:03d}.jsonl"

    def emit(self, event: str, **payload: Any) -> None:
        row = {"ts": time.time(), "event": event, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
