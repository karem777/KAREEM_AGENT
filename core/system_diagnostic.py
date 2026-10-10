"""Deterministic, read-only Windows health checks for KAREEM_AGENT.

This path intentionally bypasses LLM planning for explicit PC-health requests so
that diagnostics cannot be downgraded to chat or spin through planner retries.
"""
from __future__ import annotations

import json
import time
from typing import Any


_DIAGNOSTIC_TERMS = (
    "حالة الجهاز", "فحص الجهاز", "افحص الجهاز", "تشخيص الجهاز",
    "تقييم الجهاز", "قيم الجهاز", "تقييم الكمبيوتر", "فحص الكمبيوتر",
    "حالة الكمبيوتر", "صحة الجهاز", "شوفلي حالة الجهاز",
    "system diagnostic", "diagnose my pc", "diagnose my computer",
    "pc health", "computer health", "health of my pc", "check my pc",
    "check my computer", "rate my pc", "assess my computer",
)


def is_system_diagnostic_request(message: str) -> bool:
    text = " ".join(str(message or "").casefold().split())
    return any(term in text for term in _DIAGNOSTIC_TERMS)


def _parse_json_output(result: Any) -> Any:
    if not isinstance(result, dict):
        return None
    stdout = result.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except (ValueError, TypeError):
        return None


def _to_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def run_system_diagnostic(registry, task_id: str, goal: str) -> dict:
    """Run bounded, read-only checks and return an evidence-based health score."""
    started = time.time()
    get_tool = getattr(registry, "get", None)
    windows = get_tool("windows") if callable(get_tool) else None
    if windows is None:
        return {
            "success": False,
            "mode": "task",
            "task_id": task_id,
            "error": "Windows diagnostics tool is not registered.",
            "score": None,
            "evidence": [],
        }

    evidence: list[dict[str, Any]] = []
    collected: dict[str, Any] = {}
    checks = [
        ("system", "get_system_info", {}),
        ("processes", "processes", {"limit": 20}),
        ("storage", "storage", {}),
        ("network", "network", {}),
        ("events", "events", {"log_name": "System", "hours": 24, "limit": 60}),
    ]

    for label, action, arguments in checks:
        started_check = time.time()
        try:
            method = getattr(windows, action)
            value = method(**arguments)
            if isinstance(value, dict) and value.get("success") is False:
                evidence.append({
                    "check": label,
                    "status": "failed",
                    "error": value.get("stderr") or value.get("error") or f"{action} returned failure",
                    "elapsed_seconds": round(time.time() - started_check, 2),
                })
                continue
            collected[label] = value
            evidence.append({
                "check": label,
                "status": "passed",
                "elapsed_seconds": round(time.time() - started_check, 2),
            })
        except Exception as exc:
            evidence.append({
                "check": label,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": round(time.time() - started_check, 2),
            })

    score = 100
    findings: list[dict[str, Any]] = []
    info = collected.get("system")
    if isinstance(info, dict):
        ram = info.get("ram")
        if isinstance(ram, dict) and isinstance(ram.get("percent"), (int, float)):
            usage = float(ram["percent"])
            if usage >= 95:
                score -= 18
                findings.append({"severity": "high", "finding": f"RAM usage is very high ({usage:.1f}%)."})
            elif usage >= 90:
                score -= 12
                findings.append({"severity": "medium", "finding": f"RAM usage is high ({usage:.1f}%)."})
            elif usage >= 80:
                score -= 6
                findings.append({"severity": "low", "finding": f"RAM usage is elevated ({usage:.1f}%)."})
            else:
                findings.append({"severity": "info", "finding": f"RAM usage observed at {usage:.1f}%."})
        else:
            findings.append({"severity": "unknown", "finding": "RAM utilization was not available; it was not scored."})

        drive = info.get("system_drive")
        if isinstance(drive, dict) and isinstance(drive.get("total"), (int, float)) and drive.get("total", 0) > 0:
            free_percent = float(drive.get("free", 0)) / float(drive["total"]) * 100
            if free_percent < 5:
                score -= 22
                findings.append({"severity": "high", "finding": f"System drive has only {free_percent:.1f}% free space."})
            elif free_percent < 10:
                score -= 14
                findings.append({"severity": "medium", "finding": f"System drive has {free_percent:.1f}% free space."})
            elif free_percent < 15:
                score -= 7
                findings.append({"severity": "low", "finding": f"System drive has {free_percent:.1f}% free space."})
            else:
                findings.append({"severity": "info", "finding": f"System drive has {free_percent:.1f}% free space."})
        else:
            findings.append({"severity": "unknown", "finding": "System drive capacity was not available; it was not scored."})
    else:
        findings.append({"severity": "unknown", "finding": "Basic system information was unavailable."})

    storage_data = _parse_json_output(collected.get("storage"))
    if storage_data is not None:
        volumes = _to_list(storage_data)
        for volume in volumes:
            if not isinstance(volume, dict):
                continue
            health = str(volume.get("HealthStatus") or "").casefold()
            if health in {"unhealthy", "warning"}:
                score -= 12 if health == "unhealthy" else 5
                findings.append({"severity": "high" if health == "unhealthy" else "medium",
                                 "finding": f"Volume {volume.get('DriveLetter') or volume.get('FileSystemLabel') or '(unnamed)'} reports health status: {health}."})
    else:
        findings.append({"severity": "unknown", "finding": "Volume health check did not return parseable data."})

    events_data = _parse_json_output(collected.get("events"))
    if events_data is not None:
        events = _to_list(events_data)
        critical = sum(1 for item in events if isinstance(item, dict) and str(item.get("LevelDisplayName", "")).casefold() == "critical")
        errors = sum(1 for item in events if isinstance(item, dict) and str(item.get("LevelDisplayName", "")).casefold() == "error")
        penalty = min(20, critical * 5) + min(10, errors * 2)
        score -= penalty
        if critical:
            findings.append({"severity": "high", "finding": f"{critical} critical System event(s) found in the last 24 hours."})
        if errors:
            findings.append({"severity": "medium", "finding": f"{errors} error-level System event(s) found in the last 24 hours."})
        if not critical and not errors:
            findings.append({"severity": "info", "finding": "No Critical/Error System events were returned for the last 24 hours."})
    else:
        findings.append({"severity": "unknown", "finding": "Recent System event logs could not be assessed from parseable data."})

    network_data = _parse_json_output(collected.get("network"))
    if isinstance(network_data, dict):
        adapters = _to_list(network_data.get("adapters"))
        if adapters and not any(isinstance(item, dict) and str(item.get("Status", "")).casefold() == "up" for item in adapters):
            score -= 5
            findings.append({"severity": "low", "finding": "No network adapter reported an Up status."})
        elif adapters:
            findings.append({"severity": "info", "finding": "At least one network adapter reports Up status."})
        else:
            findings.append({"severity": "unknown", "finding": "No adapter data was returned; network status is uncertain."})
    else:
        findings.append({"severity": "unknown", "finding": "Network adapter state could not be assessed from parseable data."})

    completed_checks = sum(1 for item in evidence if item["status"] == "passed")
    total_checks = len(checks)
    missing_checks = total_checks - completed_checks
    if missing_checks:
        # Missing telemetry is not treated as healthy; reduce confidence separately
        # from hardware-risk penalties and disclose it in the findings.
        score -= min(15, missing_checks * 3)
        findings.append({
            "severity": "unknown",
            "finding": f"{missing_checks} diagnostic check(s) failed; the score is less reliable.",
        })
    score = max(0, min(100, int(round(score))))
    summary = (
        f"تقييم صحة الجهاز المبدئي: {score}/100. "
        f"اكتمل {completed_checks} من {total_checks} فحوصات للقراءة فقط. "
        "الدرجة مبنية على مؤشرات الذاكرة والتخزين وسجلات النظام والشبكة المتاحة، "
        "وليست اختبار أداء معياريًا للمعالج أو كرت الشاشة."
    )
    return {
        "success": completed_checks > 0,
        "mode": "task",
        "task_id": task_id,
        "goal": goal,
        "answer": summary,
        "score": score if completed_checks else None,
        "checks_completed": completed_checks,
        "checks_total": total_checks,
        "elapsed_seconds": round(time.time() - started, 2),
        "findings": findings,
        "evidence": evidence,
        "observations": {
            "system": collected.get("system"),
            "processes": collected.get("processes"),
            "storage": collected.get("storage"),
            "network": collected.get("network"),
            "events": collected.get("events"),
        },
        "limitations": [
            "Read-only diagnostic; no settings or processes were changed.",
            "This score is a heuristic health indicator, not a hardware benchmark or a medical-grade fault diagnosis.",
            "Checks that failed or returned no data are marked unknown and must not be interpreted as healthy.",
        ],
    }
