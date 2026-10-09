from __future__ import annotations

import json
import re
import time
from typing import Any

from brain.planner import Planner
from tools.registry import ToolRegistry
from tools.executor_v4 import ToolExecutorV4
from memory.engine import LongTermMemory
from knowledge.store import KnowledgeStore
from core.cognition import CognitiveRuntime
from core.trace import TraceStore


class AgentRunner:
    """KAREEM_AGENT V5 perception/reasoning/action/verification runtime."""

    def __init__(self, workspace="workspace", max_steps=80):
        self.workspace = workspace
        self.max_steps = int(max_steps)
        self.planner = Planner()
        self.registry = ToolRegistry(workspace)
        self.executor = ToolExecutorV4(self.registry)
        self.memory = LongTermMemory()
        self.knowledge = KnowledgeStore()
        self.cognition = CognitiveRuntime(brain=self.planner.brain)
        self.trace = TraceStore()
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def _pre_route(user_message: str) -> dict[str, Any] | None:
        """Route only narrow, unambiguous local tasks without an LLM call."""
        text = str(user_message or "").strip()
        if not text:
            return None

        folder = re.fullmatch(
            r"""\s*(?:أنشئ|انشئ|اعمل|اعملّي|create|make)\s+"""
            r"""(?:مجلد|فولدر|folder|directory)\s+"""
            r"""(?:(?:على|في)\s+(?:سطح المكتب|الديسكتوب|desktop)\s+)?"""
            r"""(?:(?:باسم|اسمه|اسم|named)\s+)?["']?([^"'\r\n]+?)["']?\s*""",
            text,
            flags=re.IGNORECASE,
        )
        if folder:
            name = folder.group(1).strip().rstrip(".")
            if name and name not in {".", ".."} and not re.search(r"[\\/]", name):
                desktop = bool(re.search(r"(?:على|في)\s+(?:سطح المكتب|الديسكتوب|desktop)", text, re.I))
                return {
                    "tool": "filesystem",
                    "action": "create_directory",
                    "arguments": {"path": f"Desktop/{name}" if desktop else name},
                }

        file_match = re.fullmatch(
            r"""\s*(?:أنشئ|انشئ|اعمل|create|make)\s+(?:ملف|فايل|file)\s+"""
            r"""(?:(?:باسم|اسمه|اسم|named)\s+)?([^\s"'<>|]+)\s+"""
            r"""(?:بمحتوى|محتواه|بمحتويات|with\s+content)\s+(.+?)\s*""",
            text,
            flags=re.IGNORECASE,
        )
        if file_match:
            name, content = file_match.group(1).strip(), file_match.group(2).strip()
            if name and name not in {".", ".."} and not re.search(r"[\\/]", name) and content:
                desktop = bool(re.search(r"(?:على|في)\s+(?:سطح المكتب|الديسكتوب|desktop)", text, re.I))
                return {
                    "tool": "filesystem",
                    "action": "write_file",
                    "arguments": {"path": f"Desktop/{name}" if desktop else name, "content": content},
                }

        apps = {
            "chrome": "chrome",
            "كروم": "chrome",
            "google chrome": "chrome",
            "notepad": "notepad",
            "المفكرة": "notepad",
            "calculator": "calc",
            "الحاسبة": "calc",
            "الآلة الحاسبة": "calc",
            "explorer": "explorer",
            "مستكشف الملفات": "explorer",
            "vscode": "code",
            "vs code": "code",
            "visual studio code": "code",
        }
        app_pattern = re.fullmatch(
            r"\s*(?:افتح|إفتح|شغل|شغّل|شغلّي|launch|open)\s+(.+?)\s*",
            text,
            flags=re.IGNORECASE,
        )
        if app_pattern:
            requested = app_pattern.group(1).strip().casefold()
            command = apps.get(requested)
            if command:
                return {
                    "tool": "desktop",
                    "action": "open_app",
                    "arguments": {"command": command},
                }
        return None

    def _dispatch(self, call: dict[str, Any]) -> dict[str, Any]:
        """Validate tool/action/arguments before the compatibility executor runs."""
        tool = str(call.get("tool") or "").strip()
        action = str(call.get("action") or "").strip()
        arguments = call.get("arguments") or {}
        try:
            self.registry.validate_call(tool, action, arguments)
        except Exception as exc:
            return {
                "success": False,
                "error": f"Tool validation failed: {exc}",
                "tool": tool,
                "action": action,
            }
        return self.executor.execute(tool, action, **arguments)

    def _print_step(self, step, plan):
        print("\n" + "=" * 78)
        print(f"KAREEM_AGENT V8 | THINK / STEP {step}/{self.max_steps}")
        print("=" * 78)
        print("GOAL:")
        print(json.dumps(self.cognition.goal, ensure_ascii=False, indent=2))
        print("COGNITION:")
        print(json.dumps(self.cognition.compact(), ensure_ascii=False, indent=2, default=str)[:16000])
        print("PLAN:")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    def _observe(self, tool, action, args, result, internal=False):
        item = {
            "ts": time.time(), "role": "tool", "tool": tool, "action": action,
            "arguments": args, "result": result, "internal": bool(internal),
        }
        self.history.append(item)
        self.trace.emit("tool_result", internal=internal, tool=tool, action=action, arguments=args, result=result)
        return item

    def _recent_knowledge(self, user_message):
        try:
            return self.knowledge.search(user_message, limit=6)
        except Exception:
            return []

    def _auto_browser_inspect(self, action: str, result: dict[str, Any]) -> None:
        if action in {"inspect", "screenshot", "wait_for"}:
            self.cognition.observe(result, self.history)
            return
        if not isinstance(result, dict) or not result.get("success"):
            return
        # Every navigation/mutation action gets a fresh perception pass. This is
        # the key architectural change: the agent reasons about the page it just
        # reached instead of assuming the next step is valid.
        if action in {"open_url", "click", "fill", "press_key", "navigate", "type_text"}:
            observed = self.executor.execute("browser", "inspect")
            self._observe("browser", "inspect", {}, observed, internal=True)
            self.cognition.observe(observed, self.history)
            self.trace.emit("perception", state=self.cognition.state, page=self.cognition.page)

    def _verified_answer(self) -> str:
        state = self.cognition.state
        page = self.cognition.page
        goal = self.cognition.goal
        if state.get("eligible_candidates"):
            rows = state["eligible_candidates"]
            lines = ["تم التحقق من النتائج المطلوبة:"]
            for i, item in enumerate(rows[: int(goal.get("result_count") or len(rows))], 1):
                name = item.get("name") or "غير معروف"
                price = item.get("price")
                currency = item.get("currency") or goal.get("currency") or ""
                url = item.get("url") or ""
                lines.append(f"{i}. {name} — {price} {currency} — {url}")
            return "\n".join(lines)
        return f"تم تنفيذ المهمة والتحقق منها. الصفحة الحالية: {page.get('url') or 'غير متاحة'}"

    def run(self, user_message):
        self.history = [{"role": "user", "content": user_message}]

        # Deterministic fast path: never invoke the local LLM for these exact,
        # low-ambiguity filesystem/application-launch requests.
        direct_call = self._pre_route(user_message)
        if direct_call is not None:
            result = self._dispatch(direct_call)
            self._observe(
                direct_call["tool"], direct_call["action"],
                direct_call["arguments"], result,
            )
            self.trace.emit("deterministic_route", call=direct_call, result=result)
            return result
        self.trace.emit("run_start", user_message=user_message)
        try:
            goal = self.cognition.start(user_message)
            self.trace.emit("goal_understood", goal=goal)
        except Exception as exc:
            return {"success": False, "error": f"Goal understanding failed: {exc}"}

        same_signature = None
        repeat_without_change = 0
        final_answer = None

        for step in range(1, self.max_steps + 1):
            # Hard completion gate before planner invocation. The planner is never
            # allowed to override a deterministic world-state proof.
            if self.cognition.state.get("complete"):
                final_answer = self._verified_answer()
                break

            cognition_context = self.cognition.compact()
            cognition_context["hints"] = self.cognition.candidate_action_hints()
            try:
                plan = self.planner.plan(
                    user_message=user_message,
                    history=self.history,
                    tools=self.registry.describe(),
                    memory=self.memory.search(user_message, limit=6),
                    knowledge=self._recent_knowledge(user_message),
                    cognition=cognition_context,
                )
            except Exception as exc:
                self.trace.emit("planner_failure", error=str(exc))
                reflection = self.cognition.on_failure(str(exc), self.history)
                self.history.append({"role": "system", "content": json.dumps(reflection, ensure_ascii=False)})
                continue

            self._print_step(step, plan)
            self.trace.emit("plan", step=step, plan=plan)

            if plan.get("type") == "chat":
                content = str(plan.get("content") or "").strip()
                if content.startswith("__TASK_FAILED__"):
                    self.cognition.record_experience(
                        user_message,
                        {"success": False, "state": self.cognition.state, "error": content},
                        self.history,
                        self.cognition.reflection_note,
                    )
                    return {
                        "success": False,
                        "error": content.replace("__TASK_FAILED__", "", 1).strip(),
                        "goal": self.cognition.goal,
                        "state": self.cognition.state,
                        "history": self.history[-15:],
                    }
                if content == "__VERIFIED_COMPLETE__" or self.cognition.state.get("complete"):
                    final_answer = self._verified_answer()
                    break
                # A natural language response before proof is treated as a planning failure,
                # not as task completion.
                self.history.append({"role": "assistant", "content": content, "note": "unverified_chat"})
                if content:
                    reflection = self.cognition.on_failure("Planner returned chat before proof", self.history)
                    self.history.append({"role": "system", "content": json.dumps(reflection, ensure_ascii=False)})
                continue

            tool = str(plan.get("tool") or "").strip()
            action = str(plan.get("action") or "").strip()
            args = plan.get("arguments") or {}
            if not tool or not action:
                self.history.append({"role": "system", "content": "Invalid tool call."})
                continue

            print(f"\nACT {tool}.{action}")
            print(json.dumps(args, ensure_ascii=False, indent=2))
            result = self._dispatch({"tool": tool, "action": action, "arguments": args})
            print("\nOBSERVE:")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:24000])
            self._observe(tool, action, args, result)
            self._auto_browser_inspect(action, result)

            if isinstance(result, dict) and not result.get("success", True):
                reflection = self.cognition.on_failure(result, self.history)
                self.history.append({"role": "system", "content": json.dumps(reflection, ensure_ascii=False)})
                self.trace.emit("reflection", reflection=reflection)

            signature = json.dumps({
                "tool": tool,
                "action": action,
                "arguments": args,
                "fingerprint": self.cognition.page.get("fingerprint"),
            }, ensure_ascii=False, sort_keys=True)
            if signature == same_signature:
                repeat_without_change += 1
            else:
                same_signature = signature
                repeat_without_change = 0
            if repeat_without_change >= 2:
                reflection = self.cognition.on_failure("Repeated action on the same perceived state", self.history)
                self.history.append({"role": "system", "content": json.dumps({
                    "LOOP_GUARD": True,
                    "reflection": reflection,
                    "instruction": "STOP: the world state did not change after repeated identical actions.",
                }, ensure_ascii=False)})
                self.cognition.state = {
                    **self.cognition.state,
                    "status": "loop_blocked",
                    "complete": False,
                    "loop_guard": True,
                }
                self.cognition.record_experience(
                    user_message,
                    {"success": False, "state": self.cognition.state, "error": "Loop guard blocked a repeated action."},
                    self.history,
                    self.cognition.reflection_note,
                )
                return {
                    "success": False,
                    "error": "تم إيقاف التنفيذ تلقائيًا لأن الحالة لم تتغير بعد تكرار نفس الفعل.",
                    "goal": self.cognition.goal,
                    "state": self.cognition.state,
                    "history": self.history[-15:],
                }

            if self.cognition.state.get("complete"):
                final_answer = self._verified_answer()
                break

        if final_answer is None:
            self.cognition.record_experience(
                user_message,
                {"success": False, "state": self.cognition.state},
                self.history,
                self.cognition.reflection_note,
            )
            return {
                "success": False,
                "error": f"Task stopped after {self.max_steps} adaptive cognition steps.",
                "goal": self.cognition.goal,
                "state": self.cognition.state,
                "history": self.history[-15:],
            }

        outcome = {"success": True, "state": self.cognition.state, "answer": final_answer}
        self.cognition.record_experience(user_message, outcome, self.history, self.cognition.reflection_note)
        self.trace.emit("run_complete", outcome=outcome)
        return final_answer
