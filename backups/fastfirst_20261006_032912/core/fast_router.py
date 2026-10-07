import re
from dataclasses import dataclass
from urllib.parse import quote


@dataclass
class FastTask:
    kind: str
    actions: list[dict]
    reason: str


class FastRouter:
    """Zero-LLM fast paths for deterministic, low-risk tasks."""

    SEARCH_ENGINES = {
        "google": "https://www.google.com/",
        "جوجل": "https://www.google.com/",
        "bing": "https://www.bing.com/",
        "بينج": "https://www.bing.com/",
        "duckduckgo": "https://duckduckgo.com/",
        "داك": "https://duckduckgo.com/",
    }

    def route(self, request: str) -> FastTask | None:
        text = " ".join(str(request).split())
        low = text.lower()

        m = re.fullmatch(r"(?:افتح|ادخل|open|go to)\s+(https?://[^\s]+)", text, re.I)
        if m:
            return FastTask(
                "open_url",
                [{"tool": "browser", "action": "open_url", "arguments": {"url": m.group(1)}}],
                "Explicit URL open is deterministic.",
            )

        engine = None
        for key, base in self.SEARCH_ENGINES.items():
            if key in low:
                engine = base
                break

        first_result = bool(
            re.search(
                r"(افتح\s+أول\s+نتيجة|افتح\s+النتيجة\s+الأولى|open\s+(?:the\s+)?first\s+result|first\s+result)",
                low,
                re.I,
            )
        )
        search_match = re.search(
            r"(?:ابحث\s+عن|ابحث\s+في\s+[^\s]+\s+عن|search\s+for|find)\s+(.+?)(?=\s+(?:وافتح|ثم\s+افتح|و\s*افتح|and\s+open|open\s+the\s+first)|$)",
            text,
            re.I,
        )
        if engine and search_match:
            query = search_match.group(1).strip().strip("\"'")
            if query:
                search_url = engine.rstrip("/") + "/search?q=" + quote(query)
                actions = [
                    {"tool": "browser", "action": "open_url", "arguments": {"url": engine}},
                    {"tool": "browser", "action": "open_url", "arguments": {"url": search_url}},
                    {"tool": "browser", "action": "inspect", "arguments": {}},
                ]
                if first_result:
                    actions.append(
                        {"tool": "browser", "action": "click", "arguments": {"first_result": True}}
                    )
                return FastTask(
                    "search_first_result" if first_result else "search",
                    actions,
                    "Simple search workflow is deterministic and needs no planning LLM.",
                )

        m = re.search(
            r"(?:افتح|ادخل|open|go to)\s+([a-z0-9.-]+\.(?:com|net|org|sa|io|dev)(?:/[^\s]*)?)",
            text,
            re.I,
        )
        if m and not re.search(r"(?:ابحث|search|find)", low):
            raw = m.group(1)
            url = raw if raw.startswith("http") else "https://" + raw
            return FastTask(
                "open_url",
                [{"tool": "browser", "action": "open_url", "arguments": {"url": url}}],
                "Explicit hostname open is deterministic.",
            )

        return None
