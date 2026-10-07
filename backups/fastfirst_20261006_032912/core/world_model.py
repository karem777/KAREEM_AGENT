import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse, parse_qs


@dataclass
class PageElement:
    uid: str = ""
    role: str = ""
    name: str = ""
    url: str = ""
    value: str = ""
    semantic: list[str] = field(default_factory=list)


@dataclass
class WorldState:
    url: str | None = None
    origin: str | None = None
    title: str | None = None
    domain: str | None = None
    page_type: str = "unknown"
    page_id: Any = None
    text: str = ""
    elements: list[PageElement] = field(default_factory=list)
    result_links: list[PageElement] = field(default_factory=list)
    search_fields: list[PageElement] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def compact(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "origin": self.origin,
            "title": self.title,
            "domain": self.domain,
            "page_type": self.page_type,
            "page_id": self.page_id,
            "facts": self.facts,
            "search_fields": [asdict(x) for x in self.search_fields[:8]],
            "result_links": [asdict(x) for x in self.result_links[:12]],
            "fingerprint": self.fingerprint,
        }


class WorldModel:
    SEARCH_DOMAINS = {"google.com", "www.google.com", "bing.com", "www.bing.com", "duckduckgo.com", "search.brave.com"}

    def __init__(self):
        self.state = WorldState()

    @staticmethod
    def _origin(url: str | None) -> str | None:
        if not url:
            return None
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}"

    @staticmethod
    def _element_match(line: str) -> PageElement | None:
        m = re.search(r'uid=([^\s]+)\s+(\w+)\s+"([^"]*)"(?:\s+url="([^"]*)")?', line)
        if not m:
            return None
        uid, role, name, url = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        return PageElement(uid=uid, role=role.lower(), name=name, url=url)

    def observe(self, observation: Any) -> WorldState:
        if isinstance(observation, str):
            data = {"text": observation}
        elif isinstance(observation, dict):
            data = observation
        else:
            data = {"text": repr(observation)}

        nested = data.get("result") if isinstance(data.get("result"), dict) else {}
        merged = dict(nested)
        merged.update(data)
        text = str(merged.get("snapshot") or merged.get("text") or "")
        url = merged.get("actual_url") or merged.get("url") or self._url_from_text(text)
        if not url:
            url = self.state.url
        title = merged.get("title") or self._title_from_text(text) or self.state.title
        domain = urlparse(url).netloc.lower() if url else self.state.domain
        page_type = self._classify(url, title, text)

        elements = []
        for line in text.splitlines():
            el = self._element_match(line)
            if el:
                low = (el.name + " " + el.role).lower()
                if any(k in low for k in ["search", "بحث", "query", "recherche"]):
                    el.semantic.append("search_candidate")
                if el.role in {"textbox", "combobox", "searchbox"}:
                    el.semantic.append("text_input")
                if el.role == "link" and el.url:
                    el.semantic.append("navigation_link")
                elements.append(el)

        search_fields = [e for e in elements if "search_candidate" in e.semantic or e.role in {"searchbox", "combobox"}]
        result_links = [e for e in elements if e.role == "link" and e.url and "navigation_link" in e.semantic]
        facts = {
            "has_search_field": bool(search_fields),
            "has_form": " form" in text.lower(),
            "has_results": page_type == "search_results" or ("search?" in (url or "") and len(result_links) >= 2),
            "query": self._query_from_url(url),
            "contains_price": bool(re.search(r"(?:SAR|\$|€|£|ريال|ر\.س|\d+[,.]\d{2})", text, re.I)),
            "contains_login": bool(re.search(r"\b(log in|sign in|تسجيل الدخول)\b", text, re.I)),
        }
        fingerprint_payload = {"url": url, "title": title, "page_type": page_type, "links": [(x.name, x.url) for x in result_links[:20]], "text": re.sub(r"\s+", " ", text)[:2500]}
        fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

        if url and url != self.state.url:
            self.state.evidence.append({"type": "navigation", "from": self.state.url, "to": url})
        self.state = WorldState(
            url=url,
            origin=self._origin(url),
            title=title,
            domain=domain,
            page_type=page_type,
            page_id=merged.get("page_id") or self.state.page_id,
            text=text,
            elements=elements,
            result_links=result_links,
            search_fields=search_fields,
            facts=facts,
            fingerprint=fingerprint,
            evidence=self.state.evidence[-30:],
        )
        return self.state

    @staticmethod
    def _url_from_text(text: str) -> str | None:
        m = re.search(r"(?:navigated to|url=\"|URL:)\s*(https?://[^\s\"]+)", text, re.I)
        return m.group(1).rstrip(".,") if m else None

    @staticmethod
    def _title_from_text(text: str) -> str | None:
        m = re.search(r'RootWebArea\s+"([^"]+)"', text)
        return m.group(1) if m else None

    @classmethod
    def _classify(cls, url: str | None, title: str | None, text: str) -> str:
        low_url = (url or "").lower()
        low_title = (title or "").lower()
        low_text = text.lower()
        if any(low_url.startswith(x) for x in ["http://127.0.0.1:5000", "http://127.0.0.1:5001"]):
            return "agent_control_ui"
        if any(d in low_url for d in cls.SEARCH_DOMAINS) and ("/search" in low_url or "q=" in low_url):
            return "search_results"
        if any(d in low_url for d in cls.SEARCH_DOMAINS) and ("google" in low_title or "bing" in low_title or "search" in low_text[:1000]):
            return "search_home"
        if "login" in low_url or re.search(r"\b(sign in|log in|تسجيل الدخول)\b", low_text):
            return "login"
        if "checkout" in low_url or "cart" in low_url or "السلة" in low_text:
            return "checkout_or_cart"
        if re.search(r"\b(product|products|add to cart|buy now|shop|price)\b", low_text[:6000]):
            return "commerce"
        if "docs" in low_url or "documentation" in low_title or "api reference" in low_text[:2000]:
            return "documentation"
        if "github.com" in low_url and "/search" in low_url:
            return "repository_search"
        if "github.com" in low_url and "/" in low_url:
            return "repository_or_code"
        return "generic_web"

    @staticmethod
    def _query_from_url(url: str | None) -> str | None:
        if not url:
            return None
        try:
            q = parse_qs(urlparse(url).query)
            return (q.get("q") or q.get("query") or [None])[0]
        except Exception:
            return None
