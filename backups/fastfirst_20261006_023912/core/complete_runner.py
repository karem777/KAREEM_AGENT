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
from core.url_compat import origin, same_site
from tools.complete_registry import CompleteRegistry


class CompleteRunner:
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

    @staticmethod
    def _ok(result):
        return isinstance(result, dict) and result.get("success") is not False and not result.get("approval_required")

    def _recover_browser_navigation_drift(self, browser, target_url: str, error_text: str):
        """Recover only from a proven same-site navigation mismatch."""
        if not browser or not target_url:
            return None
        if "browser target drift detected" not in error_text.lower():
            return None
        try:
            obs = browser.inspect()
        except Exception:
            return None
        actual_url = None
        if isinstance(obs, dict):
            nested = obs.get("result") if isinstance(obs.get("result"), dict) else {}
            actual_url = nested.get("actual_url") or nested.get("url") or obs.get("actual_url") or obs.get("url")
            if not actual_url:
                text = str(nested.get("text") or obs.get("text") or "")
                for marker in ("https://", "http://"):
                    if marker in text:
                        actual_url = text[text.find(marker):].split()[0].rstrip(".,)")
                        break
        if not actual_url or not same_site(target_url, actual_url):
            return None
        try:
            page_id = obs.get("page_id") if isinstance(obs, dict) else None
            if page_id is None and isinstance(obs, dict):
                nested = obs.get("result") if isinstance(obs.get("result"), dict) else {}
                page_id = nested.get("page_id")
            if page_id is not None and hasattr(browser, "_bound_page_id"):
                browser._bound_page_id = page_id
            if hasattr(browser, "_expected_origin"):
                browser._expected_origin = origin(actual_url)
            if hasattr(browser, "_pending_target_url"):
                browser._pending_target_url = actual_url
        except Exception:
            pass
        return {
            "success": True,
            "url": actual_url,
            "target_url": target_url,
            "recovered": True,
            "recovery": "Accepted same-site URL normalization/redirect and rebound browser to the live destination.",
            "observation": obs,
        }

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
            return method(**arguments)
        except TypeError as exc:
            return {"success": False, "error": f"Bad arguments for {tool_name}.{action}: {exc}"}
        except Exception as exc:
            if tool_name == "browser" and action == "open_url":
                recovered = self._recover_browser_navigation_drift(tool, str(arguments.get("url", "")), str(exc))
                if recovered:
                    return recovered
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def _auto_perceive(self, tool: str, action: str, result: dict[str, Any]):
        if tool != "browser" or action == "inspect" or not self._ok(result):
            return result
        browser = self.registry.get("browser")
        if not browser:
            return result
        inspect = getattr(browser, "inspect", None)
        if not callable(inspect):
            return result
        try:
            perception = inspect()
            self.world.observe(perception)
            result = {"action_result": result, "auto_perception": perception, "success": True}
        except Exception:
            # The action itself may still be successful; perception is best effort.
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
        text = contract.get("goal", "").lower()
        last = history[-1] if history else {}
        result = last.get("result") or {}
        if contract.get("domain") == "research":
            if last.get("tool") == "research" and last.get("action") in {"deep_research", "rank_projects"} and self._ok(result):
                return True, "Research tool produced ranked evidence."
        if any(k in text for k in ["افتح أول نتيجة", "open first result", "first result"]):
            if self.world.state.page_type not in {"search_results", "search_home", "agent_control_ui"} and self.world.state.url:
                if last.get("tool") == "browser" and last.get("action") in {"click", "open_url", "navigate"} and self._ok(result):
                    return True, "Navigation evidence shows the requested result was opened."
        if any(k in text for k in ["احفظ", "save", "اكتب في ملف", "write to file"]):
            if last.get("tool") in {"filesystem", "windows"} and last.get("action") in {"write_file", "write_text_file"} and self._ok(result):
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

    def run(self, user_message: str):
        task_id = str(int(time.time() * 1000))
        contract = self.goal_compiler.compile(user_message)
        experiences = self.experience.search(user_message, limit=5)
        history: list[dict[str, Any]] = []
        recovery = {}

        # Initial observation if browser backend can inspect the current page.
        browser = self.registry.get("browser")
        if browser and callable(getattr(browser, "inspect", None)):
            try:
                obs = browser.inspect()
                self.world.observe(obs)
                history.append({"kind": "observe", "tool": "browser", "action": "inspect", "result": obs})
            except Exception as exc:
                history.append({"kind": "observe", "tool": "browser", "action": "inspect", "result": {"success": False, "error": str(exc)}})

        for step in range(1, self.max_steps + 1):
            tools = self.registry.describe()
            plan = self.planner.plan(contract, self.world.state.compact(), history, tools, recovery, experiences)
            ptype = plan.get("type") if isinstance(plan, dict) else None

            print("\n" + "=" * 78)
            print(f"KAREEM_AGENT COMPLETE | STEP {step}/{self.max_steps}")
            print("GOAL:", json.dumps(contract, ensure_ascii=False))
            print("WORLD:", json.dumps(self.world.state.compact(), ensure_ascii=False))
            print("PLAN:", json.dumps(plan, ensure_ascii=False, indent=2))

            if ptype == "ask_user":
                return {"success": False, "needs_user": True, "question": plan.get("question", "Need clarification."), "task_id": task_id}
            if ptype == "finish":
                ok, reason, missing = self._verifier(contract, self.world, history)
                if ok:
                    self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "success", "steps": step, "lesson": reason})
                    return {"success": True, "answer": plan.get("answer", "Task completed."), "evidence": plan.get("evidence", []), "steps": step, "task_id": task_id}
                recovery = {"type": "premature_finish", "reason": reason, "missing": missing}
                continue

            if ptype != "tool_call":
                recovery = {"type": "invalid_plan", "plan": plan}
                continue

            tool = str(plan.get("tool", "")).strip()
            action = str(plan.get("action", "")).strip()
            args = plan.get("arguments") if isinstance(plan.get("arguments"), dict) else {}
            guard = self.guard.check(self.world.state.fingerprint, tool, action, args)
            if guard["blocked"]:
                recovery = {"type": "loop_detected", "guard": guard, "message": "Choose a materially different action or refresh the world."}
                # A hard stop prevents wasting all 80 cycles on one mistake.
                if guard["count"] >= 4:
                    self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "stuck", "steps": step, "lesson": "Repeated same action on same world state."})
                    return {"success": False, "error": "Agent detected a loop and stopped instead of repeating it indefinitely.", "task_id": task_id, "steps": step}
                continue

            result = self._execute(tool, action, args)
            result = self._auto_perceive(tool, action, result)
            self._world_from_result(tool, action, result)
            record = {"step": step, "tool": tool, "action": action, "arguments": args, "result": result, "expected": plan.get("expected"), "reason": plan.get("reason")}
            history.append(record)
            print("OBSERVE:", json.dumps(result, ensure_ascii=False, indent=2))

            if result.get("approval_required"):
                self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "approval_required", "steps": step, "lesson": result.get("reason", "")})
                return {"success": False, "needs_approval": True, "question": result.get("reason", "Approval required."), "task_id": task_id, "steps": step}

            if self._ok(result):
                done, reason, missing = self._verifier(contract, self.world, history)
                if done:
                    self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "success", "steps": step, "lesson": reason, "evidence": history[-3:]})
                    return {"success": True, "answer": "تم تنفيذ الطلب بنجاح.", "reason": reason, "steps": step, "task_id": task_id}
                recovery = {"type": "continue", "missing": missing}
            else:
                recovery = {"type": "tool_error", "error": result.get("error", "unknown"), "last_action": {"tool": tool, "action": action}, "message": "Analyze the exact error and choose a different recovery path."}

        self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "step_limit", "steps": self.max_steps, "lesson": "Goal was not verified within the step budget."})
        return {"success": False, "error": f"Task stopped after {self.max_steps} cognitive cycles without verified completion.", "task_id": task_id}
