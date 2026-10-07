from __future__ import annotations

import re
from typing import Any


class BrowserGoalController:
    """Deterministic guardrail for generic multi-step browser search tasks.

    It is intentionally site-agnostic: it understands the logical dependency
    between open -> inspect -> fill search -> submit -> inspect results -> click
    first result, but it does not contain site-specific workflows.
    """

    SITE_ALIASES = {
        "google": "https://www.google.com",
        "جوجل": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "يوتيوب": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "جيميل": "https://mail.google.com",
        "github": "https://github.com",
        "جيت هب": "https://github.com",
        "chatgpt": "https://chatgpt.com",
        "شات جي بي تي": "https://chatgpt.com",
        "whatsapp": "https://web.whatsapp.com",
        "واتساب": "https://web.whatsapp.com",
        "amazon": "https://www.amazon.sa/",
        "امازون": "https://www.amazon.sa/",
        "أمازون": "https://www.amazon.sa/",
    }

    OPEN_RE = re.compile(
        r"(?:افتح|ادخل(?:\s+على)?|روح(?:\s+على)?|خش(?:\s+على)?|go\s+to|open|visit)\s+(?:موقع\s+)?(?P<site>[^،,؛;\n]+)",
        re.IGNORECASE,
    )
    SEARCH_RE = re.compile(
        r"(?:ابحث(?:\s+لي)?|دور(?:\s+لي)?|search|find)\s+(?:عن|على|في|for)?\s*(?P<query>.+?)(?=(?:\s+(?:وا?فتح|افتح|ثم|وبعدين|and\s+open|then\s+open)\b)|$)",
        re.IGNORECASE,
    )
    FIRST_RESULT_RE = re.compile(
        r"(?:افتح|ادخل|روح|خش|open)\s+(?:أول|اول|first)\s+(?:نتيجة|result)|(?:أول|اول)\s+(?:نتيجة|result)",
        re.IGNORECASE,
    )

    def parse(self, user_message: str) -> dict[str, Any] | None:
        text = str(user_message or "").strip()
        query_match = self.SEARCH_RE.search(text)
        first_result = bool(self.FIRST_RESULT_RE.search(text))
        if not query_match:
            return None

        query = query_match.group("query").strip(" .،,؛;")
        query = re.sub(
            r"(?:\s+(?:وا?فتح|ثم|وبعدين|and\s+open|then\s+open).*)$",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip(" .،,؛;")
        if not query:
            return None

        url = None
        url_match = re.search(r"https?://[^\s]+", text, flags=re.IGNORECASE)
        if url_match:
            url = url_match.group(0).rstrip(".,،)")
        if not url:
            open_match = self.OPEN_RE.search(text)
            if open_match:
                site_text = open_match.group("site").strip()
                site_text = re.split(r"\s+و(?=\S)|\s+ثم(?=\S)|\s+(?:and|then)\s+", site_text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                key = site_text.casefold()
                url = self.SITE_ALIASES.get(key)
                if not url and "." in site_text and " " not in site_text:
                    url = "https://" + site_text.rstrip("/")

        return {"query": query, "url": url, "first_result": first_result}

    @staticmethod
    def _browser_history(history: list[dict]) -> list[dict]:
        return [h for h in history if h.get("role") == "tool" and h.get("tool") == "browser"]

    @staticmethod
    def _result_ok(item: dict | None) -> bool:
        result = item.get("result") if isinstance(item, dict) else None
        return bool(isinstance(result, dict) and result.get("success", False))

    @staticmethod
    def _result_url(item: dict | None) -> str:
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            return ""

        direct = str(result.get("url") or "").strip()
        if direct:
            return direct

        # Browser inspect responses often keep the current URL only inside the
        # accessibility snapshot. Extract it so the deterministic controller can
        # recognize that a search has already been submitted.
        snapshot = str(result.get("snapshot") or "")
        match = re.search(r'\burl=\"([^\"]+)\"', snapshot, flags=re.IGNORECASE)
        if match:
            return match.group(1)

        text = str(result.get("text") or "")
        match = re.search(r'\b(?:url|URL)[:=]\s*[\"\']?([^\s\"\']+)', text)
        if match:
            return match.group(1)

        return ""

    def next_action(self, user_message: str, history: list[dict]) -> dict[str, Any] | None:
        intent = self.parse(user_message)
        if not intent:
            return None

        bh = self._browser_history(history)
        if not bh:
            if intent.get("url"):
                return {"tool": "browser", "action": "open_url", "arguments": {"url": intent["url"]}}
            return None

        last = bh[-1]
        last_action = str(last.get("action") or "")
        last_ok = self._result_ok(last)
        current_url = self._result_url(last)

        if not last_ok:
            # Let the general planner diagnose failures rather than forcing a
            # blind repeat.
            return None

        if last_action == "open_url":
            return {"tool": "browser", "action": "inspect", "arguments": {}}

        if last_action == "inspect":
            # If this inspect immediately follows the requested click, verify the
            # destination and finish instead of starting the search over again.
            if len(bh) >= 2:
                previous = bh[-2]
                if previous.get("action") == "click" and self._result_ok(previous):
                    return {"type": "chat", "content": "تم فتح أول نتيجة والتحقق من الانتقال إليها."}

            # A URL containing /search or ?q= is a strong generic signal that a
            # submitted search now has results. At that point, first-result means
            # first result in that result context, not first link on the page.
            search_context = ("/search" in current_url.lower() or "?q=" in current_url.lower())
            if search_context:
                if intent.get("first_result"):
                    return {"tool": "browser", "action": "click", "arguments": {"first_result": True}}
                return {"type": "chat", "content": "تم تنفيذ البحث بنجاح والتحقق من صفحة النتائج."}
            return {"tool": "browser", "action": "fill", "arguments": {"target": "search", "value": intent["query"]}}

        if last_action == "fill":
            return {"tool": "browser", "action": "press_key", "arguments": {"key": "Enter"}}

        if last_action == "press_key":
            return {"tool": "browser", "action": "inspect", "arguments": {}}

        if last_action == "click":
            # A successful click is enough to trigger one verification observation;
            # the next turn will become a final chat once the URL leaves the search page.
            if "/search" not in current_url.lower() and "?q=" not in current_url.lower():
                return {"tool": "browser", "action": "inspect", "arguments": {}}
            return {"tool": "browser", "action": "inspect", "arguments": {}}

        return None
