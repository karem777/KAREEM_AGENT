import importlib
from pathlib import Path

from tools.windows_complete import WindowsTool
from tools.developer_complete import DeveloperTool


class CompleteRegistry:
    def __init__(self, workspace):
        self.tools = {}
        self.workspace = str(workspace)
        self._register_optional("filesystem", "tools.filesystem", "FileSystemTool", workspace)
        self._register_optional("memory", "tools.memory", "MemoryTool")
        self._register_optional("web", "tools.web", "WebTool")
        self._register_optional("system", "tools.system", "SystemTool")
        self._register_optional("browser", "tools.browser", "BrowserTool")
        self._register_optional("desktop", "tools.desktop", "DesktopTool")
        self._register_optional("computer", "tools.local_computer", "LocalComputerTool")
        self.register(WindowsTool())
        self.register(DeveloperTool(workspace))
        self.register(_ExperienceProxy(workspace))
        self.register(_ResearchProxy())

    def _register_optional(self, name, module_name, cls_name, *args):
        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, cls_name)
            obj = cls(*args)
            self.register(obj)
        except Exception as exc:
            # Optional backends are intentionally non-fatal. The caller can see the list in describe().
            self.tools.setdefault("_load_errors", {})[name] = str(exc)

    def register(self, tool):
        self.tools[tool.name] = tool

    def get(self, name):
        return self.tools.get(name)

    def describe(self):
        out = {}
        for name, tool in self.tools.items():
            if name == "_load_errors":
                continue
            try:
                d = tool.describe()
                # Keep descriptions compact to protect Qwen's context.
                actions = d.get("actions", {})
                out[name] = {"description": d.get("description", name), "actions": {k: v.get("description", "") for k, v in actions.items()}}
            except Exception:
                out[name] = {"description": getattr(tool, "description", name), "actions": {}}
        if self.tools.get("_load_errors"):
            out["_load_errors"] = self.tools["_load_errors"]
        return out


class _ResearchProxy:
    name = "research"
    description = "Search, inspect and rank external open-source projects with evidence."

    def __init__(self):
        from core.research_engine import ResearchEngine
        self.engine = ResearchEngine()

    def search_projects(self, query, max_results=8):
        return self.engine.search_projects(query, max_results=max_results)

    def inspect_project(self, full_name, default_branch="main"):
        return self.engine.inspect_project(full_name, default_branch=default_branch)

    def rank_projects(self, projects, requirements=None):
        return {"success": True, "projects": self.engine.rank_projects(projects, requirements)}

    def deep_research(self, queries, requirements=None, time_budget_minutes=60, max_per_query=6):
        return self.engine.deep_research(queries, requirements=requirements, time_budget_minutes=time_budget_minutes, max_per_query=max_per_query)

    def describe(self):
        return {"name": self.name, "description": self.description, "actions": {
            "search_projects": {"description": "Search GitHub repositories.", "parameters": {"query": {"type": "string", "required": True}, "max_results": {"type": "integer", "required": False}}},
            "inspect_project": {"description": "Read repository metadata and README evidence.", "parameters": {"full_name": {"type": "string", "required": True}, "default_branch": {"type": "string", "required": False}}},
            "rank_projects": {"description": "Rank gathered projects for the target model/platform.", "parameters": {"projects": {"type": "array", "required": True}, "requirements": {"type": "object", "required": False}}},
            "deep_research": {"description": "Run multi-query project research with a time budget up to 60 minutes.", "parameters": {"queries": {"type": "array", "required": True}, "requirements": {"type": "object", "required": False}, "time_budget_minutes": {"type": "number", "required": False}, "max_per_query": {"type": "integer", "required": False}}},
        }}


class _ExperienceProxy:
    name = "experience"
    description = "Recall and store successful/failing trajectories and lessons."

    def __init__(self, workspace):
        from core.experience import ExperienceStore
        self.store = ExperienceStore(Path(workspace) / "agent_memory")

    def recent(self, limit=6):
        return {"success": True, "experiences": self.store.recent(limit)}

    def search(self, query, limit=8):
        return {"success": True, "experiences": self.store.search(query, limit)}

    def save(self, task, lesson="", outcome=""):
        self.store.append({"goal": task, "lesson": lesson, "outcome": outcome})
        return {"success": True}

    def describe(self):
        return {"name": self.name, "description": self.description, "actions": {
            "recent": {"description": "Recall recent experiences.", "parameters": {"limit": {"type": "integer", "required": False}}},
            "search": {"description": "Search past experiences semantically-ish by tokens.", "parameters": {"query": {"type": "string", "required": True}, "limit": {"type": "integer", "required": False}}},
            "save": {"description": "Store a trajectory lesson.", "parameters": {"task": {"type": "string", "required": True}, "lesson": {"type": "string", "required": False}, "outcome": {"type": "string", "required": False}}},
        }}













