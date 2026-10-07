from pathlib import Path
import re

path = Path(r".\tools\complete_registry.py")
text = path.read_text(encoding="utf-8")

# inspect must exist because we synthesize schemas from Python signatures.
if "import inspect" not in text:
    text = text.replace(
        "import importlib\n",
        "import importlib\nimport inspect\n",
        1,
    )

start = text.find("    def describe(self):")
if start < 0:
    raise RuntimeError("CompleteRegistry.describe() not found")

# Find the next top-level method/class after describe().
tail = text[start:]
matches = list(
    re.finditer(
        r"\n    def |\nclass ",
        tail[1:],
    )
)

if matches:
    end = start + 1 + matches[0].start() + 1
else:
    end = len(text)

new_describe = r'''    @staticmethod
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
'''

text = text[:start] + new_describe + text[end:]

path.write_text(
    text,
    encoding="utf-8",
)

print(
    "CompleteRegistry schema synthesis installed."
)
