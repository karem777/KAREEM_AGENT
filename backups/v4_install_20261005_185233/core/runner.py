import json
import re

from brain.analyst import AnalyticalBrain
from brain.completion import CompletionJudge
from brain.evidence import EvidenceSummarizer
from brain.planner import Planner
from core.goal_state import GoalState
from core.task_manager import TaskManager
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


class AgentRunner:
    TOOL_ALIASES = {
        "file": "filesystem",
        "files": "filesystem",
        "fs": "filesystem",
        "system_tool": "system",
        "browser_tool": "browser",
    }

    ACTION_ALIASES = {
        "mkdir": "create_directory",
        "make_folder": "create_directory",
        "create_folder": "create_directory",
        "write": "write_file",
        "read": "read_file",
        "ls": "list_directory",
        "list": "list_directory",
        "rm": "delete",
        "remove": "delete",
        "mv": "move",
        "cp": "copy",
    }

    def __init__(self, workspace="workspace", max_steps=24):
        self.workspace = workspace
        self.max_steps = max_steps

        self.analyst = AnalyticalBrain()
        self.planner = Planner()
        self.completion_judge = CompletionJudge()
        self.evidence_summarizer = EvidenceSummarizer()

        self.registry = ToolRegistry(
            workspace
        )
        self.executor = ToolExecutor(
            self.registry
        )
        self.tasks = TaskManager()

        self.pending_approval = None

        self.last_context = {
            "last_tool": None,
            "last_action": None,
            "last_file": None,
            "last_result": None,
            "planner_warning": None,
        }

    def _normalize_url(self, value):
        text = str(
            value or ""
        ).strip()

        match = re.fullmatch(
            r"\[[^\]]+\]\((https?://[^)]+)\)",
            text,
        )

        if match:
            return match.group(1)

        match = re.fullmatch(
            r"\[(https?://[^\]]+)\]",
            text,
        )

        if match:
            return match.group(1)

        return text

    def _normalize_call(self, call):
        if not isinstance(
            call,
            dict,
        ):
            return None

        tool = str(
            call.get(
                "tool",
                "",
            )
        ).strip()

        action = str(
            call.get(
                "action",
                "",
            )
        ).strip()

        arguments = call.get(
            "arguments",
            {},
        )

        if not isinstance(
            arguments,
            dict,
        ):
            arguments = {}

        if "." in tool:
            left, right = tool.split(
                ".",
                1,
            )

            if self.registry.get(
                left
            ) is not None:
                tool = left
                if right:
                    action = right

        tool = self.TOOL_ALIASES.get(
            tool.lower(),
            tool,
        )

        action = self.ACTION_ALIASES.get(
            action.lower(),
            action,
        )

        if "url" in arguments:
            arguments["url"] = (
                self._normalize_url(
                    arguments["url"]
                )
            )

        return {
            "tool": tool,
            "action": action,
            "arguments": arguments,
        }

    def _signature(self, call):
        return json.dumps(
            call,
            ensure_ascii=False,
            sort_keys=True,
        )

    def _research_task(self, user_message):
        text = str(
            user_message
        ).lower()

        return any(
            word in text
            for word in [
                "ابحث",
                "بحث",
                "جوجل",
                "google",
                "search",
                "web",
                "الويب",
                "اقرأ",
                "read",
                "نتيجة",
                "ملخص",
                "summary",
                "مصدر",
                "source",
            ]
        )

    def _collect_evidence(self, history):
        evidence = []

        for item in history:
            if (
                item.get("type") != "tool_result"
                or not item.get("success")
            ):
                continue

            tool = item.get("tool")
            action = item.get("action")
            result = item.get(
                "result",
                {},
            )

            if not isinstance(
                result,
                dict,
            ):
                continue

            if (
                tool == "web"
                and action == "open_url"
            ):
                text = str(
                    result.get(
                        "text",
                        "",
                    )
                ).strip()

                if (
                    len(text) >= 80
                    and result.get(
                        "meaningful_text",
                        True,
                    )
                ):
                    evidence.append(
                        {
                            "url": self._normalize_url(
                                result.get(
                                    "url",
                                    "",
                                )
                            ),
                            "text": text,
                        }
                    )

            elif (
                tool == "browser"
                and action in {
                    "inspect",
                    "extract_text",
                }
            ):
                text = str(
                    result.get(
                        "text",
                        "",
                    )
                ).strip()

                if len(text) >= 80:
                    evidence.append(
                        {
                            "url": self._normalize_url(
                                result.get(
                                    "url",
                                    "",
                                )
                            ),
                            "text": text,
                        }
                    )

        return evidence

    def _remember(self, call, result):
        self.last_context[
            "last_tool"
        ] = call["tool"]

        self.last_context[
            "last_action"
        ] = call["action"]

        self.last_context[
            "last_result"
        ] = result

        self.last_context[
            "planner_warning"
        ] = None

        if call["action"] in {
            "write_file",
            "create_directory",
        }:
            self.last_context[
                "last_file"
            ] = call["arguments"].get(
                "path"
            )

    def _add_step(self, task, step, data):
        if task is None:
            return

        try:
            self.tasks.add_step(
                task,
                step,
                data,
            )
            return
        except Exception:
            try:
                self.tasks.add_step(
                    task,
                    data,
                )
            except Exception:
                pass

    def _validate_call(self, call):
        tool = self.registry.get(
            call["tool"]
        )

        if tool is None:
            return (
                False,
                f"Unknown tool: {call['tool']}.",
            )

        method = getattr(
            tool,
            call["action"],
            None,
        )

        if (
            method is None
            or call["action"].startswith("_")
        ):
            return (
                False,
                f"Unknown action: {call['tool']}.{call['action']}.",
            )

        return True, ""

    def _execute(self, task, step, call):
        print(f"\nACT {call['tool']}.{call['action']}")
        print(json.dumps(call["arguments"], ensure_ascii=False, indent=2))

        result = self.executor.execute(
            call["tool"],
            call["action"],
            **call["arguments"],
        )

        print("\nOBSERVE:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        self._remember(call, result)
        self._add_step(
            task,
            step,
            {
                "tool": call["tool"],
                "action": call["action"],
                "arguments": call["arguments"],
                "result": result,
            },
        )

        return result

    def _approval(self, text):
        return str(
            text
        ).strip().lower() in {
            "موافق",
            "نعم",
            "نفذ",
            "نفذها",
            "كمل",
            "اكمل",
            "أكمل",
            "yes",
            "approve",
            "approved",
            "confirm",
            "confirmed",
            "ok",
        }

    def _reject(self, text):
        return str(
            text
        ).strip().lower() in {
            "لا",
            "الغاء",
            "إلغاء",
            "cancel",
            "no",
            "رفض",
            "ارفض",
        }

    def _execute_approved(self):
        pending = self.pending_approval
        self.pending_approval = None

        arguments = dict(
            pending["arguments"]
        )

        if (
            pending["tool"] == "system"
            and pending["action"] == "run_command"
        ):
            arguments["approved"] = True

        result = self.executor.execute(
            pending["tool"],
            pending["action"],
            **arguments,
        )

        if result.get(
            "success"
        ):
            return (
                "تمت الموافقة والتنفيذ بنجاح.\n\n"
                + str(
                    result.get(
                        "result",
                        result,
                    )
                )
            )

        return (
            "تمت الموافقة لكن التنفيذ فشل.\n\n"
            + str(
                result.get(
                    "error",
                    result,
                )
            )
        )

    def run(self, user_message):
        if self.pending_approval:
            if self._approval(
                user_message
            ):
                return self._execute_approved()

            if self._reject(
                user_message
            ):
                operation = (
                    self.pending_approval.get(
                        "operation",
                        "",
                    )
                )

                self.pending_approval = None

                return (
                    "تم إلغاء العملية:\n"
                    + operation
                )

            return (
                "فيه عملية حساسة مستنية موافقتك. "
                "اكتب «موافق» أو «إلغاء»."
            )

        try:
            task = self.tasks.create(
                user_message
            )
        except Exception:
            task = None

        analysis = self.analyst.analyze(
            user_message,
            available_tools=self.registry.describe(),
        )

        print("\nANALYTICAL BRAIN:")
        print(
            json.dumps(
                analysis,
                ensure_ascii=False,
                indent=2,
            )
        )

        if not analysis:
            return "ماقدرتش أبني فهم موثوق للطلب."

        mode = analysis.get(
            "mode",
            "execute",
        )

        if mode == "chat":
            answer = analysis.get(
                "answer",
                "",
            ).strip()

            if not answer:
                answer = self.analyst.brain.ask(
                    (
                        "Answer the user naturally in Arabic. "
                        "Do not call tools.\nUSER:\n"
                        + str(user_message)
                    )
                ).strip()

            return answer

        if mode == "clarify":
            return (
                analysis.get(
                    "answer",
                    "",
                ).strip()
                or
                "محتاج توضيح صغير عشان أنفذ الطلب صح."
            )

        goal_state = GoalState(
            analysis
        )

        history = []

        last_success_signature = None
        last_failure_signature = None
        failure_streak = 0
        duplicate_success_streak = 0
        invalid_count = 0

        for step_number in range(
            1,
            self.max_steps + 1,
        ):
            if goal_state.is_complete():
                break

            print(
                "\n" + "=" * 64
            )
            print(
                f"THINK / STEP {step_number}/{self.max_steps}"
            )
            print(
                "=" * 64
            )

            plan = self.planner.plan(
                user_message,
                tools=self.registry.describe(),
                analysis=analysis,
                goal_state=goal_state,
                history=history,
                last_context=self.last_context,
            )

            print(
                "\nPLAN:"
            )
            print(
                json.dumps(
                    plan,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            if plan.get(
                "type"
            ) == "chat":
                # Never let chat override a pending required step.
                if goal_state.is_complete():
                    return str(
                        plan.get(
                            "content",
                            "تم تنفيذ الطلب بنجاح.",
                        )
                    ).strip()

                self.last_context[
                    "planner_warning"
                ] = (
                    "The goal graph is not complete. "
                    "Choose a READY STEP instead of chat."
                )
                continue

            if plan.get(
                "type"
            ) != "tool_calls":
                invalid_count += 1

                if invalid_count >= 2:
                    return (
                        "الـAI فشل مرتين في اختيار خطوة صحيحة، "
                        "فتم إيقاف المهمة."
                    )

                continue

            invalid_count = 0

            calls = plan.get(
                "calls",
                [],
            )

            if (
                not isinstance(
                    calls,
                    list,
                )
                or not calls
            ):
                continue

            call = self._normalize_call(
                calls[0]
            )

            if not call:
                continue

            valid, error = (
                self._validate_call(
                    call
                )
            )

            if not valid:
                self.last_context[
                    "planner_warning"
                ] = error

                print(
                    "\nGUARD:"
                )
                print(error)

                continue

            signature = self._signature(
                call
            )

            # Same successful action repeated immediately.
            if (
                signature
                == last_success_signature
            ):
                duplicate_success_streak += 1

                self.last_context[
                    "planner_warning"
                ] = (
                    "The previous action succeeded. "
                    "Choose a different READY STEP."
                )

                print(
                    "\nGUARD:"
                )
                print(
                    "Skipped immediate duplicate successful action "
                    f"({duplicate_success_streak})."
                )

                if (
                    duplicate_success_streak >= 2
                ):
                    # Give the planner stronger state instead of destroying
                    # the whole goal.
                    self.last_context[
                        "planner_warning"
                    ] = (
                        "DUPLICATE_ACTION_LOOP. "
                        "Do not repeat the previous action. "
                        "Choose another READY STEP."
                    )
                    duplicate_success_streak = 0

                continue

            duplicate_success_streak = 0

            # Same failed action repeated immediately.
            if (
                signature
                == last_failure_signature
            ):
                failure_streak += 1

                self.last_context[
                    "planner_warning"
                ] = (
                    "The previous attempt FAILED. "
                    "Do not repeat the exact same failing call. "
                    "Use a recovery/fallback or change arguments."
                )

                print(
                    "\nRECOVERY GUARD:"
                )
                print(
                    "Skipped immediate duplicate failed action "
                    f"({failure_streak})."
                )

                if failure_streak >= 2:
                    return (
                        "الـAgent كرر نفس العملية الفاشلة بدون تغيير "
                        "الاستراتيجية، فتم إيقافه."
                    )

                continue

            result = self._execute(
                task,
                step_number,
                call,
            )

            success = (
                bool(
                    result.get(
                        "success"
                    )
                )
                if isinstance(
                    result,
                    dict,
                )
                else False
            )

            history.append(
                {
                    "step": step_number,
                    "type": "tool_result",
                    "tool": call["tool"],
                    "action": call["action"],
                    "arguments": call["arguments"],
                    "success": success,
                    "result": result,
                }
            )

            if success:
                last_success_signature = signature
                last_failure_signature = None
                failure_streak = 0

                goal_state.observe_success(
                    call,
                    result,
                )
            else:
                last_failure_signature = signature
                last_success_signature = None

                goal_state.observe_failure(
                    call,
                    result,
                )

            if (
                isinstance(
                    result,
                    dict,
                )
                and result.get(
                    "requires_approval"
                )
            ):
                self.pending_approval = {
                    "tool": call["tool"],
                    "action": call["action"],
                    "arguments": call["arguments"],
                    "operation": result.get(
                        "operation",
                        (
                            f"{call['tool']}."
                            f"{call['action']}"
                        ),
                    ),
                    "reason": result.get(
                        "reason",
                        "",
                    ),
                }

                return (
                    "⚠️ العملية دي محتاجة موافقتك.\n\n"
                    f"العملية: {self.pending_approval['operation']}\n"
                    f"السبب: {self.pending_approval['reason']}\n\n"
                    "اكتب «موافق» أو «إلغاء»."
                )

            # Deterministic goal completion.
            if (
                success
                and goal_state.is_complete()
            ):
                done = (
                    "تم تنفيذ الطلب بنجاح."
                )

                try:
                    if task is not None:
                        self.tasks.complete(
                            task,
                            done,
                        )
                except Exception:
                    pass

                return done

            # AI verifier is diagnostic only when graph is complete.
            if goal_state.is_complete():
                verification = (
                    self.completion_judge.is_complete(
                        user_message,
                        analysis,
                        goal_state,
                        history,
                    )
                )

                print(
                    "\nCOMPLETION JUDGE:"
                )
                print(
                    json.dumps(
                        verification,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

                return "تم تنفيذ الطلب بنجاح."

        return (
            "وصلنا للحد الأقصى من الخطوات "
            "من غير إكمال الهدف."
        )
