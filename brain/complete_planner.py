import json
from typing import Any

from brain.complete_brain import CompleteBrain


class CompletePlanner:
    """
    Model-driven autonomous planner.

    No Notepad/Paint/WhatsApp workflows live here.
    The model chooses the next action from the live tool schema and
    current world state.
    """

    def __init__(self, brain=None):
        self.brain = brain or CompleteBrain()

    @staticmethod
    def _native_tools():
        return [
            {
                "type": "function",
                "function": {
                    "name": "agent_action",
                    "description": (
                        "Execute exactly one action using a live agent tool. "
                        "The selected tool and action MUST exist in the "
                        "LIVE TOOL SCHEMA supplied in the prompt."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool": {
                                "type": "string",
                                "description": (
                                    "Canonical tool name from LIVE TOOL SCHEMA."
                                ),
                            },
                            "action": {
                                "type": "string",
                                "description": (
                                    "Action name exposed by the selected tool."
                                ),
                            },
                            "arguments": {
                                "type": "object",
                                "description": (
                                    "Arguments for the selected action."
                                ),
                                "additionalProperties": True,
                            },
                        },
                        "required": [
                            "tool",
                            "action",
                            "arguments",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "finish_task",
                    "description": (
                        "Finish the task only when current evidence proves "
                        "the user's goal is complete."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                            },
                            "evidence": {
                                "type": "array",
                            },
                        },
                        "required": [
                            "answer",
                            "evidence",
                        ],
                    },
                },
            },

        ]

    def _build_prompt(
        self,
        goal,
        world,
        history,
        tools,
        recovery,
        experiences,
    ):
        return f"""
You are KAREEM_AGENT's autonomous execution brain.

You are NOT an automation script.
You are NOT a fixed workflow executor.
You are NOT allowed to assume an application-specific sequence.

Your job is to achieve the USER GOAL on a real machine.

Your operating loop is:

1. Read CURRENT STATE.
2. Decide the NEXT useful action.
3. Execute exactly one action.
4. Read its result.
5. Update your understanding.
6. Decide again.
7. Repeat until the goal is actually verified.

IMPORTANT:

- Never create a hidden workflow in your head such as:
  "Notepad means open -> type -> save".
- The application name does NOT define the action sequence.
- Inspect the current machine state and decide dynamically.
- Never invent target IDs.
- Never invent control IDs.
- Never invent coordinates when an inspection action can provide them.
- Never assume a dialog is present without observing it.
- After UI changes, reason from the newest observation.
- If an action fails, analyze the exact result and recover.
- Do not blindly repeat a failed action.
- Do not claim success from intention.
- Completion requires evidence.
- Respect approval_required responses.

WINDOWS:

For native Windows interaction, prefer the canonical "computer" tool.

The computer tool exposes a real UI/operator layer.
Its state is part of the world you are reasoning about.

For native applications:

- inspect before interacting when the target is unknown
- use the currently observed target_id/control_id
- use semantic/control-level operations when available
- use mouse/keyboard fallback only when appropriate
- inspect dialogs before typing into them
- verify the result before calling the task complete

GENERAL:

- You can use ANY available tool.
- One meaningful action per reasoning cycle.
- Preserve every user constraint.
- Do not replace the user's goal with a guessed workflow.
- Do not invent facts that are not in the current state.
- Never finish because an action returned success=True alone.
- Treat an actionable user request as sufficient input. Do NOT ask the user to restate or clarify a clear task.
- Use reasonable defaults when the request contains an obvious choice such as "first result".
- Ask the user ONLY when a required fact is genuinely impossible to infer or obtain through available tools.

REFERENCE ARCHITECTURE PRINCIPLES:
- ReAct: reason from the latest observation, take one action, observe the result, then reason again.
- Computer-use grounding: inspect the real UI/state before interacting with unknown targets; never invent selectors or coordinates.
- Experience learning: successful and failed trajectories should produce reusable lessons, not just logs.
- Recovery: failures are observations; diagnose them and choose a different next action instead of blindly retrying.
- Context discipline: keep the working context focused on the current goal, latest state, relevant history, and relevant tools.
- Verification: completion requires evidence from the environment, not the model's intention.
- Skills: reusable methods can be recalled when they match the current task, but must remain subordinate to current observations.

USER REQUEST (verbatim):
{json.dumps(goal.get("goal", ""), ensure_ascii=False)}

USER GOAL OBJECT:
{json.dumps(goal, ensure_ascii=False)}

CURRENT WORLD:
{json.dumps(world, ensure_ascii=False)}

RECENT HISTORY:
{json.dumps(history[-8:], ensure_ascii=False)}

RECOVERY:
{json.dumps(recovery or {}, ensure_ascii=False)}

RECALLED EXPERIENCES:
{json.dumps(experiences or [], ensure_ascii=False)}

LIVE TOOL SCHEMA:
{json.dumps(tools, ensure_ascii=False)}

Choose the next action from the LIVE TOOL SCHEMA.
""".strip()

    def plan(
        self,
        goal: dict[str, Any],
        world: dict[str, Any],
        history: list[dict[str, Any]],
        tools: dict[str, Any],
        recovery=None,
        experiences=None,
    ):
        # Keep the planner call single-pass and compact. The model chooses
        # behavior; the registry remains the source of executable capabilities.
        prompt = f"""
You are the decision brain of KAREEM_AGENT.

Choose exactly ONE next step toward the user's goal.
You are autonomous: never ask the user to clarify an actionable request.
Use ONLY tools/actions that exist in LIVE TOOLS.
Do not invent IDs, coordinates, controls, URLs, or unseen state.
Use the latest WORLD observation and recover from failures.
Do not finish until the goal is verified by evidence.

Return JSON only:
{{"type":"tool_call","tool":"...","action":"...","arguments":{{}}}}
or
{{"type":"finish","answer":"...","evidence":[]}}

USER GOAL:
{json.dumps(goal.get("goal", ""), ensure_ascii=False)}

WORLD:
{json.dumps(world, ensure_ascii=False)}

RECENT HISTORY:
{json.dumps(history[-4:], ensure_ascii=False)}

RECOVERY:
{json.dumps(recovery or {}, ensure_ascii=False)}

RELEVANT EXPERIENCES:
{json.dumps(experiences or [], ensure_ascii=False)}

LIVE TOOLS:
{json.dumps(tools, ensure_ascii=False)}
""".strip()

        try:
            value = self.brain.json(prompt, fallback=None)
            if not isinstance(value, dict):
                return {
                    "type": "invalid_plan",
                    "reason": "Planner returned a non-object decision.",
                }

            if value.get("type") == "ask_user":
                return {
                    "type": "invalid_plan",
                    "reason": "Planner attempted clarification instead of using available tools.",
                }

            return value
        except Exception as exc:
            return {
                "type": "invalid_plan",
                "reason": f"Planner decision failed: {exc}",
            }
