import os
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from core.background_tasks import BackgroundTaskQueue
from core.complete_runner import CompleteRunner
from core.report_writer import write_task_report

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("KAREEM_PORT", "5000"))

app = Flask(__name__)
runner = CompleteRunner(ROOT, max_steps=80)
background_tasks = BackgroundTaskQueue(
    lambda: CompleteRunner(ROOT, max_steps=80),
    max_workers=int(os.getenv("KAREEM_BACKGROUND_WORKERS", "2")),
)

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
.log{height:60vh;overflow:auto;background:#0b0f14;border-radius:10px;padding:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.row{display:flex;gap:10px;margin-top:12px;align-items:stretch}
textarea{flex:1;min-height:90px;background:#0d1117;color:#fff;border:1px solid #30363d;border-radius:10px;padding:12px}
button{background:#238636;color:white;border:0;border-radius:10px;padding:12px 20px;font-weight:700;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
select{background:#0d1117;color:#fff;border:1px solid #30363d;border-radius:10px;padding:10px}
.muted{color:#8b949e}
.mode{display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap}
</style>
</head>
<body>
<main>
<h1>KAREEM_AGENT COMPLETE</h1>
<p class="muted">Windows Operator · Background Tasks · Verified Results · Desktop TXT Reports</p>
<div class="box">
  <div id="log" class="log" role="log" aria-live="polite"></div>
  <div class="mode">
    <label for="mode">طريقة التحكم:</label>
    <select id="mode">
      <option value="visible">Visible — تحكم مرئي</option>
      <option value="background">Background — تحكم بالخلفية</option>
    </select>
    <button id="refresh" type="button" onclick="showTasks()">المهام الأخيرة</button>
  </div>
  <div class="row">
    <textarea id="q" placeholder="اكتب المهمة..."></textarea>
    <button id="submit" onclick="runTask()">تنفيذ</button>
  </div>
</div>
</main>
<script>
const log=document.getElementById('log');
const submitButton=document.getElementById('submit');
function add(x){
  log.textContent += (typeof x==='string' ? x : JSON.stringify(x,null,2)) + '\n\n';
  log.scrollTop=log.scrollHeight;
}
const sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
async function pollTask(taskId){
  add('تم إرسال المهمة للخلفية. المعرّف: '+taskId);
  while(true){
    await sleep(1500);
    let response, data;
    try{
      response=await fetch('/tasks/'+encodeURIComponent(taskId));
      data=await response.json();
    }catch(error){
      add('تعذر تحديث حالة المهمة مؤقتًا: '+error);
      continue;
    }
    if(!response.ok){add(data);return;}
    add('الحالة: '+data.status);
    if(['completed','failed','needs_approval'].includes(data.status)){
      add(data);
      if(data.report_path) add('تقرير TXT: '+data.report_path);
      else if(data.result && data.result.report_error) add('تعذر إنشاء التقرير: '+data.result.report_error);
      return;
    }
  }
}
async function runTask(){
  const q=document.getElementById('q').value.trim();
  if(!q)return;
  const mode=document.getElementById('mode').value;
  add('المهمة: '+q);
  add('وضع التنفيذ: '+mode);
  document.getElementById('q').value='';
  submitButton.disabled=true;
  try{
    const response=await fetch('/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:q,execution_mode:mode})
    });
    const data=await response.json();
    if(!response.ok && response.status!==202){add(data);return;}
    if(mode==='background' && data.task_id) await pollTask(data.task_id);
    else {
      add(data);
      if(data.report_path) add('تقرير TXT: '+data.report_path);
    }
  }catch(error){add('فشل الاتصال بالتطبيق: '+error);}
  finally{submitButton.disabled=false;}
}
async function showTasks(){
  try{
    const response=await fetch('/tasks');
    add(await response.json());
  }catch(error){add('تعذر جلب المهام: '+error);}
}
document.getElementById('q').addEventListener('keydown',event=>{
  if(event.key==='Enter' && !event.shiftKey){event.preventDefault();runTask();}
});
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
        return jsonify({"success": False, "error": "Empty message"}), 400

    if execution_mode == "background":
        return jsonify(background_tasks.submit(message)), 202

    started = time.time()
    try:
        result = runner.run(message, execution_mode="visible")
    except Exception as exc:
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        result["report_path"] = write_task_report(
            task_id=str(result.get("task_id") or int(started * 1000)),
            goal=message,
            result=result,
            started_at=started,
            finished_at=time.time(),
        )
    except Exception as exc:
        result["report_error"] = f"{type(exc).__name__}: {exc}"
    return jsonify(result)


@app.get("/tasks")
def list_tasks():
    return jsonify({"success": True, "tasks": background_tasks.list()})


@app.get("/tasks/<task_id>")
def get_task(task_id):
    task = background_tasks.get(task_id)
    if task is None:
        return jsonify({"success": False, "error": "Task not found"}), 404
    return jsonify(task)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
