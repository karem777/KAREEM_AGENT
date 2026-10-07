import json

from brain.local_brain import LocalBrain


class CompletionJudge:
    def __init__(self):
        self.brain = LocalBrain()

    def is_complete(
        self,
        user_goal,
        analysis,
        goal_state,
        history,
    ):
        # HARD RULE:
        # If deterministic goal state says anything required is pending,
        # the AI is not allowed to say "complete".
        if (
            goal_state is None
            or not goal_state.is_complete()
        ):
            return {
                "complete": False,
                "reason": (
                    "Required goal steps are still pending. "
                    "AI cannot override deterministic goal state."
                ),
            }

        prompt = (
            "You are the final verification layer for KAREEM_AGENT.\n"
            "The deterministic goal graph is already complete.\n\n"
            "USER GOAL:\n"
            + str(user_goal)
            + "\n\nGOAL:\n"
            + json.dumps(
                analysis or {},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n\nHISTORY:\n"
            + json.dumps(
                (history or [])[-12:],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + """

Return JSON only:
{"complete":true,"reason":"..."}
or
{"complete":false,"reason":"..."}
"""
        )

        try:
            value = json.loads(
                str(
                    self.brain.ask(prompt)
                ).strip()
            )
        except Exception:
            return {
                "complete": True,
                "reason": (
                    "Deterministic goal graph is complete; "
                    "AI verifier output was unavailable."
                ),
            }

        return {
            "complete": bool(
                value.get(
                    "complete",
                    True,
                )
            ),
            "reason": str(
                value.get(
                    "reason",
                    "",
                )
            ),
        }
