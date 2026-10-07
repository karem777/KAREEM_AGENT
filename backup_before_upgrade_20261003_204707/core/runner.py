import json
import re
from pathlib import PureWindowsPath

from brain.planner import Planner
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from core.task_manager import TaskManager


class AgentRunner:

    TOOL_ALIASES = {
        "file": "filesystem",
        "files": "filesystem",
        "fs": "filesystem",
        "system_tool": "system",
    }

    ACTION_ALIASES = {
        "mkdir": "create_directory",
        "make_directory": "create_directory",
        "create_folder": "create_directory",
        "make_folder": "create_directory",

        "write": "write_file",
        "create_file": "write_file",

        "read": "read_file",

        "list": "list_directory",
        "ls": "list_directory",

        "rm": "delete",
        "remove": "delete",

        "mv": "move",
        "cp": "copy",
    }

    def __init__(
        self,
        workspace="workspace",
        max_steps=20
    ):

        self.workspace = workspace
        self.max_steps = max_steps

        self.planner = Planner()

        self.registry = ToolRegistry(
            workspace
        )

        self.executor = ToolExecutor(
            self.registry
        )

        self.tasks = TaskManager()

        # عملية حساسة متوقفة لحين موافقة المستخدم
        self.pending_approval = None

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    def _clean_text(self, text):

        return re.sub(
            r"\s+",
            " ",
            str(text).strip()
        )

    def _is_absolute_path(self, path):

        path = str(path).strip()

        if re.match(
            r"^[A-Za-z]:[\\/]",
            path
        ):
            return True

        if path.startswith("\\\\"):
            return True

        return False

    # =========================================================
    # SPECIAL LOCATIONS
    # =========================================================

    def _location_alias(self, text):

        text = self._clean_text(
            text
        ).lower()

        replacements = {

            "سطح المكتب":
                "Desktop",

            "على سطح المكتب":
                "Desktop",

            "الديسكتوب":
                "Desktop",

            "desktop":
                "Desktop",

            "المستندات":
                "Documents",

            "مجلد المستندات":
                "Documents",

            "documents":
                "Documents",

            "document":
                "Documents",

            "التنزيلات":
                "Downloads",

            "التنزيل":
                "Downloads",

            "downloads":
                "Downloads",

            "download":
                "Downloads",

            "الهوم":
                "Home",

            "home":
                "Home",
        }

        for key, value in replacements.items():

            if text == key:
                return value

        return None

    def _normalize_location_path(
        self,
        path
    ):

        path = self._clean_text(
            path
        )

        alias = self._location_alias(
            path
        )

        if alias:
            return alias

        return path

    # =========================================================
    # PATH + FILENAME HELPERS
    # =========================================================

    def _join_location(
        self,
        location,
        filename
    ):

        location = self._normalize_location_path(
            location
        )

        filename = self._clean_text(
            filename
        )

        if not filename:
            return location

        if self._is_absolute_path(
            filename
        ):
            return filename

        if location in [
            "Desktop",
            "Documents",
            "Downloads",
            "Home"
        ]:

            return (
                f"{location}/{filename}"
            )

        return filename

    def _basename(self, path):

        path = str(
            path
        ).strip()

        path = path.rstrip(
            "\\/"
        )

        if not path:
            return ""

        return PureWindowsPath(
            path
        ).name

    # =========================================================
    # FIND LOCATION IN ARABIC/ENGLISH
    # =========================================================

    def _extract_location(
        self,
        text
    ):

        text = self._clean_text(
            text
        )

        patterns = [

            r"(?:على|في|إلى|الى|من)\s+(سطح المكتب|الديسكتوب|desktop)",

            r"(?:على|في|إلى|الى|من)\s+(المستندات|documents|document)",

            r"(?:على|في|إلى|الى|من)\s+(التنزيلات|التنزيل|downloads|download)",

            r"(?:to|from)\s+(desktop|documents|downloads)",

        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                return self._normalize_location_path(
                    match.group(1)
                )

        return None

    # =========================================================
    # DETERMINISTIC MOVE
    # =========================================================

    def _parse_move_command(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        move_words = [
            "انقل",
            "نقل",
            "حرك",
            "حرّك",
            "move"
        ]

        if not any(
            text.lower().startswith(word)
            for word in move_words
        ):
            return None

        # -----------------------------------------------------
        # Arabic:
        #
        # انقل hello.txt من سطح المكتب إلى Documents
        # -----------------------------------------------------

        pattern = re.compile(
            r"^(?:انقل|نقل|حرك|حرّك)\s+(.+?)"
            r"\s+من\s+(.+?)"
            r"\s+(?:إلى|الى)\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if match:

            filename = self._clean_text(
                match.group(1)
            )

            source_location = self._normalize_location_path(
                match.group(2)
            )

            destination_location = self._normalize_location_path(
                match.group(3)
            )

            # Remove descriptive words
            source_location = re.sub(
                r"^(?:على|في)\s+",
                "",
                source_location,
                flags=re.IGNORECASE
            )

            destination_location = re.sub(
                r"^(?:على|في)\s+",
                "",
                destination_location,
                flags=re.IGNORECASE
            )

            source = self._join_location(
                source_location,
                filename
            )

            destination = self._join_location(
                destination_location,
                filename
            )

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool": "filesystem",
                        "action": "move",
                        "arguments": {
                            "source": source,
                            "destination": destination
                        }
                    }
                ]
            }

        # -----------------------------------------------------
        # Arabic:
        #
        # انقل hello.txt إلى Documents
        # -----------------------------------------------------

        pattern = re.compile(
            r"^(?:انقل|نقل|حرك|حرّك)\s+(.+?)"
            r"\s+(?:إلى|الى)\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if match:

            filename = self._clean_text(
                match.group(1)
            )

            destination_location = self._normalize_location_path(
                match.group(2)
            )

            destination_location = re.sub(
                r"^(?:على|في)\s+",
                "",
                destination_location,
                flags=re.IGNORECASE
            )

            source = filename

            destination = self._join_location(
                destination_location,
                self._basename(filename)
            )

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool": "filesystem",
                        "action": "move",
                        "arguments": {
                            "source": source,
                            "destination": destination
                        }
                    }
                ]
            }

        # -----------------------------------------------------
        # English:
        #
        # move hello.txt from Desktop to Documents
        # -----------------------------------------------------

        pattern = re.compile(
            r"^move\s+(.+?)"
            r"\s+from\s+(.+?)"
            r"\s+to\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if match:

            filename = self._clean_text(
                match.group(1)
            )

            source_location = self._normalize_location_path(
                match.group(2)
            )

            destination_location = self._normalize_location_path(
                match.group(3)
            )

            source = self._join_location(
                source_location,
                filename
            )

            destination = self._join_location(
                destination_location,
                self._basename(filename)
            )

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool": "filesystem",
                        "action": "move",
                        "arguments": {
                            "source": source,
                            "destination": destination
                        }
                    }
                ]
            }

        return None

    # =========================================================
    # DETERMINISTIC COPY
    # =========================================================

    def _parse_copy_command(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        if not (
            text.lower().startswith("انسخ")
            or text.lower().startswith("انسخلي")
            or text.lower().startswith("copy")
        ):
            return None

        # Arabic:
        # انسخ hello.txt من سطح المكتب إلى Documents

        pattern = re.compile(
            r"^(?:انسخ(?:لي)?|copy)\s+(.+?)"
            r"\s+من\s+(.+?)"
            r"\s+(?:إلى|الى)\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if match:

            filename = self._clean_text(
                match.group(1)
            )

            source_location = self._normalize_location_path(
                match.group(2)
            )

            destination_location = self._normalize_location_path(
                match.group(3)
            )

            source = self._join_location(
                source_location,
                filename
            )

            destination = self._join_location(
                destination_location,
                self._basename(filename)
            )

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool": "filesystem",
                        "action": "copy",
                        "arguments": {
                            "source": source,
                            "destination": destination
                        }
                    }
                ]
            }

        # Arabic:
        # انسخ hello.txt إلى Documents

        pattern = re.compile(
            r"^(?:انسخ(?:لي)?|copy)\s+(.+?)"
            r"\s+(?:إلى|الى|إلي|الي)\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if match:

            filename = self._clean_text(
                match.group(1)
            )

            destination_location = self._normalize_location_path(
                match.group(2)
            )

            destination = self._join_location(
                destination_location,
                self._basename(filename)
            )

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool": "filesystem",
                        "action": "copy",
                        "arguments": {
                            "source": filename,
                            "destination": destination
                        }
                    }
                ]
            }

        return None

    # =========================================================
    # DETERMINISTIC RENAME
    # =========================================================

    def _parse_rename_command(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        pattern = re.compile(
            r"^(?:غير اسم|غيّر اسم|غير اسم الملف|rename)"
            r"\s+(.+?)"
            r"\s+(?:إلى|الى|لـ|ل)"
            r"\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if not match:
            return None

        old_name = self._clean_text(
            match.group(1)
        )

        new_name = self._clean_text(
            match.group(2)
        )

        return {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "filesystem",
                    "action": "rename",
                    "arguments": {
                        "path": old_name,
                        "new_name": new_name
                    }
                }
            ]
        }

    # =========================================================
    # DETERMINISTIC DELETE
    # =========================================================

    def _parse_delete_command(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        pattern = re.compile(
            r"^(?:امسح|احذف|حذف|احذفلي|امسحلي|delete|remove)"
            r"\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if not match:
            return None

        path = self._clean_text(
            match.group(1)
        )

        return {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "filesystem",
                    "action": "delete",
                    "arguments": {
                        "path": path
                    }
                }
            ]
        }

    # =========================================================
    # DETERMINISTIC CREATE DIRECTORY
    # =========================================================

    def _parse_create_directory(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        pattern = re.compile(
            r"^(?:اعمل|أنشئ|انشئ|اعمللي|أنشئلي)"
            r"\s+(?:فولدر|مجلد)"
            r"(?:\s+(?:في|على)\s+(.+?))?"
            r"\s+(?:اسمه|اسمو|باسم)\s+(.+?)\s*$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if not match:
            return None

        location = match.group(1)
        name = self._clean_text(
            match.group(2)
        )

        if location:

            location = self._normalize_location_path(
                location
            )

            path = self._join_location(
                location,
                name
            )

        else:

            path = name

        return {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "filesystem",
                    "action": "create_directory",
                    "arguments": {
                        "path": path
                    }
                }
            ]
        }

    # =========================================================
    # DETERMINISTIC FILE CREATION
    # =========================================================

    def _parse_create_file(
        self,
        message
    ):

        text = self._clean_text(
            message
        )

        pattern = re.compile(
            r"^(?:اعمل|أنشئ|انشئ|اعمللي|أنشئلي)"
            r"\s+(?:ملف|فايل|file)"
            r"(?:\s+(?:في|على)\s+(.+?))?"
            r"\s+(?:اسمه|اسمو|باسم)\s+(.+?)"
            r"(?:\s+(?:واكتب فيه|واكتب جواه|محتواه)\s+(.+))?$",
            re.IGNORECASE
        )

        match = pattern.match(
            text
        )

        if not match:
            return None

        location = match.group(1)
        filename = self._clean_text(
            match.group(2)
        )

        content = match.group(3) or ""

        if location:

            location = self._normalize_location_path(
                location
            )

            path = self._join_location(
                location,
                filename
            )

        else:

            path = filename

        return {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "filesystem",
                    "action": "write_file",
                    "arguments": {
                        "path": path,
                        "content": content
                    }
                }
            ]
        }

    # =========================================================
    # DETERMINISTIC FILE COMMANDS
    # =========================================================

    def _deterministic_filesystem_plan(
        self,
        message
    ):

        # Order matters.

        parsers = [

            self._parse_move_command,

            self._parse_copy_command,

            self._parse_rename_command,

            self._parse_delete_command,

            self._parse_create_directory,

            self._parse_create_file,
        ]

        for parser in parsers:

            try:

                result = parser(
                    message
                )

                if result:

                    print(
                        "\nDETERMINISTIC FILESYSTEM PLAN:"
                    )

                    print(
                        json.dumps(
                            result,
                            ensure_ascii=False,
                            indent=2
                        )
                    )

                    return result

            except Exception as e:

                print(
                    f"Parser error: {e}"
                )

        return None

    # =========================================================
    # APPROVAL
    # =========================================================

    def _is_approval(
        self,
        message
    ):

        text = str(
            message
        ).strip().lower()

        return text in [

            "موافق",
            "وافق",
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
            "okay",
            "نعم",
        ]

    def _is_rejection(
        self,
        message
    ):

        text = str(
            message
        ).strip().lower()

        return text in [

            "لا",
            "الغاء",
            "إلغاء",
            "الغ",
            "cancel",
            "no",
            "رفض",
            "ارفض",
        ]

    def _execute_approved_operation(
        self
    ):

        if not self.pending_approval:

            return (
                "مفيش عملية معلقة محتاجة موافقة."
            )

        pending = (
            self.pending_approval
        )

        self.pending_approval = None

        tool = pending["tool"]
        action = pending["action"]

        arguments = dict(
            pending["arguments"]
        )

        if (
            tool == "system"
            and action == "run_command"
        ):

            arguments["approved"] = True

        result = self.executor.execute(
            tool,
            action,
            **arguments
        )

        if result.get(
            "success",
            False
        ):

            return (
                "تمت الموافقة والتنفيذ بنجاح.\n\n"
                + self._format_result(
                    result
                )
            )

        return (
            "تمت الموافقة، لكن التنفيذ فشل.\n\n"
            + self._format_result(
                result
            )
        )

    # =========================================================
    # FORMAT RESULT
    # =========================================================

    def _format_result(
        self,
        result
    ):

        if not isinstance(
            result,
            dict
        ):

            return str(result)

        if "result" in result:

            return str(
                result["result"]
            )

        if "stdout" in result:

            output = result.get(
                "stdout",
                ""
            )

            error = result.get(
                "stderr",
                ""
            )

            text = ""

            if output:
                text += output

            if error:
                text += (
                    "\n\nERROR:\n"
                    + error
                )

            return text.strip()

        if "error" in result:

            return str(
                result["error"]
            )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )

    # =========================================================
    # NORMALIZE TOOL CALL
    # =========================================================

    def _normalize_call(
        self,
        call
    ):

        if not isinstance(
            call,
            dict
        ):
            return None

        tool = str(
            call.get(
                "tool",
                ""
            )
        ).strip()

        action = str(
            call.get(
                "action",
                ""
            )
        ).strip()

        arguments = call.get(
            "arguments",
            {}
        )

        if not isinstance(
            arguments,
            dict
        ):

            arguments = {}

        tool = self.TOOL_ALIASES.get(
            tool.lower(),
            tool
        )

        action = self.ACTION_ALIASES.get(
            action.lower(),
            action
        )

        for key in [
            "path",
            "source",
            "destination",
            "cwd"
        ]:

            if key in arguments:

                arguments[key] = str(
                    arguments[key]
                ).strip()

        return {
            "tool": tool,
            "action": action,
            "arguments": arguments
        }

    # =========================================================
    # LOCATION FIX FOR AI-GENERATED CALLS
    # =========================================================

    def _fix_user_location(
        self,
        call,
        user_message
    ):

        if not call:
            return call

        if call["tool"] != "filesystem":
            return call

        message = str(
            user_message
        ).lower()

        wants_desktop = any(
            x in message
            for x in [
                "سطح المكتب",
                "desktop",
            ]
        )

        wants_documents = any(
            x in message
            for x in [
                "المستندات",
                "documents",
                "document",
            ]
        )

        wants_downloads = any(
            x in message
            for x in [
                "التنزيلات",
                "downloads",
                "download",
            ]
        )

        # Do NOT modify move/copy destination blindly.
        # Deterministic parsers already handled those commands.

        if call["action"] in [
            "move",
            "copy",
        ]:

            return call

        if "path" not in call["arguments"]:

            return call

        value = str(
            call["arguments"]["path"]
        ).strip()

        lower = value.lower()

        if wants_desktop:

            if not (
                lower.startswith(
                    "desktop/"
                )
                or lower.startswith(
                    "desktop\\"
                )
                or lower == "desktop"
                or self._is_absolute_path(
                    value
                )
            ):

                call["arguments"]["path"] = (
                    "Desktop/" + value
                )

        elif wants_documents:

            if not (
                lower.startswith(
                    "documents/"
                )
                or lower.startswith(
                    "documents\\"
                )
                or lower == "documents"
                or self._is_absolute_path(
                    value
                )
            ):

                call["arguments"]["path"] = (
                    "Documents/" + value
                )

        elif wants_downloads:

            if not (
                lower.startswith(
                    "downloads/"
                )
                or lower.startswith(
                    "downloads\\"
                )
                or lower == "downloads"
                or self._is_absolute_path(
                    value
                )
            ):

                call["arguments"]["path"] = (
                    "Downloads/" + value
                )

        return call

    # =========================================================
    # SIGNATURE
    # =========================================================

    def _signature(
        self,
        call
    ):

        return json.dumps(
            call,
            ensure_ascii=False,
            sort_keys=True
        )

    # =========================================================
    # TASK STEP
    # =========================================================

    def _add_task_step(
        self,
        task,
        step,
        data
    ):

        if task is None:
            return

        try:

            self.tasks.add_step(
                task,
                step,
                data
            )

            return

        except Exception:
            pass

        try:

            self.tasks.add_step(
                task,
                data
            )

        except Exception:
            pass

    # =========================================================
    # RUN
    # =========================================================

    def run(
        self,
        user_message
    ):

        # =====================================================
        # PENDING APPROVAL
        # =====================================================

        if self.pending_approval:

            if self._is_approval(
                user_message
            ):

                return (
                    self._execute_approved_operation()
                )

            if self._is_rejection(
                user_message
            ):

                operation = (
                    self.pending_approval.get(
                        "operation",
                        ""
                    )
                )

                self.pending_approval = None

                return (
                    "تم إلغاء العملية:\n"
                    + operation
                )

            return (
                "فيه عملية حساسة مستنية موافقتك.\n\n"
                "العملية:\n"
                + self.pending_approval.get(
                    "operation",
                    ""
                )
                + "\n\n"
                "السبب:\n"
                + self.pending_approval.get(
                    "reason",
                    ""
                )
                + "\n\n"
                "اكتب «موافق» للتنفيذ أو «إلغاء»."
            )

        # =====================================================
        # DETERMINISTIC FILESYSTEM LAYER
        # =====================================================

        deterministic_plan = (
            self._deterministic_filesystem_plan(
                user_message
            )
        )

        if deterministic_plan:

            return self._execute_plan(
                user_message,
                deterministic_plan
            )

        # =====================================================
        # AI AGENT LOOP
        # =====================================================

        history = []

        successful_calls = set()

        try:

            task = self.tasks.create(
                user_message
            )

        except Exception:

            task = None

        for step in range(
            1,
            self.max_steps + 1
        ):

            print(
                f"\n{'=' * 60}"
            )

            print(
                f"THINK / STEP {step}/{self.max_steps}"
            )

            print(
                f"{'=' * 60}"
            )

            plan = self.planner.plan(
                user_message,
                tools=self.registry.describe(),
                history=history
            )

            print(
                json.dumps(
                    plan,
                    ensure_ascii=False,
                    indent=2
                )
            )

            if not isinstance(
                plan,
                dict
            ):

                return (
                    "حدث خطأ في التخطيط."
                )

            plan_type = plan.get(
                "type"
            )

            if plan_type == "chat":

                content = str(
                    plan.get(
                        "content",
                        ""
                    )
                ).strip()

                if not content:

                    return "تم تنفيذ الطلب."

                try:

                    if task is not None:

                        self.tasks.complete(
                            task,
                            content
                        )

                except Exception:
                    pass

                print(
                    "\nTASK COMPLETED"
                )

                return content

            if plan_type == "invalid":

                history.append({

                    "step":
                        step,

                    "type":
                        "planner_error",

                    "content":
                        plan.get(
                            "content",
                            ""
                        )
                })

                continue

            if plan_type != "tool_calls":

                history.append({

                    "step":
                        step,

                    "type":
                        "planner_error",

                    "content":
                        str(plan)
                })

                continue

            calls = plan.get(
                "calls",
                []
            )

            if not isinstance(
                calls,
                list
            ):

                continue

            executed = False

            for raw_call in calls:

                call = self._normalize_call(
                    raw_call
                )

                if not call:
                    continue

                call = self._fix_user_location(
                    call,
                    user_message
                )

                signature = self._signature(
                    call
                )

                if signature in successful_calls:

                    history.append({

                        "step":
                            step,

                        "type":
                            "duplicate_skipped",

                        "call":
                            call
                    })

                    continue

                tool = call["tool"]
                action = call["action"]
                arguments = call[
                    "arguments"
                ]

                print(
                    f"\nACT {tool}.{action}"
                )

                print(
                    json.dumps(
                        arguments,
                        ensure_ascii=False,
                        indent=2
                    )
                )

                result = self.executor.execute(
                    tool,
                    action,
                    **arguments
                )

                print(
                    "\nOBSERVE:"
                )

                print(
                    json.dumps(
                        result,
                        ensure_ascii=False,
                        indent=2
                    )
                )

                executed = True

                success = bool(
                    result.get(
                        "success",
                        False
                    )
                )

                history.append({

                    "step":
                        step,

                    "type":
                        "tool_result",

                    "tool":
                        tool,

                    "action":
                        action,

                    "arguments":
                        arguments,

                    "success":
                        success,

                    "result":
                        result
                })

                if success:

                    successful_calls.add(
                        signature
                    )

                self._add_task_step(
                    task,
                    step,
                    {
                        "tool":
                            tool,

                        "action":
                            action,

                        "arguments":
                            arguments,

                        "result":
                            result
                    }
                )

                # =================================================
                # APPROVAL
                # =================================================

                if result.get(
                    "requires_approval",
                    False
                ):

                    self.pending_approval = {

                        "tool":
                            tool,

                        "action":
                            action,

                        "arguments":
                            arguments,

                        "operation":
                            result.get(
                                "operation",
                                f"{tool}.{action}"
                            ),

                        "reason":
                            result.get(
                                "reason",
                                ""
                            )
                    }

                    return (
                        "⚠️ العملية دي محتاجة موافقتك.\n\n"
                        "العملية:\n"
                        + self.pending_approval[
                            "operation"
                        ]
                        + "\n\n"
                        "السبب:\n"
                        + self.pending_approval[
                            "reason"
                        ]
                        + "\n\n"
                        "اكتب «موافق» للتنفيذ أو «إلغاء»."
                    )

            if not executed:

                return (
                    "العملية المطلوبة تم تنفيذها بالفعل."
                )

        return (
            "وصلت المهمة للحد الأقصى من الخطوات "
            "من غير تأكيد اكتمالها."
        )

    # =========================================================
    # EXECUTE A PLAN
    # =========================================================

    def _execute_plan(
        self,
        user_message,
        plan
    ):

        try:

            task = self.tasks.create(
                user_message
            )

        except Exception:

            task = None

        calls = plan.get(
            "calls",
            []
        )

        if not calls:

            return (
                "لم أجد عملية مناسبة لتنفيذ الطلب."
            )

        for index, raw_call in enumerate(
            calls,
            start=1
        ):

            call = self._normalize_call(
                raw_call
            )

            if not call:
                continue

            tool = call["tool"]
            action = call["action"]
            arguments = call[
                "arguments"
            ]

            print(
                f"\nACT {tool}.{action}"
            )

            print(
                json.dumps(
                    arguments,
                    ensure_ascii=False,
                    indent=2
                )
            )

            result = self.executor.execute(
                tool,
                action,
                **arguments
            )

            print(
                "\nOBSERVE:"
            )

            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2
                )
            )

            self._add_task_step(
                task,
                index,
                {
                    "tool":
                        tool,

                    "action":
                        action,

                    "arguments":
                        arguments,

                    "result":
                        result
                }
            )

            # -------------------------------------------------
            # Approval
            # -------------------------------------------------

            if result.get(
                "requires_approval",
                False
            ):

                self.pending_approval = {

                    "tool":
                        tool,

                    "action":
                        action,

                    "arguments":
                        arguments,

                    "operation":
                        result.get(
                            "operation",
                            f"{tool}.{action}"
                        ),

                    "reason":
                        result.get(
                            "reason",
                            ""
                        )
                }

                return (
                    "⚠️ العملية دي محتاجة موافقتك.\n\n"
                    "العملية:\n"
                    + self.pending_approval[
                        "operation"
                    ]
                    + "\n\n"
                    "السبب:\n"
                    + self.pending_approval[
                        "reason"
                    ]
                    + "\n\n"
                    "اكتب «موافق» للتنفيذ أو «إلغاء»."
                )

            # -------------------------------------------------
            # Failure
            # -------------------------------------------------

            if not result.get(
                "success",
                False
            ):

                return (
                    "فشل تنفيذ الطلب:\n\n"
                    + self._format_result(
                        result
                    )
                )

        try:

            if task is not None:

                self.tasks.complete(
                    task,
                    "تم تنفيذ الطلب بنجاح."
                )

        except Exception:
            pass

        return (
            "تم تنفيذ الطلب بنجاح.\n\n"
            + self._format_result(
                result
            )
        )