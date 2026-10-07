import json
import os
import time
from pathlib import Path
from typing import Any

from brain.complete_brain import CompleteBrain
from brain.complete_planner import CompletePlanner
from core.experience import ExperienceStore
from core.fast_router import FastRouter
from core.goal_contract import GoalContract
from core.loop_guard import LoopGuard
from core.local_windows_fast import try_run_local_windows_fast
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
        self.fast_router = FastRouter()
        self.experience = ExperienceStore(self.workspace / "agent_memory")
        self.fast_mode = os.getenv("KAREEM_FAST_MODE", "1") == "1"
        self.verify_every_action = os.getenv("KAREEM_VERIFY_EVERY_ACTION", "0") == "1"
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

    def _deterministic_completion(self, contract: dict[str, Any], history: list[dict[str, Any]]) -> tuple[bool, str]:
        text = str(contract.get("goal", "")).lower()
        last = history[-1] if history else {}
        result = last.get("result") or {}
        if contract.get("domain") == "research":
            if last.get("tool") == "research" and last.get("action") in {"deep_research", "rank_projects"} and self._ok(result):
                return True, "Research tool produced ranked evidence."
        if any(k in text for k in ["Ø§ÙØªØ­ Ø£ÙˆÙ„ Ù†ØªÙŠØ¬Ø©", "Ø§ÙØªØ­ Ø§Ù„Ù†ØªÙŠØ¬Ø© Ø§Ù„Ø£ÙˆÙ„Ù‰", "open first result", "first result"]):
            if last.get("tool") == "browser" and last.get("action") in {"click", "open_url", "navigate"} and self._ok(result):
                domain = (self.world.state.domain or "").lower()
                if domain and not any(x in domain for x in ["google.", "bing.", "duckduckgo.", "brave"]):
                    return True, "Navigation evidence shows the requested first result was opened."
        if any(k in text for k in ["Ø§Ø­ÙØ¸", "save", "Ø§ÙƒØªØ¨ ÙÙŠ Ù…Ù„Ù", "write to file"]):
            if last.get("tool") in {"filesystem", "windows", "developer"} and last.get("action") in {"write_file", "write_text_file", "write_code"} and self._ok(result):
                return True, "File-write evidence present."
        return False, ""

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

    def _run_fast(self, task_id: str, user_message: str, fast_task) -> dict[str, Any] | None:
        history: list[dict[str, Any]] = []
        print(f"\nFAST PATH: {fast_task.kind} | {fast_task.reason}")
        for step, plan in enumerate(fast_task.actions, 1):
            tool = plan["tool"]
            action = plan["action"]
            args = plan.get("arguments", {})
            guard = self.guard.check(self.world.state.fingerprint or "empty", tool, action, args)
            if guard["blocked"]:
                return None
            print(f"\nFAST STEP {step}/{len(fast_task.actions)}: {tool}.{action} {args}")
            result = self._execute(tool, action, args)
            result = self._inspect_after(tool, action, result, force=(action == "inspect"))
            self._world_from_result(tool, action, result)
            history.append({"step": step, "tool": tool, "action": action, "arguments": args, "result": result})
            print("OBSERVE:", json.dumps(result, ensure_ascii=False, indent=2))
            if result.get("approval_required"):
                return {"success": False, "needs_approval": True, "question": result.get("reason", "Approval required."), "task_id": task_id, "steps": step}
            if not self._ok(result):
                return None

        deterministic = True
        if fast_task.kind == "open_url":
            reason = "Explicit URL open completed."
        elif fast_task.kind == "search":
            reason = "Search page opened and observed."
        elif fast_task.kind == "search_first_result":
            deterministic = self.world.state.url is not None and self.world.state.page_type not in {"search_results", "search_home", "agent_control_ui"}
            reason = "First-result navigation completed with a non-search destination."
        else:
            deterministic, reason = self._deterministic_completion({"goal": user_message, "domain": "web"}, history)
        if deterministic:
            return self._finish(task_id, user_message, len(history), "ØªÙ… ØªÙ†ÙÙŠØ° Ø§Ù„Ø·Ù„Ø¨ Ø¨Ù†Ø¬Ø§Ø­.", history, reason)
        return None

    def run(self, user_message: str, execution_mode: str | None = None):
        task_id = str(int(time.time() * 1000))
        print("KAREEM_AGENT TASK START", flush=True)

        # Very simple local Windows tasks can be executed deterministically
        # without waiting for the LLM planning stack.
        local_fast = try_run_local_windows_fast(
            user_message,
            getattr(self, "execution_mode", "visible"),
        )

        if local_fast is not None:
            print("LOCAL FAST PATH RESULT:", json.dumps(local_fast, ensure_ascii=False, indent=2))
            local_fast["task_id"] = task_id
            return local_fast


        # Store execution mode for local computer actions.
        if execution_mode:
            mode = str(execution_mode).strip().lower()
            self.execution_mode = "background" if mode == "background" else "visible"

        if self.fast_mode:
            fast_task = self.fast_router.route(user_message)
            if fast_task:
                fast_result = self._run_fast(task_id, user_message, fast_task)
                if fast_result is not None:
                    return fast_result

        contract = self.goal_compiler.compile(user_message)
        experiences = self.experience.search(user_message, limit=5)
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

            # Hard safety/routing guard:
            # Local Windows goals must use the computer tool, not browser.
            if str(contract.get("domain", "")).lower() in {
                "windows",
                "desktop",
                "local",
                "system",
            }:
                if tool == "browser":
                    recovery = {
                        "type": "wrong_tool",
                        "message": "This is a local Windows task. Use the computer tool.",
                        "last_plan": plan,
                    }
                    continue

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
                deterministic, reason = self._deterministic_completion(
                    contract,
                    history,
                )

                if deterministic:
                    return self._finish(
                        task_id,
                        user_message,
                        step,
                        "تم تنفيذ الطلب بنجاح.",
                        history,
                        reason,
                    )

                if self.verify_every_action:
                    done, reason, missing = self._verifier(
                        contract,
                        self.world,
                        history,
                    )

                    if done:
                        return self._finish(
                            task_id,
                            user_message,
                            step,
                            "تم تنفيذ الطلب بنجاح.",
                            history,
                            reason,
                        )

                    recovery = {
                        "type": "continue",
                        "missing": missing,
                    }
                else:
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










