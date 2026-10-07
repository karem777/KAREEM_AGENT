import json
import os
import re
from typing import Any

try:
    import ollama
except Exception:
    ollama = None


class CompleteBrain:
    """Local Qwen interface with native Ollama tool-calling support."""

    def __init__(self, model=None, timeout=180):
        self.model = model or os.getenv("KAREEM_MODEL", "qwen3:8b")
        self.timeout = timeout

    def _options(self):
        return {
            "temperature": 0,
            "num_ctx": int(os.getenv("KAREEM_CONTEXT", "12288")),
        }

    def text(self, prompt: str) -> str:
        if ollama is None:
            raise RuntimeError("ollama package is not installed")

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options=self._options(),
            keep_alive=os.getenv("KAREEM_KEEP_ALIVE", "10m"),
        )

        return (response.get("message") or {}).get("content", "")

    def chat(self, messages, tools=None):
        """
        Native Ollama chat interface.

        Normalizes tool_calls so the planner does not care whether the
        installed Ollama Python package returns dictionaries or objects.
        """
        if ollama is None:
            raise RuntimeError("ollama package is not installed")

        kwargs = {
            "model": self.model,
            "messages": messages,
            "options": self._options(),
            "keep_alive": os.getenv("KAREEM_KEEP_ALIVE", "10m"),
        }

        if tools:
            kwargs["tools"] = tools

        response = ollama.chat(**kwargs)

        if isinstance(response, dict):
            message = response.get("message") or {}
        else:
            message = getattr(response, "message", None) or {}

        if isinstance(message, dict):
            content = message.get("content", "") or ""
            raw_calls = message.get("tool_calls", []) or []
        else:
            content = getattr(message, "content", "") or ""
            raw_calls = getattr(message, "tool_calls", []) or []

        calls = []

        for call in raw_calls:
            if isinstance(call, dict):
                function = call.get("function") or {}
                name = function.get("name", "")
                arguments = function.get("arguments", {}) or {}
            else:
                function = getattr(call, "function", None)

                name = (
                    getattr(function, "name", "")
                    if function is not None
                    else ""
                )

                arguments = (
                    getattr(function, "arguments", {})
                    if function is not None
                    else {}
                )

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except Exception:
                    arguments = {"raw_arguments": arguments}

            calls.append({
                "name": str(name),
                "arguments": arguments,
            })

        return {
            "content": str(content),
            "tool_calls": calls,
            "raw": response,
        }

    @staticmethod
    def _extract_json(text: str) -> Any:
        text = text.strip()

        candidates = [text]

        fenced = re.findall(
            r"```(?:json)?\s*(.*?)```",
            text,
            flags=re.S | re.I,
        )

        candidates.extend(fenced)

        for candidate in candidates:
            candidate = candidate.strip()

            try:
                return json.loads(candidate)
            except Exception:
                pass

            starts = [
                m.start()
                for m in re.finditer(r"[\[{]", candidate)
            ]

            for start in starts:
                fragment = candidate[start:]

                for end in range(
                    len(fragment),
                    max(0, len(fragment) - 12000),
                    -1,
                ):
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
