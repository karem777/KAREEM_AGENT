"""Safe, deterministic RAM review for Windows.

This module is intentionally observational: it reports memory usage and ranks
processes, but never terminates processes or clears caches automatically.
"""
from __future__ import annotations

import json
import time
from typing import Any


_RAM_TERMS = (
    "نظف الرام", "تنظيف الرام", "تنضيف الرام", "حرر الرام", "تفريغ الرام",
    "قلل استهلاك الرام", "استهلاك الرام", "استهلاك الذاكرة", "حل مشكلة الرام",
    "ram cleanup", "clean ram", "free up ram", "free ram", "optimize ram",
    "reduce memory usage", "memory cleanup", "high ram usage",
)


def is_ram_optimization_request(message: str) -> bool:
    text = " ".join(str(message or "").casefold().split())
    return any(term in text for term in _RAM_TERMS)


def _json_stdout(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    stdout = value.get("stdout")
    if isinstance(stdout, str) and stdout.strip():
        try:
            return json.loads(stdout)
        except (ValueError, TypeError):
            return None
    return value


def _process_rows(value: Any) -> list[dict[str, Any]]:
    data = _json_stdout(value)
    rows = []
    if isinstance(data, dict):
        rows = data.get("processes")
        if rows is None and ("ProcessName" in data or "name" in data):
            rows = [data]
        elif rows is None and ("Id" in data or "pid" in data):
            rows = [data]
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    normalized = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("ProcessName") or row.get("process_name") or "unknown"
        pid = row.get("pid", row.get("Id"))
        memory = row.get("memory", row.get("WS", row.get("WorkingSet64", 0)))
        try:
            memory = max(0, int(memory or 0))
        except (ValueError, TypeError):
            memory = 0
        try:
            pid = int(pid) if pid is not None else None
        except (ValueError, TypeError):
            pid = None
        normalized.append({
            "pid": pid,
            "name": str(name),
            "memory_bytes": memory,
            "memory_mib": round(memory / (1024 ** 2), 1),
            "cpu_percent": row.get("cpu", row.get("CPU")),
        })
    normalized.sort(key=lambda row: row["memory_bytes"], reverse=True)
    return normalized


def run_ram_review(registry, task_id: str, goal: str) -> dict:
    """Measure RAM and report top consumers without changing the machine."""
    started = time.time()
    get_tool = getattr(registry, "get", None)
    windows = get_tool("windows") if callable(get_tool) else None
    if windows is None:
        return {
            "success": False, "mode": "task", "task_id": task_id,
            "error": "Windows diagnostics tool is not registered.",
            "evidence": [],
        }

    evidence = []
    info = None
    processes = []
    try:
        info = windows.get_system_info()
        evidence.append({"check": "ram_snapshot", "status": "passed"})
    except Exception as exc:
        evidence.append({"check": "ram_snapshot", "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    try:
        process_result = windows.processes(limit=50)
        processes = _process_rows(process_result)
        if isinstance(process_result, dict) and process_result.get("success") is False:
            evidence.append({"check": "top_processes", "status": "failed", "error": process_result.get("stderr") or process_result.get("error") or "Process query failed"})
        elif processes:
            evidence.append({"check": "top_processes", "status": "passed"})
        else:
            evidence.append({"check": "top_processes", "status": "unknown", "error": "Process data was empty or could not be parsed"})
    except Exception as exc:
        evidence.append({"check": "top_processes", "status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    ram = info.get("ram") if isinstance(info, dict) else None
    total = ram.get("total") if isinstance(ram, dict) else None
    available = ram.get("available") if isinstance(ram, dict) else None
    percent = ram.get("percent") if isinstance(ram, dict) else None
    findings = []
    if isinstance(percent, (int, float)):
        findings.append({
            "severity": "high" if percent >= 95 else "medium" if percent >= 85 else "info",
            "finding": f"RAM usage is {float(percent):.1f}%.",
        })
    else:
        findings.append({"severity": "unknown", "finding": "Windows did not return a usable RAM utilization percentage."})

    top_processes = processes[:8]
    if top_processes:
        formatted = [
            f"{p['name']} (PID {p['pid'] if p['pid'] is not None else '?'}, {p['memory_mib']:.1f} MiB)"
            for p in top_processes
        ]
        findings.append({
            "severity": "info",
            "finding": "Largest observed processes: " + "; ".join(formatted),
        })
    else:
        findings.append({"severity": "unknown", "finding": "Top process memory usage could not be parsed."})

    if isinstance(percent, (int, float)) and percent >= 85 and top_processes:
        findings.append({
            "severity": "recommendation",
            "finding": "Review the listed user applications and save your work before closing any of them. No process was closed by this review.",
        })
    if isinstance(total, (int, float)) and isinstance(available, (int, float)) and total > 0:
        ram_line = f"المتاح حاليًا {available / (1024 ** 3):.2f} من {total / (1024 ** 3):.2f} جيجابايت."
    else:
        ram_line = "تعذّر حساب الذاكرة المتاحة بدقة."
    status = sum(1 for item in evidence if item.get("status") == "passed")
    usage_line = f"استخدام الرام {float(percent):.1f}%." if isinstance(percent, (int, float)) else "نسبة الاستخدام غير متاحة."
    return {
        "success": status > 0,
        "mode": "task",
        "task_id": task_id,
        "goal": goal,
        "answer": (
            f"فحص الرام اكتمل دون إجراء تغييرات. {usage_line} {ram_line} "
            "عرضت أكثر العمليات استهلاكًا للذاكرة؛ لم أغلق أي برنامج ولم أمسح ذاكرة التخزين المؤقت."
        ),
        "checks_completed": status,
        "checks_total": 2,
        "elapsed_seconds": round(time.time() - started, 2),
        "findings": findings,
        "evidence": evidence,
        "observations": {
            "ram": {"total": total, "available": available, "percent": percent},
            "top_processes": top_processes,
        },
        "limitations": [
            "Read-only review: no processes were terminated and no settings were changed.",
            "Process memory values are a point-in-time snapshot and may change immediately.",
            "Closing an application can lose unsaved work; a separate explicit approval workflow is required before any process termination.",
        ],
    }
