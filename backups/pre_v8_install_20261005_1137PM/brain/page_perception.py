from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.local_brain import LocalBrain


class PagePerception:
    """Builds a semantic world-model from an accessibility snapshot.

    The parser is deterministic-first. A local model is only asked to interpret
    ambiguous parts, preserving the original snapshot as evidence.
    """

    ROLE_RE = re.compile(r'uid=([^\s]+)\s+(\w+)\s+"([^"]*)"(?:\s+url="([^"]*)")?')
    ROOT_RE = re.compile(r'RootWebArea\s+"([^"]*)"\s+url="([^"]*)"')
    VALUE_RE = re.compile(r'value="([^"]*)"')
    PRICE_RE = re.compile(r'(?:SAR|AED|EGP|USD|EUR|ر\.س|د\.إ|ج\.م|ريال|درهم|جنيه|\$|€)\s*[\d][\d,\.]*|[\d][\d,\.]*\s*(?:ر\.س|SAR|AED|درهم|ريال)', re.I)

    def __init__(self, brain: LocalBrain | None = None):
        if brain is None:
            from brain.local_brain import LocalBrain
            brain = LocalBrain()
        self.brain = brain

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _country_currency(text: str, url: str) -> tuple[str | None, str | None]:
        low = (text + " " + url).casefold()
        country = None
        currency = None
        if any(x in low for x in ["saudi arabia", "السعودية", "ksa", "/sa/", "saudi-en"]):
            country = "Saudi Arabia"
        elif any(x in low for x in ["united arab emirates", "الإمارات", "uae", "/ae/", "uae-en", "dubai"]):
            country = "United Arab Emirates"
        elif any(x in low for x in ["egypt", "مصر", "egyp"]):
            country = "Egypt"
        if re.search(r"(?:SAR|ر\.س|ريال(?:\s+سعودي)?)", text, re.I) or "saudi-en" in url.casefold() or "amazon.sa" in url.casefold():
            currency = "SAR"
        elif re.search(r"(?:AED|د\.إ|درهم(?:\s+إماراتي)?)", text, re.I) or "uae-en" in url.casefold() or "amazon.ae" in url.casefold():
            currency = "AED"
        elif re.search(r"(?:EGP|ج\.م|جنيه(?:\s+مصري)?)", text, re.I):
            currency = "EGP"
        elif re.search(r"(?:USD|\$|دولار)", text, re.I):
            currency = "USD"
        elif re.search(r"(?:EUR|€|يورو)", text, re.I):
            currency = "EUR"
        return country, currency

    @staticmethod
    def _origin(url: str) -> str | None:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(str(url or ""))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return None
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        except Exception:
            return None

    @staticmethod
    def _page_type(title: str, url: str, text: str, elements: list[dict[str, Any]]) -> str:
        low = " ".join([title, url, text[:6000]]).casefold()
        # KAREEM_AGENT's own Flask UI is not a user website. Treat it as a
        # protected control surface so the agent can never mistake its chat
        # textbox for a website search box.
        origin = PagePerception._origin(url)
        if origin in {"http://127.0.0.1:5000", "http://localhost:5000"} or "kareem agent" in low:
            return "agent_control_ui"
        if any(x in low for x in ["login", "sign in", "تسجيل الدخول", "دخول"]):
            return "login"
        if any(x in low for x in ["checkout", "الدفع", "الدفع وإتمام الشراء"]):
            return "checkout"
        if "/search" in url.casefold() or "?q=" in url.casefold() or "search results" in low or "نتائج البحث" in low:
            return "search_results"
        if any(e.get("role") in {"textbox", "combobox"} for e in elements) and any(x in low for x in ["search", "بحث"]):
            return "search_home"
        if any(x in low for x in ["product", "المنتج", "أضف إلى السلة", "add to cart"]):
            return "product"
        if any(x in low for x in ["article", "publication", "مدونة", "blog"]):
            return "article"
        if len(elements) > 10 and any(e.get("role") == "main" for e in elements):
            return "app_or_content"
        return "unknown"

    def _parse(self, snapshot: str) -> dict[str, Any]:
        raw = str(snapshot or "")
        root = self.ROOT_RE.search(raw)
        title = root.group(1) if root else ""
        url = root.group(2) if root else ""

        elements: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = self.ROLE_RE.search(line)
            if not m:
                continue
            item = {
                "uid": m.group(1),
                "role": m.group(2),
                "name": self._normalize_text(m.group(3)),
                "url": self._normalize_text(m.group(4) or ""),
            }
            vm = self.VALUE_RE.search(line)
            if vm:
                item["value"] = vm.group(1)
            elements.append(item)

        visible = self._normalize_text(raw)
        links = [e for e in elements if e.get("role") == "link" and e.get("url")]
        fields = [e for e in elements if e.get("role") in {"textbox", "combobox", "searchfield"}]
        buttons = [e for e in elements if e.get("role") == "button"]
        external_links = [e for e in links if not e["url"].lower().startswith("https://www.google.")]
        text_lines = [self._normalize_text(x) for x in raw.splitlines() if x.strip()]
        price_lines = [line for line in text_lines if self.PRICE_RE.search(line)]
        repeated = Counter([e.get("role") for e in elements]).most_common()
        country, currency = self._country_currency(visible, url)
        page_type = self._page_type(title, url, visible, elements)

        search_fields = [e for e in fields if re.search(r"(?:search|بحث|ابحث|looking for|ماذا تبحث)", e.get("name", ""), re.I)]
        result_links = []
        for e in external_links:
            if not e.get("name"):
                continue
            if e["name"] in {"Privacy", "Help", "About", "Sign in", "تسجيل الدخول"}:
                continue
            result_links.append(e)
            if len(result_links) >= 12:
                break

        return {
            "url": url,
            "title": title,
            "domain": urlparse(url).netloc.lower(),
            "page_type": page_type,
            "country": country,
            "currency": currency,
            "interactive_count": len(elements),
            "role_counts": dict(repeated),
            "search_fields": search_fields[:5],
            "fields": fields[:20],
            "buttons": buttons[:25],
            "result_links": result_links,
            "price_lines": price_lines[:20],
            "text_excerpt": visible[:12000],
            "elements": elements[:180],
            "fingerprint": self.fingerprint({"url": url, "title": title, "elements": elements, "text": visible[:6000]}),
        }

    @staticmethod
    def fingerprint(model: dict[str, Any]) -> str:
        import hashlib
        basis = json.dumps({
            "url": model.get("url"),
            "title": model.get("title"),
            "page_type": model.get("page_type"),
            "country": model.get("country"),
            "currency": model.get("currency"),
            "elements": [
                (e.get("role"), e.get("name"), e.get("url"))
                for e in model.get("elements", [])[:80]
            ],
            "prices": model.get("price_lines", [])[:10],
        }, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()

    def perceive(self, snapshot: str, goal: dict[str, Any] | None = None) -> dict[str, Any]:
        model = self._parse(snapshot)
        goal = goal or {}

        # Only call the LLM for ambiguous interpretation / candidate extraction.
        if model["page_type"] in {"search_results", "product", "app_or_content", "unknown"} or goal.get("requires_data_collection"):
            compact = {
                "goal": {
                    "site": goal.get("site"),
                    "country": goal.get("country"),
                    "currency": goal.get("currency"),
                    "query": goal.get("query"),
                    "constraints": goal.get("constraints", {}),
                    "result_count": goal.get("result_count"),
                    "required_fields": goal.get("required_fields", []),
                },
                "page": {
                    "url": model["url"],
                    "title": model["title"],
                    "page_type": model["page_type"],
                    "country": model["country"],
                    "currency": model["currency"],
                    "price_lines": model["price_lines"],
                    "result_links": model["result_links"][:12],
                    "text_excerpt": model["text_excerpt"][:11000],
                    "elements": model["elements"][:140],
                },
                "rules": [
                    "Use only the supplied page evidence.",
                    "Do not invent prices, products, URLs, or page states.",
                    "When extracting candidates, include exact evidence snippets from the page.",
                    "If a value is not visible, set it to null.",
                    "For product/search pages, emit one candidate per visible product/result when possible, preserving the exact product name, visible price, currency, destination URL, and a short evidence snippet.",
                ],
            }
            prompt = """
You are the Page Perception module of an autonomous computer agent.
Interpret what is currently visible and relate it to the user's goal.
Return JSON only.

Return schema:
{
  "goal_relevance": 0.0,
  "state": "useful|irrelevant|blocked|ambiguous|ready_for_next_action",
  "search_value": null,
  "region_signal": null,
  "candidates": [
    {"name": null, "price": null, "currency": null, "url": null, "evidence": "", "confidence": 0.0}
  ],
  "missing_information": [],
  "useful_elements": [{"uid": "", "why": ""}]
}

PAGE INPUT:
""" + json.dumps(compact, ensure_ascii=False)
            try:
                raw = str(self.brain.ask(prompt) or "").strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
                raw = re.sub(r"\s*```$", "", raw).strip()
                try:
                    parsed = json.loads(raw)
                except Exception:
                    a, b = raw.find("{"), raw.rfind("}")
                    parsed = json.loads(raw[a:b + 1]) if a >= 0 and b > a else {}
                if isinstance(parsed, dict):
                    model["llm"] = parsed
            except Exception as exc:
                model["llm_error"] = str(exc)

        return model
