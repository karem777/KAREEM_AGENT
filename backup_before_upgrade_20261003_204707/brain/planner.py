import json
import re

from brain.local_brain import LocalBrain


class Planner:

    def __init__(self):

        self.brain = LocalBrain()

    def plan(
        self,
        user_message,
        tools=None,
        history=None
    ):

        tools = tools or {}
        history = history or []

        prompt = f"""
You are KAREEM_AGENT.

You are an autonomous local computer assistant.

Your job is to actually execute the user's request
using the available tools.

AVAILABLE TOOLS:

{json.dumps(
    tools,
    ensure_ascii=False,
    indent=2
)}

EXECUTION HISTORY:

{json.dumps(
    history,
    ensure_ascii=False,
    indent=2
)}

USER REQUEST:

{user_message}

==================================================
STRICT OUTPUT RULES
==================================================

Return ONLY valid JSON.

Never use markdown.

Never explain outside JSON.

Never invent tools.

Never invent actions.

Never return empty tool calls.

Use only the tools and actions listed above.

If a tool operation already succeeded,
do NOT execute the exact same operation again.

==================================================
FILESYSTEM
==================================================

The filesystem is NOT restricted to the workspace.

The agent can work anywhere Windows allows it.

Supported operations include:

- create_directory
- write_file
- read_file
- list_directory
- delete
- rename
- move
- copy

Relative paths are allowed.

Absolute Windows paths are allowed.

Never remove drive letters.

Never convert:

C:\\Users\\Acer\\Desktop\\test

into:

Users\\Acer\\Desktop\\test

==================================================
SPECIAL LOCATIONS
==================================================

Desktop = Windows Desktop.

سطح المكتب = Desktop.

Documents = Windows Documents.

المستندات = Documents.

Downloads = Windows Downloads.

التنزيلات = Downloads.

Home = Windows user home.

==================================================
EXAMPLES
==================================================

User:

اعمل فولدر اسمه test

Return:

{{
  "type": "tool_calls",
  "calls": [
    {{
      "tool": "filesystem",
      "action": "create_directory",
      "arguments": {{
        "path": "test"
      }}
    }}
  ]
}}

User:

اعمل فولدر على سطح المكتب اسمه test

Return:

{{
  "type": "tool_calls",
  "calls": [
    {{
      "tool": "filesystem",
      "action": "create_directory",
      "arguments": {{
        "path": "Desktop/test"
      }}
    }}
  ]
}}

User:

امسح الملف test.txt

Return:

{{
  "type": "tool_calls",
  "calls": [
    {{
      "tool": "filesystem",
      "action": "delete",
      "arguments": {{
        "path": "test.txt"
      }}
    }}
  ]
}}

User:

غير اسم test.txt إلى hello.txt

Return:

{{
  "type": "tool_calls",
  "calls": [
    {{
      "tool": "filesystem",
      "action": "rename",
      "arguments": {{
        "path": "test.txt",
        "new_name": "hello.txt"
      }}
    }}
  ]
}}

User:

انقل test.txt لسطح المكتب

Return:

{{
  "type": "tool_calls",
  "calls": [
    {{
      "tool": "filesystem",
      "action": "move",
      "arguments": {{
        "source": "test.txt",
        "destination": "Desktop/test.txt"
      }}
    }}
  ]
}}

==================================================
WINDOWS COMMANDS
==================================================

Use:

system.run_command

when the user asks you to:

- run a Windows command
- open a program
- launch an application
- check a command
- execute PowerShell
- execute CMD
- perform a system operation

Sensitive system commands are automatically intercepted
by the system tool and require user approval.

Do NOT pretend that an operation succeeded.

Wait for the tool result.

==================================================
SYSTEM INSPECTION
==================================================

Use system tools for:

CPU
RAM
disk
network
processes
OS
diagnostics

==================================================
AFTER SUCCESS
==================================================

If the user's request has been successfully completed,
return:

{{
  "type": "chat",
  "content": "تم تنفيذ الطلب."
}}

Do not repeat successful operations.

If more tool work is actually required,
return another tool call.

If the request cannot be performed with the available tools,
return:

{{
  "type": "chat",
  "content": "لا أستطيع تنفيذ الطلب بالأدوات المتاحة."
}}

==================================================

Now execute the user's request.
"""

        response = self.brain.ask(
            prompt
        )

        if response is None:

            return {
                "type": "invalid",
                "content":
                    "Empty planner response."
            }

        response = str(
            response
        ).strip()

        response = re.sub(
            r"^```(?:json)?\s*",
            "",
            response,
            flags=re.IGNORECASE
        )

        response = re.sub(
            r"\s*```$",
            "",
            response
        )

        response = response.strip()

        try:

            result = json.loads(
                response
            )

        except json.JSONDecodeError:

            match = re.search(
                r"\{[\s\S]*\}",
                response
            )

            if not match:

                return {
                    "type": "invalid",
                    "content": response
                }

            try:

                result = json.loads(
                    match.group(0)
                )

            except json.JSONDecodeError:

                return {
                    "type": "invalid",
                    "content": response
                }

        # =====================================================
        # Normalize single tool_call
        # =====================================================

        if result.get(
            "type"
        ) == "tool_call":

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool":
                            result.get(
                                "tool"
                            ),

                        "action":
                            result.get(
                                "action"
                            ),

                        "arguments":
                            result.get(
                                "arguments",
                                {}
                            )
                    }
                ]
            }

        # =====================================================
        # Normalize role=tool
        # =====================================================

        if result.get(
            "role"
        ) == "tool":

            return {
                "type": "tool_calls",
                "calls": [
                    {
                        "tool":
                            result.get(
                                "tool"
                            ),

                        "action":
                            result.get(
                                "action"
                            ),

                        "arguments":
                            result.get(
                                "arguments",
                                {}
                            )
                    }
                ]
            }

        # =====================================================
        # Tool calls
        # =====================================================

        if result.get(
            "type"
        ) == "tool_calls":

            calls = result.get(
                "calls",
                []
            )

            if not isinstance(
                calls,
                list
            ):

                return {
                    "type": "invalid",
                    "content":
                        "Calls must be a list."
                }

            cleaned = []

            for call in calls:

                if not isinstance(
                    call,
                    dict
                ):
                    continue

                tool = call.get(
                    "tool"
                )

                action = call.get(
                    "action"
                )

                if not tool or not action:
                    continue

                arguments = call.get(
                    "arguments",
                    {}
                )

                if not isinstance(
                    arguments,
                    dict
                ):
                    arguments = {}

                # Preserve paths exactly.
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

                cleaned.append({

                    "tool":
                        str(tool).strip(),

                    "action":
                        str(action).strip(),

                    "arguments":
                        arguments
                })

            if not cleaned:

                return {
                    "type": "invalid",
                    "content":
                        "No valid tool calls."
                }

            return {
                "type": "tool_calls",
                "calls": cleaned
            }

        # =====================================================
        # Chat
        # =====================================================

        if result.get(
            "type"
        ) == "chat":

            return {
                "type": "chat",
                "content":
                    str(
                        result.get(
                            "content",
                            ""
                        )
                    )
            }

        return {
            "type": "invalid",
            "content":
                json.dumps(
                    result,
                    ensure_ascii=False
                )
        }