from flask import Flask, request, jsonify, render_template_string
from core.runner import AgentRunner

app = Flask(__name__)

runner = AgentRunner("workspace")

HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>KAREEM AGENT</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            background: #0b0d10;
            color: #f1f3f5;
            font-family: "Segoe UI", Tahoma, Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
        }

        .app {
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .header {
            height: 70px;
            border-bottom: 1px solid #252930;
            display: flex;
            align-items: center;
            padding: 0 24px;
            background: #101318;
        }

        .logo {
            width: 42px;
            height: 42px;
            border-radius: 12px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 18px;
            margin-left: 12px;
        }

        .title {
            font-size: 18px;
            font-weight: 700;
        }

        .status {
            font-size: 12px;
            color: #22c55e;
            margin-top: 3px;
        }

        .chat {
            flex: 1;
            overflow-y: auto;
            padding: 35px 20px 120px;
        }

        .messages {
            max-width: 900px;
            margin: auto;
        }

        .welcome {
            text-align: center;
            margin-top: 15vh;
        }

        .welcome h1 {
            font-size: 34px;
            margin-bottom: 10px;
        }

        .welcome p {
            color: #9ca3af;
            font-size: 16px;
        }

        .message {
            display: flex;
            margin: 18px 0;
        }

        .message.user {
            justify-content: flex-start;
        }

        .message.agent {
            justify-content: flex-end;
        }

        .bubble {
            max-width: 75%;
            padding: 14px 18px;
            border-radius: 18px;
            line-height: 1.7;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .user .bubble {
            background: #2563eb;
            border-bottom-left-radius: 5px;
        }

        .agent .bubble {
            background: #191d24;
            border: 1px solid #292e37;
            border-bottom-right-radius: 5px;
        }

        .bottom {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 18px 20px 22px;
            background: linear-gradient(
                transparent,
                #0b0d10 25%
            );
        }

        .input-area {
            max-width: 900px;
            margin: auto;
            display: flex;
            gap: 10px;
            background: #15181e;
            border: 1px solid #303640;
            border-radius: 18px;
            padding: 8px;
            box-shadow: 0 10px 35px rgba(0,0,0,.35);
        }

        textarea {
            flex: 1;
            resize: none;
            border: none;
            outline: none;
            background: transparent;
            color: white;
            font-size: 16px;
            padding: 12px;
            min-height: 46px;
            max-height: 140px;
            font-family: inherit;
        }

        textarea::placeholder {
            color: #737985;
        }

        button {
            width: 48px;
            height: 48px;
            border: none;
            border-radius: 14px;
            background: #6366f1;
            color: white;
            font-size: 20px;
            cursor: pointer;
        }

        button:hover {
            background: #7c3aed;
        }

        button:disabled {
            opacity: .5;
            cursor: not-allowed;
        }

        .typing {
            color: #9ca3af;
            font-size: 14px;
            padding: 10px;
            display: none;
        }

        @media (max-width: 700px) {
            .bubble {
                max-width: 90%;
            }

            .welcome h1 {
                font-size: 26px;
            }
        }
    </style>
</head>

<body>

<div class="app">

    <div class="header">
        <div class="logo">K</div>

        <div>
            <div class="title">KAREEM AGENT</div>
            <div class="status">● متصل</div>
        </div>
    </div>

    <div class="chat" id="chat">

        <div class="messages" id="messages">

            <div class="welcome" id="welcome">
                <h1>أهلًا يا كريم 👋</h1>
                <p>أنا KAREEM AGENT، جاهز أساعدك.</p>
            </div>

            <div class="typing" id="typing">
                KAREEM AGENT يفكر...
            </div>

        </div>

    </div>

    <div class="bottom">
        <div class="input-area">

            <textarea
                id="input"
                placeholder="اكتب رسالتك هنا..."
                rows="1"
            ></textarea>

            <button id="send">➤</button>

        </div>
    </div>

</div>

<script>

const input = document.getElementById("input");
const send = document.getElementById("send");
const messages = document.getElementById("messages");
const welcome = document.getElementById("welcome");
const typing = document.getElementById("typing");

function addMessage(text, type) {

    welcome.style.display = "none";

    const wrapper = document.createElement("div");
    wrapper.className = "message " + type;

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;

    wrapper.appendChild(bubble);

    messages.insertBefore(wrapper, typing);

    document.getElementById("chat").scrollTop =
        document.getElementById("chat").scrollHeight;
}

async function sendMessage() {

    const text = input.value.trim();

    if (!text) {
        return;
    }

    addMessage(text, "user");

    input.value = "";
    input.style.height = "auto";

    send.disabled = true;
    typing.style.display = "block";

    try {

        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: text
            })
        });

        const data = await response.json();

        typing.style.display = "none";

        if (data.success) {

            addMessage(
                data.response,
                "agent"
            );

        } else {

            addMessage(
                "حصل خطأ: " + data.error,
                "agent"
            );
        }

    } catch (error) {

        typing.style.display = "none";

        addMessage(
            "تعذر الاتصال بالـAgent.",
            "agent"
        );
    }

    send.disabled = false;
    input.focus();
}

send.addEventListener(
    "click",
    sendMessage
);

input.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            sendMessage();
        }
    }
);

input.addEventListener(
    "input",
    function() {

        this.style.height = "auto";

        this.style.height =
            Math.min(
                this.scrollHeight,
                140
            ) + "px";
    }
);

</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json()

    if not data or not data.get("message"):
        return jsonify({
            "success": False,
            "error": "Empty message."
        })

    try:

        result = runner.run(
            data["message"]
        )

        if isinstance(result, str):

            return jsonify({
                "success": True,
                "response": result
            })

        if isinstance(result, dict):

            if result.get("success") is False:

                return jsonify({
                    "success": False,
                    "error": result.get(
                        "error",
                        "Unknown agent error."
                    )
                })

            return jsonify({
                "success": True,
                "response": result.get(
                    "result",
                    result.get(
                        "response",
                        "تم تنفيذ الطلب."
                    )
                )
            })

        return jsonify({
            "success": False,
            "error": "Unexpected agent response."
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        })


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )