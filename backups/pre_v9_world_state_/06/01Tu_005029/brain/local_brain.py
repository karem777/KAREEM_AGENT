from ollama import chat


class LocalBrain:
    def __init__(self, model="qwen3:8b"):
        self.model = model

    def ask(self, message):
        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are KAREEM_AGENT's reasoning engine. "
                        "Return exactly one valid JSON object. "
                        "Use only the tools and actions supplied by the caller. "
                        "Never invent observations or source facts."
                    ),
                },
                {
                    "role": "user",
                    "content": str(message),
                },
            ],
            format="json",
            think=False,
            options={
                "temperature": 0,
                "num_ctx": 8192,
            },
            keep_alive="10m",
        )

        return str(
            response.message.content or ""
        ).strip()
