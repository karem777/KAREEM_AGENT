import json
import re
from brain.local_brain import LocalBrain


class EvidenceSummarizer:
    """
    Strict extractive evidence builder.

    The model is only allowed to SELECT exact source excerpts and provide
    a short label for each excerpt. The final file content is constructed
    deterministically from the exact excerpts, so the model cannot invent
    factual wording inside the saved file.
    """

    def __init__(self):
        self.brain = LocalBrain()

    @staticmethod
    def normalize_url(value):
        text = str(value or "").strip()

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

    @staticmethod
    def normalize_text(value):
        return re.sub(
            r"\s+",
            " ",
            str(value or ""),
        ).strip()

    def summarize(
        self,
        user_request,
        evidence,
    ):
        compact = []

        for item in evidence:
            text = self.normalize_text(
                item.get("text", "")
            )

            if not text:
                continue

            compact.append(
                {
                    "id": len(compact),
                    "url": self.normalize_url(
                        item.get("url", "")
                    ),
                    "text": text[:12000],
                }
            )

        if not compact:
            return {
                "success": False,
                "error": "No usable evidence.",
                "content": "",
            }

        prompt = """
You are an extractive evidence selector.

USER REQUEST:
""" + str(user_request) + """

SOURCE EVIDENCE:
""" + json.dumps(
            compact,
            ensure_ascii=False,
            indent=2,
        ) + """

RULES:
- Do NOT summarize in your own words.
- Do NOT add facts.
- Do NOT paraphrase.
- Select up to 5 short, useful excerpts copied EXACTLY from the source text.
- Every excerpt MUST be an exact contiguous substring of one source text.
- Return the source id and the exact excerpt only.
- Prefer excerpts directly relevant to the user's requested subject.
- If the source does not support a useful statement, return no excerpt for that source.

Return JSON only:
{"excerpts":[{"source_id":0,"excerpt":"exact text copied from source"}]}
"""

        raw = self.brain.ask(
            prompt
        )

        try:
            data = json.loads(
                str(raw).strip()
            )
        except Exception:
            return {
                "success": False,
                "error": "Evidence selector returned invalid JSON.",
                "content": "",
            }

        excerpts = data.get(
            "excerpts",
            [],
        )

        if not isinstance(
            excerpts,
            list,
        ):
            return {
                "success": False,
                "error": "Invalid excerpts list.",
                "content": "",
            }

        verified = []

        for item in excerpts:
            if not isinstance(
                item,
                dict,
            ):
                continue

            try:
                source_id = int(
                    item.get(
                        "source_id"
                    )
                )
            except Exception:
                continue

            if (
                source_id < 0
                or source_id >= len(compact)
            ):
                continue

            excerpt = self.normalize_text(
                item.get(
                    "excerpt",
                    "",
                )
            )

            if not excerpt:
                continue

            source_text = compact[
                source_id
            ]["text"]

            if excerpt not in source_text:
                continue

            verified.append(
                {
                    "url": compact[
                        source_id
                    ]["url"],
                    "excerpt": excerpt,
                }
            )

        if not verified:
            return {
                "success": False,
                "error": (
                    "No exact source excerpts passed verification."
                ),
                "content": "",
            }

        # Deduplicate while preserving order.
        unique = []
        seen = set()

        for item in verified:
            key = (
                item["url"],
                item["excerpt"],
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        lines = [
            "ملخص موثق من المصادر المسترجعة:",
            "",
        ]

        for item in unique:
            lines.append(
                f"- {item['excerpt']}"
            )
            lines.append(
                f"  المصدر: {item['url']}"
            )
            lines.append("")

        return {
            "success": True,
            "content": "\n".join(
                lines
            ).strip(),
            "excerpts": unique,
        }
