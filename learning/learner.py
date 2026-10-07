from __future__ import annotations

import re
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import httpx
from bs4 import BeautifulSoup

from knowledge.store import KnowledgeStore


class SiteLearner:
    def __init__(self, knowledge: KnowledgeStore | None = None) -> None:
        self.knowledge = knowledge or KnowledgeStore()
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "KAREEM_AGENT/4.0 (+local-agent-learning)"},
        )

    @staticmethod
    def _clean_text(html: str) -> tuple[str, str, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = " ".join(main.get_text(" ", strip=True).split())
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            if href:
                links.append(href)
        return title, text, links

    @staticmethod
    def _same_domain(root: str, other: str) -> bool:
        return urlparse(root).netloc.lower().split(":")[0] == urlparse(other).netloc.lower().split(":")[0]

    def learn_site(self, start_url: str, max_pages: int = 12, max_chars_per_page: int = 45000) -> dict:
        start_url = str(start_url).strip()
        if not re.match(r"^https?://", start_url, re.I):
            start_url = "https://" + start_url
        q = deque([start_url])
        seen: set[str] = set()
        learned: list[dict] = []
        errors: list[dict] = []

        while q and len(learned) < max(1, min(int(max_pages), 100)):
            url = urldefrag(q.popleft())[0]
            if url in seen:
                continue
            seen.add(url)
            if not self._same_domain(start_url, url):
                continue
            try:
                resp = self.client.get(url)
                resp.raise_for_status()
                title, text, links = self._clean_text(resp.text)
                text = text[:max_chars_per_page]
                if len(text) < 80:
                    continue
                domain = urlparse(url).netloc
                self.knowledge.add_document(
                    url=url,
                    title=title or url,
                    text=text,
                    domain=domain,
                    metadata={"learner": "site", "status_code": resp.status_code},
                )
                learned.append({"url": url, "title": title, "chars": len(text)})
                for href in links:
                    nxt = urldefrag(urljoin(url, href))[0]
                    if self._same_domain(start_url, nxt) and nxt not in seen:
                        q.append(nxt)
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})

        return {
            "success": bool(learned),
            "start_url": start_url,
            "pages_learned": len(learned),
            "learned": learned,
            "errors": errors[:20],
        }
