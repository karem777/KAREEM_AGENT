import json
import os
import re
from typing import Any

try:
    import ollama
except Exception:
    ollama = None


class CompleteBrain:
    """Small, strict JSON interface around the local Qwen model."""

    def __init__(self, model=None, timeout=180):
        self.model = model or os.getenv("KAREEM_MODEL", "qwen3:8b")
        self.timeout = timeout

    def text(self, prompt: str) -> str:
        if ollama is None:
            raise RuntimeError("ollama package is not installed")
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_ctx": int(os.getenv("KAREEM_CONTEXT", "8192"))},
            keep_alive=os.getenv("KAREEM_KEEP_ALIVE", "10m"),
        )
        return (response.get("message") or {}).get("content", "")

    @staticmethod
    def _extract_json(text: str) -> Any:
        text = text.strip()
        candidates = [text]
        fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
        candidates.extend(fenced)
        for candidate in candidates:
            candidate = candidate.strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass
            starts = [m.start() for m in re.finditer(r"[\[{]", candidate)]
            for start in starts:
                fragment = candidate[start:]
                for end in range(len(fragment), max(0, len(fragment) - 12000), -1):
                    piece = fragment[:end]
                    try:
                        return json.loads(piece)
                    except Exception:
                        continue
        raise ValueError("Model did not return valid JSON")

    def json(self, prompt: str, fallback: Any = None) -> Any:
        try:
            return self._extract_json(self.text(prompt))
        except Exception:
            if fallback is not None:
                return fallback
            raise
