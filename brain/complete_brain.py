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
        self.timeout = float(timeout)
        self.client = ollama.Client(timeout=self.timeout) if ollama is not None else None
        self.think = os.getenv("KAREEM_THINK", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _options(self):
        return {
            "temperature": 0,
            "num_ctx": int(os.getenv("KAREEM_CONTEXT", "8192")),
        }

    @staticmethod
    def _message_value(response, key, default=""):
        if isinstance(response, dict):
            message = response.get("message") or {}
            if isinstance(message, dict):
                return message.get(key, default) or default
            return getattr(message, key, default) or default

        message = getattr(response, "message", None) or {}
        return getattr(message, key, default) or default

    def text(self, prompt: str, json_mode=False) -> str:
        if ollama is None:
            raise RuntimeError("ollama package is not installed")

        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "options": self._options(),
            "keep_alive": os.getenv("KAREEM_KEEP_ALIVE", "10m"),
            "think": self.think,
        }

        if json_mode:
            kwargs["format"] = "json"

        response = self.client.chat(**kwargs)

        content = self._message_value(response, "content", "")
        if content:
            return str(content)

        thinking = self._message_value(response, "thinking", "")
        return str(thinking)

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
            "think": self.think,
        }

        if tools:
            kwargs["tools"] = tools

        response = self.client.chat(**kwargs)

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
            return self._extract_json(self.text(prompt, json_mode=True))
        except Exception:
            if fallback is not None:
                return fallback

            raise
