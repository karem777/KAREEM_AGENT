from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


class ToolHandoffRouter:
    """Generic discovery->execution handoff and loop prevention.

    Web search discovers destinations. Browser executes interactive website work.
    The router never contains site-specific rules; it uses the current goal,
    observed results, and action history.
    """

    def __init__(self, goal: dict[str, Any], history: list[dict[str, Any]]):
        self.goal = goal or {}
        self.history = history or []

    @staticmethod
    def _tool_events(history: list[dict[str, Any]], tool: str | None = None):
        rows = [h for h in history if h.get("role") == "tool"]
        if tool:
            rows = [h for h in rows if h.get("tool") == tool]
        return rows

    @staticmethod
    def _last(history: list[dict[str, Any]], tool: str | None = None, action: str | None = None):
        rows = ToolHandoffRouter._tool_events(history, tool)
        if action:
            rows = [h for h in rows if h.get("action") == action]
        return rows[-1] if rows else None

    @staticmethod
    def _url_from_result(item: dict[str, Any] | None) -> str:
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            return ""
        direct = str(result.get("url") or "").strip()
        if direct.startswith(("http://", "https://")):
            return direct
        text = str(result.get("text") or "")
        import re
        m = re.search(r"https?://[^\s\]\)\"']+", text)
        return m.group(0) if m else ""

    def last_web_search(self) -> dict[str, Any] | None:
        return self._last(self.history, "web", "search")

    def last_browser_action(self) -> dict[str, Any] | None:
        return self._last(self.history, "browser")

    def discovery_handoff(self) -> str | None:
        item = self.last_web_search()
        if not item:
            return None
        result = item.get("result") or {}
        if not isinstance(result, dict) or not result.get("success"):
            return None
        results = result.get("results")
        if not isinstance(results, list):
            return None
        site = str(self.goal.get("site") or "").casefold()
        country = str(self.goal.get("country") or "").casefold()
        country_tokens = {
            "saudi arabia": ["saudi", "ksa", "arabia", "السعود"],
            "united arab emirates": ["uae", "emirates", "dubai", "الإمارات", "الامارات"],
            "egypt": ["egypt", "مصر", "egyp"],
        }.get(country, [country] if country else [])
        ranked: list[tuple[int, str]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            title = str(row.get("title") or "").casefold()
            if not url.startswith(("http://", "https://")):
                continue
            hay = f"{title} {url.casefold()}"
            score = 0
            if site and site in hay:
                score += 20
            if any(tok and tok in hay for tok in country_tokens):
                score += 12
            if country == "saudi arabia" and "saudi-en" in hay:
                score += 8
            if country == "united arab emirates" and "uae-en" in hay:
                score += 8
            if "/help" not in url and "login" not in url:
                score += 1
            ranked.append((score, url))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None

    def searched_same_query(self) -> bool:
        last = self.last_web_search()
        if not last:
            return False
        query = str((last.get("arguments") or {}).get("query") or "").strip().casefold()
        if not query:
            return False
        # A successful same-query search already produced a handoff candidate.
        # Do not emit the search again unless there is explicit evidence it failed.
        result = last.get("result") or {}
        return bool(isinstance(result, dict) and result.get("success"))


    def recent_search_failures(self, query: str | None = None) -> int:
        rows = [r for r in self._tool_events(self.history, "web") if r.get("action") == "search"]
        if query is not None:
            q = " ".join(str(query).strip().casefold().split())
            rows = [
                r for r in rows
                if " ".join(str((r.get("arguments") or {}).get("query") or "").strip().casefold().split()) == q
            ]
        count = 0
        for row in reversed(rows):
            result = row.get("result") or {}
            if isinstance(result, dict) and not result.get("success"):
                count += 1
            else:
                break
        return count

    def browser_is_active(self) -> bool:
        return bool(self.last_browser_action())

    def target_domain_hint(self) -> str:
        site = str(self.goal.get("site") or "").casefold()
        aliases = {
            "noon": ["noon.com"],
            "amazon": ["amazon.sa", "amazon.com"],
            "aliexpress": ["aliexpress.com"],
            "booking": ["booking.com"],
            "github": ["github.com"],
        }
        return aliases.get(site, [site])[0] if site else ""

    def current_browser_url(self) -> str:
        item = self.last_browser_action()
        return self._url_from_result(item)

    def browser_matches_target(self) -> bool:
        url = self.current_browser_url().casefold()
        hint = self.target_domain_hint().casefold()
        return bool(hint and hint in url)
