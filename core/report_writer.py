from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|token|api[_ -]?key|secret|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+"),
]


def desktop_directory() -> Path:
    """Resolve the user's Windows Desktop, including OneDrive-backed Desktop."""
    home = Path.home()
    candidates = []
    profile = os.environ.get("USERPROFILE")
    if profile:
        candidates.append(Path(profile) / "Desktop")
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.append(Path(onedrive) / "Desktop")
    candidates.append(home / "Desktop")
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    target = candidates[0]
    target.mkdir(parents=True, exist_ok=True)
    return target


def _clean(value: Any, limit: int = 1200) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1=[REDACTED]" if "authorization" not in pattern.pattern.lower() else "Authorization: [REDACTED]", text)
    return text[:limit]


def write_task_report(
    task_id: str,
    goal: str,
    result: dict[str, Any],
    started_at: float | None = None,
    finished_at: float | None = None,
    desktop_dir: str | Path | None = None,
) -> str:
    """Write a concise, secret-conscious TXT report for a completed agent task."""
    started = datetime.fromtimestamp(started_at).astimezone().isoformat(timespec="seconds") if started_at else "غير متاح"
    finished = datetime.fromtimestamp(finished_at).astimezone().isoformat(timespec="seconds") if finished_at else datetime.now().astimezone().isoformat(timespec="seconds")
    success = bool(result.get("success"))
    status = "نجحت المهمة حسب نتيجة الوكيل" if success else ("تحتاج موافقة" if result.get("needs_approval") else "لم تكتمل")
    answer = _clean(result.get("answer") or result.get("reason") or result.get("error") or result.get("question") or "لا توجد خلاصة نصية.")
    lines = [
        "KAREEM_AGENT — تقرير تنفيذ المهمة",
        "=" * 48,
        f"معرّف المهمة: {task_id}",
        f"الحالة: {status}",
        f"بدأت: {started}",
        f"انتهت: {finished}",
        "",
        "المطلوب:",
        _clean(goal, 3000),
        "",
        "الخلاصة:",
        answer,
        "",
        f"عدد الخطوات المسجّل: {result.get('steps', 'غير متاح')}",
        f"المدة بالثواني: {result.get('elapsed_seconds', 'غير متاح')}",
        "",
        "الأدلة/الإجراءات المسجلة:",
    ]
    evidence = result.get("evidence")
    if isinstance(evidence, list) and evidence:
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                continue
            tool = _clean(item.get("tool", "?"), 100)
            action = _clean(item.get("action", "?"), 100)
            outcome = item.get("result")
            ok = not (isinstance(outcome, dict) and outcome.get("success") is False)
            lines.append(f"{index}. {tool}.{action} — {'نجاح حسب نتيجة الأداة' if ok else 'فشل حسب نتيجة الأداة'}")
            if isinstance(outcome, dict) and outcome.get("error"):
                lines.append(f"   الخطأ: {_clean(outcome.get('error'), 500)}")
    else:
        lines.append("لا توجد إجراءات تفصيلية مرفقة في نتيجة الوكيل.")
    missing = result.get("missing")
    if isinstance(missing, list) and missing:
        lines.extend(["", "ما زال يحتاج إلى معالجة:", *[f"- {_clean(x, 500)}" for x in missing[:20]]])
    if result.get("error"):
        lines.extend(["", "سبب عدم الإكمال:", _clean(result.get("error"), 1500)])
    lines.extend([
        "",
        "ملاحظة: التقرير يلخّص البيانات التي أعادها الوكيل؛ لا يُعدّ وحده إثباتًا مستقلًا على صحة جميع الإجراءات.",
        "",
    ])
    folder = Path(desktop_dir) if desktop_dir else desktop_directory()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(task_id))[:40] or "task"
    path = folder / f"KAREEM_AGENT_Report_{stamp}_{safe_id}.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
