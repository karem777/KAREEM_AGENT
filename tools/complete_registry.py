import importlib
import inspect
import pkgutil
from pathlib import Path

from tools.windows_complete import WindowsTool
from tools.developer_complete import DeveloperTool


COMPUTER_CLASS_NAMES = {
    "ComputerTool",
    "WindowsComputerTool",
    "WindowsOperator",
    "LocalComputerTool",
    "ComputerOperator",
    "WindowsOperatorTool",
}


class CompleteRegistry:

    def __init__(self, workspace):
        self.tools = {}
        self.workspace = str(workspace)

        self._register_optional(
            "filesystem",
            "tools.filesystem",
            "FileSystemTool",
            workspace,
        )

        self._register_optional(
            "memory",
            "tools.memory",
            "MemoryTool",
        )

        self._register_optional(
            "web",
            "tools.web",
            "WebTool",
        )

        self._register_optional(
            "system",
            "tools.system",
            "SystemTool",
        )

        self._register_optional(
            "browser",
            "tools.browser",
            "BrowserTool",
        )

        self._register_optional(
            "desktop",
            "tools.desktop",
            "DesktopTool",
        )

        self._register_optional(
            "learning",
            "tools.learning",
            "LearningTool",
        )

        self._register_universal_computer()

        self.register(
            WindowsTool()
        )

        self.register(
            DeveloperTool(workspace)
        )

        self.register(
            _ExperienceProxy(workspace)
        )

        self.register(
            _ResearchProxy()
        )

    # ========================================================
    # Optional tools
    # ========================================================

    def _register_optional(
        self,
        name,
        module_name,
        cls_name,
        *args,
    ):
        try:
            module = importlib.import_module(
                module_name
            )

            cls = getattr(
                module,
                cls_name,
            )

            obj = cls(*args)

            self.register(obj)

        except Exception as exc:
            self.tools.setdefault(
                "_load_errors",
                {},
            )[name] = str(exc)

    # ========================================================
    # Universal computer discovery
    # ========================================================

    def _register_universal_computer(self):

        candidates = [
            (
                "tools",
                "windows_operator",
            ),
            (
                "tools",
                "computer",
            ),
            (
                "tools",
                "computer_tool",
            ),
            (
                "tools",
                "windows_computer",
            ),
            (
                "tools",
                "computer_use",
            ),
            (
                "core",
                "windows_operator",
            ),
            (
                "core",
                "computer",
            ),
            (
                "core",
                "computer_tool",
            ),
            (
                "core",
                "windows_computer",
            ),
            (
                "core",
                "computer_use",
            ),
        ]

        # Discover other likely modules.
        for package_name, package_path in [
            (
                "tools",
                Path(__file__).resolve().parent,
            ),
            (
                "core",
                Path(__file__).resolve().parent.parent / "core",
            ),
        ]:

            if not package_path.exists():
                continue

            try:
                for module in pkgutil.iter_modules(
                    [str(package_path)]
                ):
                    lower = module.name.lower()

                    if (
                        "computer" in lower
                        or "windows_operator" in lower
                    ):
                        pair = (
                            package_name,
                            module.name,
                        )

                        if pair not in candidates:
                            candidates.append(pair)

            except Exception:
                pass

        for package_name, module_name in candidates:

            try:
                module = importlib.import_module(
                    f"{package_name}.{module_name}"
                )
            except Exception:
                continue

            for cls_name, cls in inspect.getmembers(
                module,
                inspect.isclass,
            ):

                if cls.__module__ != module.__name__:
                    continue

                declared_name = str(
                    getattr(
                        cls,
                        "name",
                        "",
                    )
                    or ""
                ).strip().lower()

                if (
                    cls_name not in COMPUTER_CLASS_NAMES
                    and declared_name not in {
                        "computer",
                        "windows_operator",
                    }
                ):
                    continue

                try:
                    obj = cls()

                    description = obj.describe()

                    actions = (
                        description.get(
                            "actions",
                            {},
                        )
                        if isinstance(
                            description,
                            dict,
                        )
                        else {}
                    )

                    action_names = set(
                        actions.keys()
                    )

                    # Universal operator must provide
                    # observation + actual UI interaction.
                    if (
                        "inspect" in action_names
                        and (
                            {
                                "click_control",
                                "set_text",
                                "invoke_control",
                                "click",
                            }
                            & action_names
                        )
                    ):
                        obj.name = "computer"

                        self.tools["computer"] = obj

                        # Never let the weaker desktop backend shadow it.
                        self.tools.pop(
                            "desktop",
                            None,
                        )

                        return

                except Exception:
                    continue

        # Compatibility fallback only.
        # This is NOT treated as the preferred universal operator.
        if "desktop" in self.tools:

            obj = self.tools.pop(
                "desktop"
            )

            obj.name = "computer"

            self.tools["computer"] = obj

    # ========================================================
    # Registry
    # ========================================================

    def register(self, tool):
        self.tools[tool.name] = tool

    def get(self, name):

        aliases = {
            "desktop": "computer",
            "pc": "computer",
            "windows_operator": "computer",
            "computer_tool": "computer",
        }

        raw = str(
            name or ""
        ).strip()

        canonical = aliases.get(
            raw.lower(),
            raw,
        )

        return self.tools.get(
            canonical
        )

    # ========================================================
    # Full tool schema
    # ========================================================

    @staticmethod
    def _annotation_type(annotation):
        if annotation is inspect._empty:
            return "string"

        raw = str(annotation)

        lower = raw.lower()

        if "bool" in lower:
            return "boolean"

        if "int" in lower:
            return "integer"

        if "float" in lower:
            return "number"

        if "list" in lower or "tuple" in lower:
            return "array"

        if "dict" in lower or "mapping" in lower:
            return "object"

        return "string"

    def _signature_parameters(self, tool, action_name):
        method = getattr(tool, action_name, None)

        if not callable(method):
            return {}

        try:
            signature = inspect.signature(method)
        except Exception:
            return {}

        parameters = {}

        for name, param in signature.parameters.items():

            if name in {"self", "cls"}:
                continue

            if param.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue

            parameters[name] = {
                "type": self._annotation_type(
                    param.annotation
                ),
                "required": (
                    param.default
                    is inspect._empty
                ),
            }

        return parameters

    def describe_for_planner(self, allowed_tools=None):
        """Compact live capability catalog for local-model planning.

        Keep capability names, action names, and parameter contracts while
        removing verbose metadata that wastes the local model context window.
        """
        full = self.describe()
        allowed = set(allowed_tools or full.keys())
        compact = {}

        for name, description in full.items():
            if name == "_load_errors" or name not in allowed:
                continue
            actions = description.get("actions", {}) if isinstance(description, dict) else {}
            compact_actions = {}

            for action_name, spec in actions.items():
                if not isinstance(spec, dict):
                    spec = {"description": str(spec)}
                params = spec.get("parameters", {})
                compact_params = {}

                if isinstance(params, dict):
                    for param_name, param_spec in params.items():
                        if isinstance(param_spec, dict):
                            compact_params[param_name] = {
                                "type": param_spec.get("type", "string"),
                                "required": bool(param_spec.get("required", False)),
                            }

                compact_actions[action_name] = {
                    "description": str(spec.get("description", ""))[:120],
                    "parameters": compact_params,
                }

            compact[name] = {
                "description": str(description.get("description", name))[:240],
                "actions": compact_actions,
            }

        return compact

    def describe(self):
        out = {}

        for name, tool in self.tools.items():

            if name == "_load_errors":
                continue

            try:
                description = tool.describe()

                actions = (
                    description.get(
                        "actions",
                        {},
                    )
                    if isinstance(
                        description,
                        dict,
                    )
                    else {}
                )

                normalized = {}

                for action_name, spec in actions.items():

                    if not isinstance(
                        spec,
                        dict,
                    ):
                        spec = {
                            "description": str(
                                spec
                            )
                        }

                    declared_parameters = spec.get(
                        "parameters"
                    )

                    # Some of the existing Computer Operator actions
                    # expose descriptions but don't provide a parameter
                    # schema. Generate one directly from the real method.
                    if not isinstance(
                        declared_parameters,
                        dict,
                    ) or not declared_parameters:

                        declared_parameters = (
                            self._signature_parameters(
                                tool,
                                action_name,
                            )
                        )

                    normalized[
                        action_name
                    ] = {
                        "description": spec.get(
                            "description",
                            "",
                        ),
                        "parameters": (
                            declared_parameters
                        ),
                    }

                    for key in (
                        "returns",
                        "examples",
                        "notes",
                    ):
                        if key in spec:
                            normalized[
                                action_name
                            ][key] = spec[key]

                out[name] = {
                    "description": (
                        description.get(
                            "description",
                            name,
                        )
                        if isinstance(
                            description,
                            dict,
                        )
                        else name
                    ),
                    "actions": normalized,
                }

            except Exception as exc:

                out[name] = {
                    "description": getattr(
                        tool,
                        "description",
                        name,
                    ),
                    "actions": {},
                }

        if self.tools.get(
            "_load_errors"
        ):
            out[
                "_load_errors"
            ] = self.tools[
                "_load_errors"
            ]

        return out
class _ExperienceProxy:

    name = "experience"

    description = (
        "Recall and store successful/failing "
        "trajectories and lessons."
    )

    def __init__(self, workspace):
        from core.experience import ExperienceStore

        self.store = ExperienceStore(
            Path(workspace)
            / "agent_memory"
        )

    def recent(self, limit=6):

        return {
            "success": True,
            "experiences": self.store.recent(
                limit
            ),
        }

    def search(self, query, limit=8):

        return {
            "success": True,
            "experiences": self.store.search(
                query,
                limit,
            ),
        }

    def save(
        self,
        task,
        lesson="",
        outcome="",
    ):

        self.store.append(
            {
                "goal": task,
                "lesson": lesson,
                "outcome": outcome,
            }
        )

        return {
            "success": True
        }

    def describe(self):

        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "recent": {
                    "description": (
                        "Recall recent experiences."
                    ),
                    "parameters": {
                        "limit": {
                            "type": "integer",
                            "required": False,
                        }
                    },
                },
                "search": {
                    "description": (
                        "Search previous experiences."
                    ),
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True,
                        },
                        "limit": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "save": {
                    "description": (
                        "Store a trajectory lesson."
                    ),
                    "parameters": {
                        "task": {
                            "type": "string",
                            "required": True,
                        },
                        "lesson": {
                            "type": "string",
                            "required": False,
                        },
                        "outcome": {
                            "type": "string",
                            "required": False,
                        },
                    },
                },
            },
        }


# ============================================================
# Research
# ============================================================

class _ResearchProxy:

    name = "research"

    description = (
        "Search, inspect and rank external "
        "open-source projects with evidence."
    )

    def __init__(self):
        from core.research_engine import ResearchEngine

        self.engine = ResearchEngine()

    def search_projects(
        self,
        query,
        max_results=8,
    ):

        return self.engine.search_projects(
            query,
            max_results=max_results,
        )

    def inspect_project(
        self,
        full_name,
        default_branch="main",
    ):

        return self.engine.inspect_project(
            full_name,
            default_branch=default_branch,
        )

    def rank_projects(
        self,
        projects,
        requirements=None,
    ):

        return {
            "success": True,
            "projects": self.engine.rank_projects(
                projects,
                requirements,
            ),
        }

    def deep_research(
        self,
        queries,
        requirements=None,
        time_budget_minutes=60,
        max_per_query=6,
    ):

        return self.engine.deep_research(
            queries,
            requirements=requirements,
            time_budget_minutes=time_budget_minutes,
            max_per_query=max_per_query,
        )

    def describe(self):

        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search_projects": {
                    "description": (
                        "Search GitHub repositories."
                    ),
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True,
                        },
                        "max_results": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "inspect_project": {
                    "description": (
                        "Read repository metadata "
                        "and README evidence."
                    ),
                    "parameters": {
                        "full_name": {
                            "type": "string",
                            "required": True,
                        },
                        "default_branch": {
                            "type": "string",
                            "required": False,
                        },
                    },
                },
                "rank_projects": {
                    "description": (
                        "Rank gathered projects."
                    ),
                    "parameters": {
                        "projects": {
                            "type": "array",
                            "required": True,
                        },
                        "requirements": {
                            "type": "object",
                            "required": False,
                        },
                    },
                },
                "deep_research": {
                    "description": (
                        "Run multi-query research."
                    ),
                    "parameters": {
                        "queries": {
                            "type": "array",
                            "required": True,
                        },
                        "requirements": {
                            "type": "object",
                            "required": False,
                        },
                        "time_budget_minutes": {
                            "type": "number",
                            "required": False,
                        },
                        "max_per_query": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
            },
        }
