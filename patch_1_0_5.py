from pathlib import Path
import re
import shutil
import py_compile

ROOT = Path.cwd()
TARGET = ROOT / "core" / "complete_runner.py"

if not TARGET.exists():
    raise SystemExit(f"NOT FOUND: {TARGET}")

text = TARGET.read_text(encoding="utf-8")
backup = TARGET.with_suffix(".py.bak_1.0.4")
shutil.copy2(TARGET, backup)

def replace_once(old, new, label):
    global text
    if old in text:
        text = text.replace(old, new, 1)
        print(f"[OK] {label}")
        return True
    if new in text:
        print(f"[SKIP] {label} already applied")
        return True
    print(f"[FAIL] {label}")
    return False

ok = True

ok &= replace_once(
'''        self.fast_mode = os.getenv("KAREEM_FAST_MODE", "1") == "1"
        self.verify_every_action = os.getenv("KAREEM_VERIFY_EVERY_ACTION", "0") == "1"
''',
'''        self.fast_mode = os.getenv("KAREEM_FAST_MODE", "1") == "1"
        self.verify_every_action = os.getenv("KAREEM_VERIFY_EVERY_ACTION", "0") == "1"
        self.max_history_context = int(os.getenv("KAREEM_HISTORY_CONTEXT", "10"))
        self.max_recovery_attempts = int(os.getenv("KAREEM_MAX_RECOVERY", "3"))
        self._run_started_at = None
''',
"runtime settings"
)

ok &= replace_once(
'''    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
''',
'''    def _reset_session(self):
        """Reset per-task world/guard state so tasks cannot leak state."""
        self.world = WorldModel()
        self.guard = LoopGuard()
        self._run_started_at = time.time()

    def _execute(self, tool_name: str, action: str, arguments: dict[str, Any]):
''',
"session reset"
)

ok &= replace_once(
'''    def _finish(self, task_id, user_message, step, answer, history, reason=""):
        self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "success", "steps": step, "lesson": reason or "Task completed with verified evidence.", "evidence": history[-3:]})
        return {"success": True, "answer": answer, "reason": reason, "steps": step, "task_id": task_id}
''',
'''    def _finish(self, task_id, user_message, step, answer, history, reason=""):
        elapsed = round(time.time() - self._run_started_at, 3) if self._run_started_at else None
        evidence = history[-3:]
        self.experience.append({
            "task_id": task_id,
            "goal": user_message,
            "outcome": "success",
            "steps": step,
            "elapsed_seconds": elapsed,
            "lesson": reason or "Task completed with verified evidence.",
            "evidence": evidence,
        })
        return {
            "success": True,
            "answer": answer,
            "reason": reason,
            "steps": step,
            "elapsed_seconds": elapsed,
            "task_id": task_id,
            "evidence": evidence,
        }
''',
"verified result payload"
)

ok &= replace_once(
'''    def run(self, user_message: str):
        task_id = str(int(time.time() * 1000))

        if self.fast_mode:
''',
'''    def run(self, user_message: str):
        task_id = str(int(time.time() * 1000))
        self._reset_session()

        if self.fast_mode:
''',
"clean task session"
)

ok &= replace_once(
'''            plan = self.planner.plan(contract, self.world.state.compact(), history[-8:], tools, recovery, experiences)
''',
'''            plan = self.planner.plan(
                contract,
                self.world.state.compact(),
                history[-self.max_history_context:],
                tools,
                recovery,
                experiences[:5],
            )
''',
"bounded planner context"
)

ok &= replace_once(
'''            if guard["blocked"]:
                recovery = {"type": "loop_detected", "guard": guard, "message": "Choose a materially different action or refresh the world."}
                if guard["count"] >= 4:
                    self.experience.append({"task_id": task_id, "goal": user_message, "outcome": "stuck", "steps": step, "lesson": "Repeated same action on same world state."})
                    return {"success": False, "error": "Agent detected a loop and stopped instead of repeating it indefinitely.", "task_id": task_id, "steps": step}
                continue
''',
'''            if guard["blocked"]:
                recovery = {
                    "type": "loop_detected",
                    "guard": guard,
                    "message": "Choose a materially different action or refresh the world.",
                    "recovery_policy": [
                        "reinspect_current_state",
                        "change_tool_or_action",
                        "replan_from_observed_state",
                    ],
                }
                if guard["count"] >= self.max_recovery_attempts:
                    self.experience.append({
                        "task_id": task_id,
                        "goal": user_message,
                        "outcome": "stuck",
                        "steps": step,
                        "lesson": "Repeated same action on same world state.",
                        "recovery_attempts": guard["count"],
                    })
                    return {
                        "success": False,
                        "error": "Agent detected a repeated-action loop and stopped safely.",
                        "task_id": task_id,
                        "steps": step,
                        "recovery": recovery,
                    }
                continue
''',
"loop recovery ladder"
)

ok &= replace_once(
'''            else:
                recovery = {"type": "tool_error", "error": result.get("error", "unknown"), "last_action": {"tool": tool, "action": action}, "message": "Analyze the exact error and choose a different recovery path."}
''',
'''            else:
                recovery = {
                    "type": "tool_error",
                    "error": result.get("error", "unknown"),
                    "last_action": {"tool": tool, "action": action},
                    "message": "Analyze the exact error and choose a different recovery path.",
                    "recovery_policy": {
                        "attempt": min(
                            self.max_recovery_attempts,
                            int(recovery.get("attempt", 0) or 0) + 1,
                        ),
                        "next": [
                            "inspect_or_read_more_evidence",
                            "try_an_alternative_action",
                            "switch_tool_when_capability_overlap_exists",
                            "ask_user_only_when_blocked_or_ambiguous",
                        ],
                    },
                }
''',
"tool-error recovery"
)

if not ok:
    print("\nPatch was not fully applied. Restoring backup...")
    shutil.copy2(backup, TARGET)
    raise SystemExit(1)

TARGET.write_text(text, encoding="utf-8")

try:
    py_compile.compile(str(TARGET), doraise=True)
except Exception:
    shutil.copy2(backup, TARGET)
    raise

REQ = ROOT / "requirements.txt"
if REQ.exists():
    req = REQ.read_text(encoding="utf-8", errors="ignore")
    additions = []
    if not re.search(r"(?im)^httpx(?:[<=>].*)?$", req):
        additions.append("httpx")
    if not re.search(r"(?im)^(beautifulsoup4|bs4)(?:[<=>].*)?$", req):
        additions.append("beautifulsoup4")
    if additions:
        REQ.write_text(req.rstrip() + "\n" + "\n".join(additions) + "\n", encoding="utf-8")
        print("[OK] requirements.txt updated:", ", ".join(additions))

print("\nKAREEM_AGENT 1.0.5 PATCH OK")
print("Backup:", backup)
print("Target:", TARGET)
