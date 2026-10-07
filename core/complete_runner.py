import json
import os
import time
from pathlib import Path
from typing import Any

from brain.complete_brain import CompleteBrain
from brain.complete_planner import CompletePlanner
from core.experience import ExperienceStore
from core.goal_contract import GoalContract
from core.loop_guard import LoopGuard
from core.world_model import WorldModel
from tools.complete_registry import CompleteRegistry


class CompleteRunner:
    """Fast-first autonomous runner.

    Deterministic low-risk tasks bypass the heavy LLM planning path. Complex
    tasks retain the full 80-cycle cognitive loop, with lazy perception and
    lazy middle-of-task verification.
    """

    def __init__(self, workspace, max_steps=80):
        self.workspace = Path(workspace).resolve()
        self.max_steps = int(os.getenv("KAREEM_MAX_STEPS", str(max_steps)))
        self.brain = CompleteBrain()
        self.planner = CompletePlanner(self.brain)
        self.goal_compiler = GoalContract(self.brain)
        self.registry = CompleteRegistry(self.workspace)
        self.world = WorldModel()
        self.guard = LoopGuard()
        self.experience = ExperienceStore(self.workspace / "agent_memory")
        self.execution_mode = os.getenv("KAREEM_EXECUTION_MODE", "visible").strip().lower()
        self.max_history_context = int(os.getenv("KAREEM_HISTORY_CONTEXT", "10"))
        self.max_recovery_attempts = int(os.getenv("KAREEM_MAX_RECOVERY", "3"))
        self._run_started_at = None

    @staticmethod
    def _ok(result):
        return isinstance(result, dict) and result.get("success") is not False and not result.get("approval_required")

    def _reset_session(self):
        """Reset per-task world/guard state so tasks cannot leak state."""
        self.world = WorldModel()
        self.guard = LoopGuard()
        self._run_started_at = time.time()

    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
        tool = self.registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {tool_name}", "available": list(self.registry.tools)}
        method = getattr(tool, action, None)
        if not callable(method):
            try:
                actions = list(tool.describe().get("actions", {}).keys())
            except Exception:
                actions = []
            return {"success": False, "error": f"Action not found: {tool_name}.{action}", "available_actions": actions}
        try:
            if tool_name == "computer":
                arguments = dict(arguments)
                arguments.setdefault("mode", self.execution_mode)
            return method(**arguments)
        except TypeError as exc:
            return {"success": False, "error": f"Bad arguments for {tool_name}.{action}: {exc}"}
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def _inspect_after(self, tool: str, action: str, result: dict[str, Any], force=False):
        if tool != "browser" or action == "inspect" or not self._ok(result):
            return result
        browser = self.registry.get("browser")
        inspect = getattr(browser, "inspect", None) if browser else None
        if not callable(inspect):
            return result
        needs = force or action in {"click", "fill", "press_key", "navigate"}
        if not needs:
            self.world.observe(result)
            return result
        try:
            perception = inspect()
            self.world.observe(perception)
            return {"action_result": result, "auto_perception": perception, "success": True}
        except Exception:
            self.world.observe(result)
            return result

    def _world_from_result(self, tool, action, result):
        if tool == "browser":
            self.world.observe(result)
        elif tool == "windows" and self._ok(result):
            if action == "get_system_info":
                self.world.state.facts["windows_system"] = result
            elif action in {"network", "storage", "processes", "services", "ports", "events", "installed_apps"}:
                self.world.state.facts[f"windows_{action}"] = result

    def _verifier(self, contract, world, history):
        deterministic, why = self._deterministic_completion(contract, history)
        if deterministic:
            return True, why, []
        prompt = f'''
You are the final evidence verifier for an autonomous agent.
Return JSON only: {{"complete": true|false, "reason": "...", "missing": ["..."]}}
Do not reward intentions. Only actual evidence counts.

GOAL:
{json.dumps(contract, ensure_ascii=False)}

WORLD:
{json.dumps(world.state.compact(), ensure_ascii=False)}

LAST 8 ACTIONS:
{json.dumps(history[-8:], ensure_ascii=False)}
'''
        value = self.brain.json(prompt, fallback={"complete": False, "reason": "Verifier unavailable", "missing": ["verified completion evidence"]})
        return bool(value.get("complete")), str(value.get("reason", "")), value.get("missing", [])

    def _finish(self, task_id, user_message, step, answer, history, reason=""):
        elapsed = round(time.time() - self._run_started_at, 3) if self._run_started_at else None
        evidence = history[-3:]
        self.experience.append({
            "task_id": task_id,
            "goal": user_message,
            "outcome": "success",
            "steps": step,
            "elapsed_seconds": elapsed,
            "lesson": reason or "Task completed with verified evidence.",
            "evidence": evidence,
        })
        return {
            "success": True,
            "answer": answer,
            "reason": reason,
            "steps": step,
            "elapsed_seconds": elapsed,
            "task_id": task_id,
            "evidence": evidence,
        }

    def run(self, user_message: str, execution_mode: str | None = None):
        task_id = str(int(time.time() * 1000))
        print("KAREEM_AGENT TASK START", flush=True)


        # Store execution mode for local computer actions.
        if execution_mode:
            mode = str(execution_mode).strip().lower()
            self.execution_mode = "background" if mode == "background" else "visible"
        stage_started = time.time()
        print("KAREEM_AGENT GOAL COMPILE START", flush=True)
        contract = self.goal_compiler.compile(user_message)
        print(f"KAREEM_AGENT GOAL COMPILE: {time.time() - stage_started:.2f}s", flush=True)

        stage_started = time.time()
        experiences = self.experience.search(user_message, limit=5)
        print(f"KAREEM_AGENT EXPERIENCE SEARCH: {time.time() - stage_started:.2f}s", flush=True)
        history: list[dict[str, Any]] = []
        recovery = {}

        # Reset per-task state.
        self.world = WorldModel()
        self.guard = LoopGuard()

        for step in range(1, self.max_steps + 1):
            tools = self.registry.describe()

            plan = self.planner.plan(
                contract,
                self.world.state.compact(),
                history[-8:],
                tools,
                recovery,
                experiences,
            )

            ptype = plan.get("type") if isinstance(plan, dict) else None

            print()
            print("=" * 78)
            print(f"KAREEM_AGENT COMPLETE | STEP {step}/{self.max_steps}")
            print("MODE:", self.execution_mode)
            print("GOAL:", json.dumps(contract, ensure_ascii=False))
            print("WORLD:", json.dumps(self.world.state.compact(), ensure_ascii=False))
            print("PLAN:", json.dumps(plan, ensure_ascii=False, indent=2))

            if ptype == "ask_user":
                return {
                    "success": False,
                    "needs_user": True,
                    "question": plan.get("question", "Need clarification."),
                    "task_id": task_id,
                }

            if ptype == "finish":
                ok, reason, missing = self._verifier(
                    contract,
                    self.world,
                    history,
                )
                if ok:
                    return self._finish(
                        task_id,
                        user_message,
                        step,
                        plan.get("answer", "Task completed."),
                        history,
                        reason,
                    )

                recovery = {
                    "type": "premature_finish",
                    "reason": reason,
                    "missing": missing,
                }
                continue

            if ptype != "tool_call":
                recovery = {
                    "type": "invalid_plan",
                    "plan": plan,
                }
                continue

            tool = str(plan.get("tool", "")).strip()
            action = str(plan.get("action", "")).strip()

            args = (
                plan.get("arguments")
                if isinstance(plan.get("arguments"), dict)
                else {}
            )

            guard = self.guard.check(
                self.world.state.fingerprint,
                tool,
                action,
                args,
            )

            if guard["blocked"]:
                recovery = {
                    "type": "loop_detected",
                    "guard": guard,
                    "message": "Choose a materially different action or refresh the world.",
                }

                if guard["count"] >= 4:
                    self.experience.append({
                        "task_id": task_id,
                        "goal": user_message,
                        "outcome": "stuck",
                        "steps": step,
                        "lesson": "Repeated same action on same world state.",
                    })

                    return {
                        "success": False,
                        "error": "Agent detected a loop and stopped instead of repeating it indefinitely.",
                        "task_id": task_id,
                        "steps": step,
                    }

                continue

            result = self._execute(tool, action, args)
            result = self._inspect_after(tool, action, result)
            self._world_from_result(tool, action, result)

            history.append({
                "step": step,
                "tool": tool,
                "action": action,
                "arguments": args,
                "result": result,
                "expected": plan.get("expected"),
                "reason": plan.get("reason"),
            })

            print(
                "OBSERVE:",
                json.dumps(result, ensure_ascii=False, indent=2),
            )

            if result.get("approval_required"):
                return {
                    "success": False,
                    "needs_approval": True,
                    "question": result.get(
                        "reason",
                        "Approval required.",
                    ),
                    "task_id": task_id,
                    "steps": step,
                }

            if self._ok(result):
                recovery = {
                    "type": "continue",
                    "missing": ["continue toward goal"],
                }

            else:
                recovery = {
                    "type": "tool_error",
                    "error": result.get("error", "unknown"),
                    "last_action": {
                        "tool": tool,
                        "action": action,
                    },
                    "message": "Analyze the exact error and choose a different recovery path.",
                }

        self.experience.append({
            "task_id": task_id,
            "goal": user_message,
            "outcome": "step_limit",
            "steps": self.max_steps,
            "lesson": "Goal was not verified within the step budget.",
        })

        return {
            "success": False,
            "error": f"Task stopped after {self.max_steps} cognitive cycles without verified completion.",
            "task_id": task_id,
        }













