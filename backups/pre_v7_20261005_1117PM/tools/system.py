import os
import platform
import psutil
import socket
import subprocess
import re


class SystemTool:
    name = "system"
    description = "Inspect Windows and run commands. Sensitive system-changing commands require user approval."

    SENSITIVE_PATTERNS = [
        (r"\breg(\.exe)?\s+(add|delete|import|copy)", "Windows Registry modification"),
        (r"\bregedit(\.exe)?\b", "Windows Registry editor"),
        (r"\bsc(\.exe)?\s+(create|delete|config|start|stop)", "Windows service modification"),
        (r"\bnetsh(\.exe)?\b", "Firewall/network configuration"),
        (r"\bpowercfg(\.exe)?\b", "Power configuration"),
        (r"\bbcdedit(\.exe)?\b", "Boot configuration"),
        (r"\bdiskpart(\.exe)?\b", "Disk partitioning"),
        (r"\bformat(\.com|\.exe)?\s+[a-z]:", "Disk formatting"),
        (r"\bshutdown(\.exe)?\b", "Shutdown/restart"),
        (r"\brestart-computer\b", "Computer restart"),
        (r"\bstop-computer\b", "Computer shutdown"),
        (r"\bpnputil(\.exe)?\b", "Driver/package management"),
        (r"\bdevcon(\.exe)?\b", "Device/driver modification"),
        (r"\bSet-NetFirewallRule\b", "Firewall rule modification"),
        (r"\bNew-NetFirewallRule\b", "Firewall rule creation"),
        (r"\bRemove-NetFirewallRule\b", "Firewall rule deletion"),
    ]

    def cpu(self):
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "cores": psutil.cpu_count(logical=False),
            "logical_processors": psutil.cpu_count(logical=True),
        }

    def memory(self):
        m = psutil.virtual_memory()
        return {
            "total_gb": round(m.total / 1024**3, 2),
            "used_gb": round(m.used / 1024**3, 2),
            "available_gb": round(m.available / 1024**3, 2),
            "percent": m.percent,
        }

    def disk(self, path="."):
        d = psutil.disk_usage(path)
        return {
            "path": str(path),
            "total_gb": round(d.total / 1024**3, 2),
            "used_gb": round(d.used / 1024**3, 2),
            "free_gb": round(d.free / 1024**3, 2),
            "percent": d.percent,
        }

    def network(self):
        return {
            "hostname": socket.gethostname(),
            "interfaces": psutil.net_if_addrs(),
        }

    def operating_system(self):
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }

    def processes(self, limit=20):
        rows = []
        for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                rows.append(p.info)
            except Exception:
                pass
        rows.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
        return rows[:int(limit)]

    def status(self):
        return {
            "cpu": self.cpu(),
            "memory": self.memory(),
            "disk": self.disk("."),
            "os": self.operating_system(),
        }

    def diagnose(self):
        return self.status()

    def run_command(self, command, cwd=None):
        command = str(command or "").strip()
        if not command:
            return {"success": False, "error": "Command is empty."}

        lowered = command.lower()
        for pattern, reason in self.SENSITIVE_PATTERNS:
            if re.search(pattern, lowered, flags=re.I):
                return {
                    "success": False,
                    "requires_approval": True,
                    "operation": command,
                    "reason": reason,
                    "message": "This command changes sensitive Windows configuration and requires user approval.",
                }

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out after 120 seconds."}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def request_approval(self, operation, reason=""):
        return {
            "success": False,
            "requires_approval": True,
            "operation": operation,
            "reason": reason,
        }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "cpu": {"description": "Get CPU status.", "parameters": {}},
                "memory": {"description": "Get RAM status.", "parameters": {}},
                "disk": {"description": "Get disk status.", "parameters": {
                    "path": {"type": "string", "required": False}}},
                "network": {"description": "Get network information.", "parameters": {}},
                "operating_system": {"description": "Get OS information.", "parameters": {}},
                "processes": {"description": "List top processes by memory.", "parameters": {
                    "limit": {"type": "integer", "required": False}}},
                "status": {"description": "Get a system status snapshot.", "parameters": {}},
                "diagnose": {"description": "Diagnose basic system state.", "parameters": {}},
                "run_command": {"description": "Run a Windows command. Sensitive system-changing commands trigger approval.", "parameters": {
                    "command": {"type": "string", "required": True},
                    "cwd": {"type": "string", "required": False}}},
                "request_approval": {"description": "Create an explicit approval request.", "parameters": {
                    "operation": {"type": "string", "required": True},
                    "reason": {"type": "string", "required": False}}},
            },
        }
