import json
import os
import time
from pathlib import Path
from typing import Any

from brain.complete_brain import CompleteBrain
from brain.complete_planner import CompletePlanner
from core.conversation_store import ConversationStore
from core.experience import ExperienceStore
from core.loop_guard import LoopGuard
from core.tool_router import ToolRouter
from core.world_model import WorldModel
from tools.complete_registry import CompleteRegistry


class CompleteRunner:
    """
    Supervisor + agent worker runtime.

    The model owns behavior. The runtime owns execution, observation,
    safety, bounded recovery, evidence, and durable conversation memory.
    """

    def __init__(self, workspace, max_steps=80):
        self.workspace = Path(workspace).resolve()
        self.max_steps = int(os.getenv("KAREEM_MAX_STEPS", str(max_steps)))
        self.brain = CompleteBrain()
        self.planner = CompletePlanner(self.brain)
        self.registry = CompleteRegistry(self.workspace)
        self.world = WorldModel()
        self.guard = LoopGuard()
        self.tool_router = ToolRouter()
        self.experience = ExperienceStore(self.workspace / "agent_memory")
        self.conversation = ConversationStore(self.workspace / "agent_memory")
        self.execution_mode = os.getenv("KAREEM_EXECUTION_MODE", "visible").strip().lower()
        self.max_recovery_attempts = int(os.getenv("KAREEM_MAX_RECOVERY", "3"))
        self._run_started_at = None

    def _step_budget(self, user_message: str) -> int:
        """Choose a practical per-task ceiling instead of spending 80 cycles by default."""
        hard_max = max(1, int(os.getenv("KAREEM_MAX_STEPS", str(self.max_steps))))
        text = str(user_message).lower()
        simple = len(text.split()) <= 12
        browser = any(k in text for k in ("http", "www.", "افتح", "موقع", "رابط", "browser", "google", "search"))
        complex_task = any(k in text for k in ("ثم", "بعد ذلك", "وبعدين", "multiple", "research", "ابحث", "حل", "ثبت", "install", "configure", "برمج"))
        if simple and not browser and not complex_task:
            target = 8
        elif browser and complex_task:
            target = 32
        elif browser:
            target = 20
        elif complex_task:
            target = 32
        else:
            target = 16
        return max(4, min(hard_max, target))

    @staticmethod
    def _classify_failure(result):
        raw = result.get("error", "") if isinstance(result, dict) else str(result)
        text = str(raw).lower()
        if any(k in text for k in ("argument", "required", "unexpected keyword", "typeerror")):
            return "bad_arguments", "Correct the arguments or inspect the tool contract before retrying."
        if any(k in text for k in ("not found", "no such", "does not exist", "unknown tool", "action not found")):
            return "missing_target", "Refresh discovery/inspection and choose a real target or action."
        if any(k in text for k in ("permission", "access denied", "forbidden", "unauthorized")):
            return "permission", "Do not repeat the blocked action; use an allowed alternative or ask only if approval is genuinely required."
        if any(k in text for k in ("timeout", "timed out", "time-out")):
            return "timeout", "Retry only after changing scope or strategy; avoid blind repetition."
        if any(k in text for k in ("connection", "network", "dns", "unreachable")):
            return "network", "Refresh the connection/state and try a different route if available."
        return "unknown", "Inspect the latest state and choose a materially different recovery action."

    @staticmethod
    def _ok(result):
        return (
            isinstance(result, dict)
            and result.get("success") is not False
            and not result.get("approval_required")
        )

    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
        tool = self.registry.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available": list(self.registry.tools),
            }

        method = getattr(tool, action, None)
        if not callable(method):
            try:
                actions = list(tool.describe().get("actions", {}).keys())
            except Exception:
                actions = []
            return {
                "success": False,
                "error": f"Action not found: {tool_name}.{action}",
                "available_actions": actions,
            }

        try:
            args = dict(arguments)
            if tool_name == "computer":
                # The universal WindowsOperator stores execution mode on the
                # operator itself; its individual actions do not accept mode.
                try:
                    tool.mode = self.execution_mode
                except Exception:
                    pass
            return method(**args)
        except TypeError as exc:
            return {
                "success": False,
                "error": f"Bad arguments for {tool_name}.{action}: {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _inspect_after(self, tool: str, action: str, result: dict[str, Any]):
        if tool != "browser" or action == "inspect" or not self._ok(result):
            return result

        browser = self.registry.get("browser")
        inspect = getattr(browser, "inspect", None) if browser else None
        if not callable(inspect):
            self.world.observe(result)
            return result

        if action not in {"click", "fill", "press_key", "navigate", "open_url", "type_text"}:
            self.world.observe(result)
            return result

        try:
            perception = inspect()
            self.world.observe(perception)
            return {
                "action_result": result,
                "auto_perception": perception,
                "success": True,
            }
        except Exception:
            self.world.observe(result)
            return result

    def _world_from_result(self, tool, action, result):
        """Promote successful observations into durable world state."""
        if not self._ok(result):
            return
        if tool == "browser":
            self.world.observe(result)
            return
        if tool == "computer":
            target = result.get("target") if isinstance(result, dict) else None
            if isinstance(target, dict):
                self.world.state.title = target.get("title") or self.world.state.title
                self.world.state.page_id = target.get("hwnd") or target.get("target_id") or self.world.state.page_id
                self.world.state.facts["active_app"] = target.get("process_name") or target.get("title") or ""
                self.world.state.facts["computer_target"] = target
            self.world.state.facts["last_computer_action"] = action
            self.world.state.fingerprint = self._state_fingerprint()
            return
        if tool == "web":
            self.world.state.facts["last_web_action"] = action
            if isinstance(result, dict):
                if result.get("query"):
                    self.world.state.facts["last_search_query"] = result.get("query")
                if isinstance(result.get("results"), list):
                    self.world.state.facts["search_results"] = result.get("results", [])[:12]
                if result.get("url"):
                    self.world.state.url = result.get("url")
                    self.world.state.origin = self.world._origin(result.get("url"))
                    from urllib.parse import urlparse
                    self.world.state.domain = urlparse(result.get("url")).netloc.lower()
                if result.get("text"):
                    self.world.state.text = str(result.get("text"))[:12000]
                    self.world.state.facts["page_text_available"] = True
                if result.get("title"):
                    self.world.state.title = str(result.get("title"))[:240]
            self.world.state.fingerprint = self._state_fingerprint()
            return
        if tool == "filesystem":
            self.world.state.facts["last_filesystem_action"] = action
            self.world.state.facts["last_filesystem_result"] = result
            self.world.state.fingerprint = self._state_fingerprint()
            return
        if tool == "windows":
            if action == "get_system_info":
                self.world.state.facts["windows_system"] = result
            elif action in {"network", "storage", "processes", "services", "ports", "events", "installed_apps"}:
                self.world.state.facts[f"windows_{action}"] = result
            self.world.state.fingerprint = self._state_fingerprint()

    def _state_fingerprint(self):
        import hashlib
        payload = {
            "url": self.world.state.url,
            "title": self.world.state.title,
            "page_type": self.world.state.page_type,
            "facts": self.world.state.facts,
        }
        return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _same_action(item, tool, action, args):
        return isinstance(item, dict) and item.get("tool") == tool and item.get("action") == action and item.get("arguments") == args and CompleteRunner._ok(item.get("result"))

    def _progress(self, history):
        successful = [h for h in history if self._ok(h.get("result"))]
        last = successful[-1] if successful else None
        return {
            "completed_actions": [{"tool": h.get("tool"), "action": h.get("action")} for h in successful[-8:]],
            "last_success": last,
            "search_completed": any(h.get("tool") == "web" and h.get("action") == "search" for h in successful),
            "web_evidence_available": any(h.get("tool") == "web" and h.get("action") == "open_url" for h in successful),
            "file_written": any(h.get("tool") == "filesystem" and h.get("action") == "write_file" for h in successful),
        }

    def _normalize_file_action(self, user_message, tool, action, args):
        if tool != "filesystem" or action != "write_file":
            return args
        low = str(user_message).lower()
        if not any(x in low for x in ("desktop", "ديسك توب", "سطح المكتب")):
            return args
        out = dict(args)
        raw = str(out.get("path") or "").strip()
        name = Path(raw).name or "output.txt"
        normalized = raw.lower().replace("/", "\\")
        if not normalized.startswith(("desktop\\", "سطح المكتب\\")):
            out["path"] = f"Desktop/{name}"
        return out

    def _duplicate_recovery_action(self, history):
        successful = [h for h in history if self._ok(h.get("result"))]
        if not successful:
            return None
        last = successful[-1]
        tool, action, result = last.get("tool"), last.get("action"), last.get("result")
        if tool == "web" and action == "search" and isinstance(result, dict):
            results = result.get("results") or []
            if results and results[0].get("url"):
                return {"tool": "web", "action": "open_url", "arguments": {"url": results[0]["url"]}}
        if tool == "filesystem" and action == "write_file" and isinstance(result, str):
            marker = "File written: "
            if marker in result:
                return {"tool": "filesystem", "action": "read_file", "arguments": {"path": result.split(marker, 1)[1].strip()}}
        if tool == "computer" and action == "open_app":
            return {"tool": "computer", "action": "inspect", "arguments": {}}
        return None

    def _verifier(self, contract, world, history):
        prompt = f"""
You are KAREEM_AGENT's independent completion verifier.

Return JSON only:
{{"complete":true|false,"reason":"...","missing":["..."]}}

The model that acted is not allowed to decide completion by intention.
Judge only observable evidence.

GOAL:
{json.dumps(contract, ensure_ascii=False)}

WORLD:
{json.dumps(world.state.compact(), ensure_ascii=False)}

RECENT ACTIONS:
{json.dumps(history[-8:], ensure_ascii=False)}
""".strip()

        value = self.brain.json(
            prompt,
            fallback={
                "complete": False,
                "reason": "Verifier unavailable.",
                "missing": ["independent completion evidence"],
            },
        )
        if not isinstance(value, dict):
            return False, "Verifier returned an invalid result.", ["verification"]
        return (
            bool(value.get("complete")),
            str(value.get("reason") or ""),
            value.get("missing") if isinstance(value.get("missing"), list) else [],
        )

    def _finish(self, task_id, user_message, step, answer, history, reason=""):
        elapsed = round(time.time() - self._run_started_at, 3) if self._run_started_at else None
        evidence = history[-4:]

        self.experience.append({
            "task_id": task_id,
            "goal": user_message,
            "outcome": "success",
            "steps": step,
            "elapsed_seconds": elapsed,
            "lesson": reason or "Task completed with independently verified evidence.",
            "evidence": evidence,
        })
        self.conversation.append(
            "assistant",
            answer,
            {"task_id": task_id, "outcome": "success", "steps": step},
        )
        return {
            "success": True,
            "mode": "task",
            "answer": answer,
            "reason": reason,
            "steps": step,
            "elapsed_seconds": elapsed,
            "task_id": task_id,
            "evidence": evidence,
        }

    def _record_failure(self, task_id, user_message, step, lesson):
        self.experience.append({
            "task_id": task_id,
            "goal": user_message,
            "outcome": "failure",
            "steps": step,
            "lesson": lesson,
        })

    def run(self, user_message: str, execution_mode: str | None = None):
        task_id = str(int(time.time() * 1000))
        self._run_started_at = time.time()
        print("KAREEM_AGENT TASK START", flush=True)

        if execution_mode:
            mode = str(execution_mode).strip().lower()
            self.execution_mode = "background" if mode == "background" else "visible"

        self.conversation.append("user", user_message)
        conversation = self.conversation.recent(limit=12)

        contract = {"goal": user_message}
        experiences = self.experience.search(user_message, limit=4)
        step_budget = self._step_budget(user_message)
        history: list[dict[str, Any]] = []
        recovery: dict[str, Any] = {}
        invalid_streak = 0
        recovery_streak = 0

        self.world = WorldModel()
        self.guard = LoopGuard()

        for step in range(1, step_budget + 1):
            available = self.registry.describe()
            allowed_tools = self.tool_router.select(user_message, available)
            tools = self.registry.describe_for_planner(allowed_tools)

            started = time.time()
            plan = self.planner.plan(
                contract,
                self.world.state.compact(),
                history[-8:],
                tools,
                recovery,
                experiences,
                conversation,
                self._progress(history),
            )
            print(
                f"KAREEM_AGENT PLANNER: {time.time() - started:.2f}s",
                flush=True,
            )

            ptype = plan.get("type") if isinstance(plan, dict) else None

            print()
            print("=" * 78)
            print(f"KAREEM_AGENT | STEP {step}/{step_budget}")
            print("GOAL:", json.dumps(contract, ensure_ascii=False))
            print("WORLD:", json.dumps(self.world.state.compact(), ensure_ascii=False))
            print("PLAN:", json.dumps(plan, ensure_ascii=False, indent=2))

            # Action requests must never be downgraded to chat.
            # The runtime is the final guardrail: if the user explicitly
            # requested an operation, force the planner back into ACT mode.
            action_request = any(
                token in str(user_message).lower()
                for token in (
                    "افتح", "ابحث", "ادخل", "اضغط", "اكتب", "شغل",
                    "نزّل", "حمل", "ثبت", "احذف", "اعمل", "روح",
                    "open", "search", "click", "type", "launch", "install",
                    "download", "delete", "go to", "navigate",
                )
            )

            # Supervisor/Talker mode.
            if ptype == "chat" and action_request:
                invalid_streak += 1
                recovery = {
                    "type": "planner_downgraded_action_to_chat",
                    "planner_response": plan.get("content", ""),
                    "instruction": (
                        "This is an executable user request. Do NOT chat or "
                        "claim inability. Choose exactly one real tool_call "
                        "from LIVE TOOLS to make progress."
                    ),
                    "required_mode": "ACT",
                }
                print(
                    "KAREEM_AGENT: rejected chat response for actionable request",
                    flush=True,
                )
                if invalid_streak >= self.max_recovery_attempts:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        "Planner repeatedly downgraded an actionable request to chat.",
                    )
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Planner refused to execute an actionable request.",
                        "task_id": task_id,
                        "steps": step,
                    }
                continue

            if ptype == "chat":
                answer = str(plan.get("content") or "").strip()
                if not answer:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        "Planner returned an empty conversational response.",
                    )
                    return {
                        "success": False,
                        "mode": "chat",
                        "error": "Planner returned an empty response.",
                        "task_id": task_id,
                    }

                self.conversation.append(
                    "assistant",
                    answer,
                    {"task_id": task_id, "outcome": "chat"},
                )
                return {
                    "success": True,
                    "mode": "chat",
                    "answer": answer,
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
                        plan.get("answer", "تم تنفيذ المهمة والتحقق منها."),
                        history,
                        reason,
                    )

                recovery = {
                    "type": "premature_finish",
                    "reason": reason,
                    "missing": missing,
                    "instruction": "Continue working; completion is not proven.",
                }
                recovery_streak += 1
                if recovery_streak >= self.max_recovery_attempts:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        "Repeated premature completion without evidence.",
                    )
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Agent could not produce completion evidence.",
                        "missing": missing,
                        "task_id": task_id,
                        "steps": step,
                    }
                continue

            if ptype != "tool_call":
                invalid_streak += 1
                recovery = {
                    "type": "invalid_plan",
                    "plan": plan,
                    "instruction": "Produce either a real tool_call, a verified finish, or a natural chat response.",
                }
                if invalid_streak >= self.max_recovery_attempts:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        f"Planner remained invalid after {invalid_streak} bounded recovery attempts.",
                    )
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Planner failed to produce a valid decision; stopped safely instead of looping.",
                        "task_id": task_id,
                        "steps": step,
                    }
                continue

            invalid_streak = 0
            tool = str(plan.get("tool") or "").strip()
            action = str(plan.get("action") or "").strip()
            args = plan.get("arguments") if isinstance(plan.get("arguments"), dict) else {}
            args = self._normalize_file_action(user_message, tool, action, args)

            if not tool or not action:
                recovery = {
                    "type": "invalid_tool_call",
                    "instruction": "Select an actual tool and action from LIVE TOOLS.",
                }
                invalid_streak += 1
                if invalid_streak >= self.max_recovery_attempts:
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Planner repeatedly produced an incomplete tool call.",
                        "task_id": task_id,
                    }
                continue

            if history and self._same_action(history[-1], tool, action, args):
                next_action = self._duplicate_recovery_action(history)
                recovery = {
                    "type": "successful_action_repeated",
                    "instruction": "The previous identical action already succeeded. Advance to a new action; do not repeat it.",
                    "suggested_next_action": next_action,
                }
                if next_action:
                    tool, action, args = next_action["tool"], next_action["action"], next_action["arguments"]
                else:
                    continue

            if tool == "filesystem" and action == "write_file":
                research_task = any(k in str(user_message).lower() for k in ("ابحث", "معلومات", "research", "search", "مصدر", "source"))
                if research_task and not self._progress(history)["web_evidence_available"]:
                    recovery = {
                        "type": "insufficient_research_evidence",
                        "instruction": "Do not write research yet. Open/read a real source from the successful web search first.",
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
                    "instruction": "Do not repeat the same action on the same state. Refresh or change strategy.",
                }
                if guard["count"] >= 4:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        "Loop guard stopped repeated actions on unchanged state.",
                    )
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Execution stopped because the agent entered a repeated-action loop.",
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
                "reason": plan.get("reason"),
            })

            print(
                "OBSERVE:",
                json.dumps(result, ensure_ascii=False, indent=2, default=str),
            )

            if isinstance(result, dict) and result.get("approval_required"):
                self.conversation.append(
                    "assistant",
                    str(result.get("reason") or "Approval is required to continue."),
                    {"task_id": task_id, "needs_approval": True},
                )
                return {
                    "success": False,
                    "mode": "task",
                    "needs_approval": True,
                    "question": result.get("reason", "Approval required."),
                    "task_id": task_id,
                    "steps": step,
                }

            if self._ok(result):
                recovery = {
                    "type": "continue",
                    "instruction": "Use the new observation and TASK PROGRESS. Never repeat a successful identical action; advance toward the remaining goal.",
                    "progress": self._progress(history),
                }
                recovery_streak = 0
            else:
                recovery = {
                    "type": "tool_error",
                    "error": result.get("error", "unknown") if isinstance(result, dict) else repr(result),
                    "last_action": {"tool": tool, "action": action},
                    "category": self._classify_failure(result)[0],
                    "instruction": self._classify_failure(result)[1],
                }
                recovery_streak += 1
                if recovery_streak >= self.max_recovery_attempts:
                    self._record_failure(
                        task_id,
                        user_message,
                        step,
                        f"Tool recovery budget exhausted after: {recovery.get('error')}",
                    )
                    return {
                        "success": False,
                        "mode": "task",
                        "error": "Agent stopped after bounded recovery attempts.",
                        "task_id": task_id,
                        "steps": step,
                    }

        self._record_failure(
            task_id,
            user_message,
            step_budget,
            f"Goal was not verified within the adaptive step budget of {step_budget}.",
        )
        return {
            "success": False,
            "mode": "task",
            "error": f"Task stopped after {step_budget} adaptive agent steps.",
            "task_id": task_id,
        }
