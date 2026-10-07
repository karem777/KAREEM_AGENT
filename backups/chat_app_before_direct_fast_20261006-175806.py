import os
from pathlib import Path

from flask import Flask, jsonify, send_file, request

from core.complete_runner import CompleteRunner


ROOT = Path(__file__).resolve().parent
PORT = 5001

app = Flask(__name__)

runner = CompleteRunner(
    ROOT,
    max_steps=80
)


@app.get("/")
def index():

    return send_file(
        ROOT / "chat.html"
    )


@app.post("/chat")
def chat():

    data = request.get_json(
        silent=True
    ) or {}

    message = str(
        data.get("message", "")
    ).strip()

    if not message:

        return jsonify({
            "success": False,
            "error": "Empty message"
        }), 400

    try:

        result = runner.run(
            message
        )

        return jsonify(result)

    except Exception as exc:

        return jsonify({
            "success": False,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
        }), 500


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=False
    )
