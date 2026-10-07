import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path


class WindowsTool:
    name = "windows"
    description = "Native Windows diagnostics and controlled system interaction."

    DANGEROUS = re.compile(r"(format[- ]volume|remove-item|del\s+/?[a-z]:|rmdir\s+/s|stop-service|disable-service|set-mppreference|set-netfirewallprofile|reg\s+delete|shutdown\s|restart-computer|diskpart)", re.I)

    def _run_ps(self, script: str, timeout=25):
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True, timeout=timeout)
        return {"success": p.returncode == 0, "exit_code": p.returncode, "stdout": p.stdout[-16000:], "stderr": p.stderr[-8000:]}

    def get_system_info(self):
        usage = shutil.disk_usage(Path.cwd().anchor or os.getcwd())
        ram = None
        try:
            import psutil
            vm = psutil.virtual_memory()
            ram = {"total": vm.total, "available": vm.available, "percent": vm.percent}
        except Exception:
            pass
        return {"success": True, "os": platform.platform(), "version": platform.version(), "hostname": platform.node(), "python": platform.python_version(), "cpu": platform.processor(), "ram": ram, "system_drive": {"total": usage.total, "free": usage.free, "used": usage.used}}

    def processes(self, limit=30):
        try:
            import psutil
            rows = []
            for p in psutil.process_iter(["pid", "name", "username", "memory_info", "cpu_percent"]):
                try:
                    info = p.info
                    rows.append({"pid": info.get("pid"), "name": info.get("name"), "username": info.get("username"), "memory": getattr(info.get("memory_info"), "rss", None), "cpu": info.get("cpu_percent")})
                except Exception:
                    pass
            rows.sort(key=lambda x: (x.get("memory") or 0), reverse=True)
            return {"success": True, "processes": rows[:limit]}
        except Exception:
            return self._run_ps("Get-Process | Sort-Object WS -Descending | Select-Object -First %d Id,ProcessName,CPU,WS | ConvertTo-Json -Depth 2" % int(limit))

    def services(self, name=""):
        filter_expr = f"Where-Object {{$_.Name -like '*{name}*'}} | " if name else ""
        return self._run_ps(f"Get-Service | {filter_expr} Sort-Object Status,DisplayName | Select-Object -First 100 Name,DisplayName,Status | ConvertTo-Json -Depth 2")

    def network(self):
        return self._run_ps("$a=Get-NetAdapter -ErrorAction SilentlyContinue | Select-Object Name,Status,LinkSpeed,MacAddress; $i=Get-NetIPConfiguration -ErrorAction SilentlyContinue | Select-Object InterfaceAlias,IPv4Address,IPv6Address,DNSServer; [pscustomobject]@{adapters=$a;config=$i}|ConvertTo-Json -Depth 5")

    def ports(self):
        return self._run_ps("Get-NetTCPConnection -ErrorAction SilentlyContinue | Select-Object -First 150 LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | ConvertTo-Json -Depth 4")

    def storage(self):
        return self._run_ps("Get-Volume | Select-Object DriveLetter,FileSystemLabel,FileSystem,Size,SizeRemaining,HealthStatus | ConvertTo-Json -Depth 4")

    def environment(self, name=""):
        if name:
            return {"success": True, "name": name, "value": os.environ.get(name)}
        return {"success": True, "environment": dict(sorted(os.environ.items()))}

    def installed_apps(self, limit=200):
        script = r"@((Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue),(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue)) | Where-Object DisplayName | Select-Object DisplayName,DisplayVersion,Publisher,InstallLocation | Sort-Object DisplayName | Select-Object -First %d | ConvertTo-Json -Depth 4" % int(limit)
        return self._run_ps(script)

    def events(self, log_name="System", hours=24, limit=100):
        script = f"$s=(Get-Date).AddHours(-{float(hours)}); Get-WinEvent -FilterHashtable @{{LogName='{log_name}';StartTime=$s}} -MaxEvents {int(limit)} -ErrorAction SilentlyContinue | Select-Object TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Depth 4"
        return self._run_ps(script, timeout=40)

    def launch_app(self, app, args=None):
        argv = args or []
        try:
            p = subprocess.Popen([app, *map(str, argv)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "pid": p.pid, "app": app}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def close_process(self, name_or_pid, confirm=False):
        if not confirm:
            return {"success": False, "approval_required": True, "reason": "Closing a process changes system state. Set confirm=true."}
        try:
            import psutil
            target = int(name_or_pid) if str(name_or_pid).isdigit() else None
            killed = []
            for p in psutil.process_iter(["pid", "name"]):
                if (target is not None and p.info["pid"] == target) or (target is None and (p.info.get("name") or "").lower() == str(name_or_pid).lower()):
                    p.terminate(); killed.append(p.info["pid"])
            return {"success": True, "terminated": killed}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def powershell(self, command, confirm=False, timeout=45):
        if self.DANGEROUS.search(command) and not confirm:
            return {"success": False, "approval_required": True, "reason": "Potentially destructive PowerShell command. Set confirm=true only for an explicitly requested action.", "command": command}
        return self._run_ps(command, timeout=timeout)

    def write_text_file(self, path, content, confirm=False, backup=True):
        target = Path(path).expanduser().resolve()
        if not confirm:
            return {"success": False, "approval_required": True, "reason": "Writing outside the workspace changes the machine. Set confirm=true."}
        backup_path = None
        if target.exists() and backup:
            backup_path = target.with_suffix(target.suffix + f".bak.{int(time.time())}")
            backup_path.write_bytes(target.read_bytes())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(target), "backup": str(backup_path) if backup_path else None}

    def describe(self):
        return {"name": self.name, "description": self.description, "actions": {
            "get_system_info": {"description": "Read Windows/CPU/RAM/disk basics.", "parameters": {}},
            "processes": {"description": "List running processes.", "parameters": {"limit": {"type": "integer", "required": False}}},
            "services": {"description": "List Windows services.", "parameters": {"name": {"type": "string", "required": False}}},
            "network": {"description": "Inspect adapters, IP configuration and link state.", "parameters": {}},
            "ports": {"description": "Inspect active TCP connections.", "parameters": {}},
            "storage": {"description": "Inspect volumes and free space.", "parameters": {}},
            "environment": {"description": "Read environment variables.", "parameters": {"name": {"type": "string", "required": False}}},
            "installed_apps": {"description": "Read installed applications from Windows uninstall registries.", "parameters": {"limit": {"type": "integer", "required": False}}},
            "events": {"description": "Read recent Windows event logs.", "parameters": {"log_name": {"type": "string", "required": False}, "hours": {"type": "number", "required": False}, "limit": {"type": "integer", "required": False}}},
            "launch_app": {"description": "Launch an application.", "parameters": {"app": {"type": "string", "required": True}, "args": {"type": "array", "required": False}}},
            "close_process": {"description": "Terminate a process; requires confirm=true.", "parameters": {"name_or_pid": {"type": "string", "required": True}, "confirm": {"type": "boolean", "required": False}}},
            "powershell": {"description": "Run PowerShell; destructive patterns require confirm=true.", "parameters": {"command": {"type": "string", "required": True}, "confirm": {"type": "boolean", "required": False}, "timeout": {"type": "integer", "required": False}}},
            "write_text_file": {"description": "Write an absolute Windows path; requires confirm=true and can create a backup.", "parameters": {"path": {"type": "string", "required": True}, "content": {"type": "string", "required": True}, "confirm": {"type": "boolean", "required": False}, "backup": {"type": "boolean", "required": False}}},
        }}
