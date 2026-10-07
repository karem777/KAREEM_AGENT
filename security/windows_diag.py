from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

import psutil


class WindowsDiagnostics:
    name = "security"
    description = "Defensive Windows diagnostics and evidence collection."

    def snapshot(self) -> dict[str, Any]:
        boot = psutil.boot_time()
        return {
            "success": True,
            "os": platform.platform(),
            "hostname": platform.node(),
            "python": platform.python_version(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "boot_time": boot,
        }

    def processes(self, limit: int = 40):
        rows = []
        for p in psutil.process_iter(["pid", "name", "username", "memory_info"]):
            try:
                info = p.info
                rss = (info.get("memory_info").rss if info.get("memory_info") else 0) / (1024**2)
                rows.append({"pid": info.get("pid"), "name": info.get("name"), "user": info.get("username"), "rss_mb": round(rss, 1)})
            except Exception:
                continue
        rows.sort(key=lambda x: x.get("rss_mb", 0), reverse=True)
        return {"success": True, "processes": rows[: int(limit)]}

    def network(self):
        return {
            "success": True,
            "interfaces": {k: [a._asdict() for a in v] for k, v in psutil.net_if_addrs().items()},
            "connections": [{"laddr": str(c.laddr), "raddr": str(c.raddr), "status": c.status, "pid": c.pid} for c in psutil.net_connections(kind="inet")[:200]],
        }

    def services(self):
        if platform.system().lower() != "windows":
            return {"success": False, "error": "Windows-only action"}
        p = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Service | Select-Object -First 250 Name,Status,StartType | ConvertTo-Json"], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return {"success": False, "error": p.stderr[-4000:]}
        try:
            data = json.loads(p.stdout or "[]")
        except json.JSONDecodeError:
            data = p.stdout
        return {"success": True, "services": data}

    def event_logs(self, max_events: int = 50):
        if platform.system().lower() != "windows":
            return {"success": False, "error": "Windows-only action"}
        cmd = "Get-WinEvent -LogName System -MaxEvents {} | Select-Object TimeCreated,Id,LevelDisplayName,ProviderName,Message | ConvertTo-Json -Depth 4".format(int(max_events))
        p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=90)
        if p.returncode != 0:
            return {"success": False, "error": p.stderr[-4000:]}
        try:
            data = json.loads(p.stdout or "[]")
        except json.JSONDecodeError:
            data = p.stdout
        return {"success": True, "events": data}

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "snapshot": {"description": "Read-only system health snapshot.", "parameters": {}},
                "processes": {"description": "Read-only process inventory.", "parameters": {"limit": {"type": "integer", "required": False, "default": 40}}},
                "network": {"description": "Read-only network interface and connection diagnostics.", "parameters": {}},
                "services": {"description": "Read-only Windows service inventory.", "parameters": {}},
                "event_logs": {"description": "Read-only recent System event log evidence.", "parameters": {"max_events": {"type": "integer", "required": False, "default": 50}}},
            },
        }
