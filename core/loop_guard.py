import json
import time
import hashlib
from collections import defaultdict
from typing import Any


class LoopGuard:
    def __init__(self, max_same=2, max_total_repeats=8):
        self.max_same = max_same
        self.max_total_repeats = max_total_repeats
        self.counts = defaultdict(int)
        self.timeline = []

    @staticmethod
    def key(state_fingerprint: str, tool: str, action: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps({"s": state_fingerprint, "t": tool, "a": action, "g": arguments}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(payload.encode()).hexdigest()

    def check(self, state_fingerprint: str, tool: str, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        k = self.key(state_fingerprint, tool, action, arguments)
        self.counts[k] += 1
        self.timeline.append((time.time(), k))
        return {
            "key": k,
            "count": self.counts[k],
            "repeat": self.counts[k] > 1,
            "blocked": self.counts[k] > self.max_same,
            "reason": "same action on same world state repeated" if self.counts[k] > self.max_same else "ok",
        }
