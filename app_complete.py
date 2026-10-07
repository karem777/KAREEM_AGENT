import os
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

from core.complete_runner import CompleteRunner

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("KAREEM_PORT", "5000"))

app = Flask(__name__)
runner = CompleteRunner(ROOT, max_steps=80)

PAGE = r'''<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KAREEM_AGENT COMPLETE</title>
<style>
body{margin:0;background:#0d1117;color:#e6edf3;font-family:Segoe UI,Tahoma,sans-serif}
main{max-width:1000px;margin:30px auto;padding:20px}
.box{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:18px}
.log{height:60vh;overflow:auto;background:#0b0f14;border-radius:10px;padding:14px;white-space:pre-wrap}
.row{display:flex;gap:10px;margin-top:12px;align-items:stretch}
textarea{flex:1;min-height:90px;background:#0d1117;color:#fff;border:1px solid #30363d;border-radius:10px;padding:12px}
button{background:#238636;color:white;border:0;border-radius:10px;padding:12px 20px;font-weight:700;cursor:pointer}
select{background:#0d1117;color:#fff;border:1px solid #30363d;border-radius:10px;padding:10px}
.muted{color:#8b949e}
.mode{display:flex;gap:8px;align-items:center;margin-top:10px}
</style>
</head>

<body>
<main>
<h1>KAREEM_AGENT COMPLETE</h1>
<p class="muted">Local Computer Operator • Cognitive World-State • Universal Web • Windows Native</p>

<div class="box">
<div id="log" class="log"></div>

<div class="mode">
<label for="mode">طريقة التحكم:</label>
<select id="mode">
<option value="visible">Visible — تحكم مرئي</option>
<option value="background">Background — تحكم بالخلفية</option>
</select>
</div>

<div class="row">
<textarea id="q" placeholder="اكتب المهمة..."></textarea>
<button onclick="run()">تنفيذ</button>
</div>
</div>
</main>

<script>
const log=document.getElementById('log');

function add(x){
  log.textContent += (typeof x==='string' ? x : JSON.stringify(x,null,2)) + '\n\n';
  log.scrollTop=log.scrollHeight;
}

async function run(){
  const q=document.getElementById('q').value.trim();
  if(!q)return;

  const mode=document.getElementById('mode').value;

  add('USER: '+q);
  add('MODE: '+mode);
  document.getElementById('q').value='';

  const r=await fetch('/chat',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      message:q,
      execution_mode:mode
    })
  });

  const j=await r.json();
  add(j);
}
</script>
</body>
</html>'''

@app.get("/")
def index():
    return render_template_string(PAGE)

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()
    execution_mode = str(data.get("execution_mode", "visible")).strip().lower()

    if execution_mode not in {"visible", "background"}:
        execution_mode = "visible"

    if not message:
        return jsonify({
            "success": False,
            "error": "Empty message"
        }), 400

    return jsonify(
        runner.run(
            message,
            execution_mode=execution_mode,
        )
    )

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=False,
    )
