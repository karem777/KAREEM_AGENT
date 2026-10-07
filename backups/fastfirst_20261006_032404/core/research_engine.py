import json
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


class ResearchEngine:
    """Project research: GitHub search + README evidence + compatibility ranking."""

    def __init__(self, timeout=20):
        self.timeout = timeout

    def _get_json(self, url: str):
        req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "KAREEM_AGENT-COMPLETE"})
        with urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))

    def _get_text(self, url: str) -> str:
        req = Request(url, headers={"User-Agent": "KAREEM_AGENT-COMPLETE"})
        with urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", errors="ignore")

    def search_projects(self, query: str, max_results=8) -> dict[str, Any]:
        url = "https://api.github.com/search/repositories?q=" + quote(query) + "&sort=stars&order=desc&per_page=" + str(min(max_results, 20))
        data = self._get_json(url)
        items = []
        for x in data.get("items", [])[:max_results]:
            items.append({
                "name": x.get("full_name"),
                "url": x.get("html_url"),
                "stars": x.get("stargazers_count", 0),
                "forks": x.get("forks_count", 0),
                "language": x.get("language"),
                "updated_at": x.get("updated_at"),
                "description": x.get("description"),
                "default_branch": x.get("default_branch", "main"),
            })
        return {"success": True, "query": query, "results": items}

    def inspect_project(self, full_name: str, default_branch="main") -> dict[str, Any]:
        repo = self._get_json(f"https://api.github.com/repos/{full_name}")
        branch = repo.get("default_branch") or default_branch
        readme_url = f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
        try:
            readme = self._get_text(readme_url)
        except Exception:
            readme = ""
        return {
            "success": True,
            "name": repo.get("full_name"),
            "url": repo.get("html_url"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "description": repo.get("description"),
            "default_branch": branch,
            "readme_excerpt": self._excerpt(readme),
        }

    @staticmethod
    def _excerpt(text, limit=12000):
        return text[:limit]

    def rank_projects(self, projects: list[dict[str, Any]], requirements: dict[str, Any] | None = None):
        requirements = requirements or {}
        desired_lang = str(requirements.get("language", "python")).lower()
        desired_model = str(requirements.get("model", "qwen3:8b")).lower()
        desired_platform = str(requirements.get("platform", "windows")).lower()
        scored = []
        for p in projects:
            text = json.dumps(p, ensure_ascii=False).lower()
            score = 0.0
            score += min(float(p.get("stars", 0)) / 5000.0, 8.0)
            score += 3.0 if str(p.get("language") or "").lower() == desired_lang else 0.0
            score += 2.0 if desired_model in text or "qwen" in text else 0.0
            score += 2.0 if desired_platform in text or "desktop" in text or "windows" in text else 0.0
            score += 1.0 if "agent" in text or "browser" in text or "computer use" in text else 0.0
            scored.append({**p, "compatibility_score": round(score, 3)})
        scored.sort(key=lambda x: x["compatibility_score"], reverse=True)
        return scored

    def deep_research(self, queries: list[str], requirements: dict[str, Any] | None = None, time_budget_minutes=60, max_per_query=6):
        start = time.time()
        projects = {}
        evidence = []
        for query in queries[:12]:
            if time.time() - start > time_budget_minutes * 60:
                break
            result = self.search_projects(query, max_results=max_per_query)
            for item in result.get("results", []):
                projects[item["name"]] = item
        inspected = []
        for name, item in list(projects.items())[:20]:
            if time.time() - start > time_budget_minutes * 60:
                break
            try:
                details = self.inspect_project(name, item.get("default_branch", "main"))
                inspected.append(details)
            except Exception as exc:
                inspected.append({**item, "inspect_error": str(exc)})
        ranked = self.rank_projects(inspected, requirements)
        for item in ranked[:10]:
            evidence.append({"source": item.get("url"), "project": item.get("name"), "score": item.get("compatibility_score"), "readme_excerpt": item.get("readme_excerpt", "")[:2200]})
        return {
            "success": True,
            "elapsed_seconds": round(time.time() - start, 2),
            "time_budget_minutes": time_budget_minutes,
            "project_count": len(inspected),
            "ranked_projects": ranked[:10],
            "evidence": evidence,
        }
