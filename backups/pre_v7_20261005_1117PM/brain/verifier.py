import json
from brain.local_brain import LocalBrain


class EvidenceVerifier:
    """
    AI-based provenance guard.
    It does not execute tools.
    It only checks whether proposed file content is supported by
    the source observations collected during this task.
    """

    def __init__(self):
        self.brain = LocalBrain()

    def verify(
        self,
        user_request,
        proposed_content,
        evidence,
    ):
        prompt = f"""
You are a strict factual verifier.

USER REQUEST:
{user_request}

PROPOSED FILE CONTENT:
{proposed_content}

SOURCE OBSERVATIONS:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

Question:
Is every factual claim in PROPOSED FILE CONTENT supported by the SOURCE OBSERVATIONS?

Rules:
- Do not use your own background knowledge.
- A URL/title alone is not evidence.
- If a claim is not supported, answer false.
- Return JSON only.

Return exactly:
{{"supported":true,"reason":"..."}}
or:
{{"supported":false,"reason":"..."}}
"""

        raw = self.brain.ask(prompt)

        try:
            result = json.loads(
                str(raw).strip()
            )
        except Exception:
            return {
                "supported": False,
                "reason": "Verifier did not return valid JSON.",
            }

        return {
            "supported": bool(
                result.get(
                    "supported",
                    False,
                )
            ),
            "reason": str(
                result.get(
                    "reason",
                    "",
                )
            ),
        }
