import json
from copy import deepcopy


class GoalState:
    def __init__(self, analysis):
        self.analysis = deepcopy(
            analysis or {}
        )

        self.steps = {
            step["id"]: {
                **deepcopy(step),
                "status": "pending",
                "result": None,
                "attempts": 0,
                "last_error": None,
            }
            for step in self.analysis.get(
                "steps",
                [],
            )
            if step.get("id")
        }

        self.history = []
        self.failure_count = 0

    def _dependency_satisfied(self, step):
        for dependency in step.get(
            "depends_on",
            [],
        ):
            dependency_step = self.steps.get(
                dependency
            )

            if not dependency_step:
                return False

            if dependency_step.get(
                "status"
            ) != "completed":
                return False

        return True

    def ready_steps(self):
        return [
            step
            for step in self.steps.values()
            if (
                step.get("status") == "pending"
                and self._dependency_satisfied(step)
            )
        ]

    def remaining(self):
        return [
            deepcopy(step)
            for step in self.steps.values()
            if step.get("status") != "completed"
        ]

    def is_complete(self):
        required = [
            step
            for step in self.steps.values()
            if step.get("required", True)
        ]

        return bool(required) and all(
            step.get("status") == "completed"
            for step in required
        )

    @staticmethod
    def _normalize_tool_action(tool, action):
        tool = str(tool or "").strip()
        action = str(action or "").strip()

        if not tool and "." in action:
            left, right = action.split(".", 1)
            if left:
                tool = left
                action = right

        if "." in action:
            left, right = action.split(".", 1)
            if left == tool and right:
                action = right

        return tool, action

    def _match_call(self, call):
        tool, action = self._normalize_tool_action(
            call.get("tool", ""),
            call.get("action", ""),
        )

        ready = self.ready_steps()

        exact = []
        for step in ready:
            step_tool, step_action = self._normalize_tool_action(
                step.get("tool", ""),
                step.get("action", ""),
            )

            if (
                step_tool == tool
                and step_action == action
            ):
                exact.append(step)

        if not exact:
            return None

        actual_args = call.get(
            "arguments",
            {},
        )

        if not isinstance(
            actual_args,
            dict,
        ):
            actual_args = {}

        best = exact[0]
        best_score = -1

        for step in exact:
            expected_args = step.get(
                "arguments",
                {},
            )

            score = len(
                set(expected_args)
                & set(actual_args)
            )

            if score > best_score:
                best_score = score
                best = step

        return best

    def observe_success(
        self,
        call,
        result,
    ):
        step = self._match_call(
            call
        )

        event = {
            "tool": call.get("tool"),
            "action": call.get("action"),
            "arguments": call.get("arguments", {}),
            "success": True,
            "result": result,
        }

        self.history.append(event)

        if step is not None:
            step["status"] = "completed"
            step["result"] = result
            step["attempts"] = (
                step.get(
                    "attempts",
                    0,
                )
                + 1
            )
            step["last_error"] = None

        return step

    def observe_failure(
        self,
        call,
        result,
    ):
        self.failure_count += 1

        step = self._match_call(
            call
        )

        event = {
            "tool": call.get("tool"),
            "action": call.get("action"),
            "arguments": call.get("arguments", {}),
            "success": False,
            "result": result,
        }

        self.history.append(event)

        if step is not None:
            step["attempts"] = (
                step.get(
                    "attempts",
                    0,
                )
                + 1
            )
            step["last_error"] = result

        return step

    def summary(self):
        return {
            "goal": self.analysis.get(
                "goal",
                "",
            ),
            "mode": self.analysis.get(
                "mode",
                "",
            ),
            "complete": self.is_complete(),
            "steps": [
                {
                    "id": step["id"],
                    "description": step.get(
                        "description",
                        "",
                    ),
                    "status": step.get(
                        "status",
                        "pending",
                    ),
                    "attempts": step.get(
                        "attempts",
                        0,
                    ),
                    "depends_on": step.get(
                        "depends_on",
                        [],
                    ),
                    "tool": step.get(
                        "tool",
                        "",
                    ),
                    "action": step.get(
                        "action",
                        "",
                    ),
                    "last_error": step.get(
                        "last_error",
                    ),
                }
                for step in self.steps.values()
            ],
            "ready_steps": [
                {
                    "id": step["id"],
                    "description": step.get(
                        "description",
                        "",
                    ),
                    "tool": step.get(
                        "tool",
                        "",
                    ),
                    "action": step.get(
                        "action",
                        "",
                    ),
                    "arguments": step.get(
                        "arguments",
                        {},
                    ),
                }
                for step in self.ready_steps()
            ],
            "recent_observations": self.history[-8:],
            "failure_count": self.failure_count,
        }

    def to_json(self):
        return json.dumps(
            self.summary(),
            ensure_ascii=False,
            indent=2,
        )
