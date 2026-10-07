import os
import platform
import psutil
import socket
import subprocess
import re


class SystemTool:

    name = "system"

    description = (
        "Inspect the computer and execute Windows commands. "
        "Sensitive system-changing operations require user approval."
    )

    # =========================================================
    # CPU
    # =========================================================

    def cpu(self):

        return {
            "usage_percent":
                psutil.cpu_percent(interval=1),

            "cores":
                psutil.cpu_count(
                    logical=False
                ),

            "logical_processors":
                psutil.cpu_count(
                    logical=True
                ),

            "frequency_mhz":
                round(
                    psutil.cpu_freq().current,
                    2
                )
                if psutil.cpu_freq()
                else None
        }

    # =========================================================
    # MEMORY
    # =========================================================

    def memory(self):

        memory = psutil.virtual_memory()

        return {
            "total_gb":
                round(
                    memory.total / 1024**3,
                    2
                ),

            "used_gb":
                round(
                    memory.used / 1024**3,
                    2
                ),

            "available_gb":
                round(
                    memory.available / 1024**3,
                    2
                ),

            "usage_percent":
                memory.percent
        }

    # =========================================================
    # DISK
    # =========================================================

    def disk(self):

        disk = psutil.disk_usage(
            os.path.abspath(
                os.sep
            )
        )

        return {
            "total_gb":
                round(
                    disk.total / 1024**3,
                    2
                ),

            "used_gb":
                round(
                    disk.used / 1024**3,
                    2
                ),

            "free_gb":
                round(
                    disk.free / 1024**3,
                    2
                ),

            "usage_percent":
                disk.percent
        }

    # =========================================================
    # NETWORK
    # =========================================================

    def network(self):

        hostname = socket.gethostname()

        try:

            ip = socket.gethostbyname(
                hostname
            )

        except Exception:

            ip = None

        return {
            "hostname": hostname,
            "local_ip": ip
        }

    # =========================================================
    # OS
    # =========================================================

    def operating_system(self):

        return {
            "system":
                platform.system(),

            "release":
                platform.release(),

            "version":
                platform.version(),

            "machine":
                platform.machine(),

            "processor":
                platform.processor()
        }

    # =========================================================
    # PROCESSES
    # =========================================================

    def processes(self):

        result = []

        for process in psutil.process_iter(
            [
                "pid",
                "name",
                "memory_percent"
            ]
        ):

            try:

                info = process.info

                result.append({
                    "pid":
                        info.get("pid"),

                    "name":
                        info.get("name"),

                    "memory_percent":
                        round(
                            info.get(
                                "memory_percent",
                                0
                            ),
                            2
                        )
                })

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied
            ):
                continue

        result.sort(
            key=lambda x:
                x.get(
                    "memory_percent",
                    0
                ),
            reverse=True
        )

        return result[:30]

    # =========================================================
    # STATUS
    # =========================================================

    def status(self):

        return {
            "cpu":
                self.cpu(),

            "memory":
                self.memory(),

            "disk":
                self.disk(),

            "network":
                self.network(),

            "os":
                self.operating_system()
        }

    # =========================================================
    # DIAGNOSE
    # =========================================================

    def diagnose(self):

        return {
            "status":
                self.status(),

            "top_processes":
                self.processes()
        }

    # =========================================================
    # SENSITIVE COMMAND DETECTION
    # =========================================================

    def _is_sensitive_command(self, command):

        text = str(
            command
        ).strip().lower()

        sensitive_patterns = [

            # Registry
            r"\breg(\.exe)?\b",
            r"\bregedit\b",
            r"\bget-itemproperty\b.*\bhklm\b",
            r"\bset-itemproperty\b.*\bhklm\b",
            r"\bremove-itemproperty\b.*\bhklm\b",

            # Services
            r"\bsc(\.exe)?\b",
            r"\bsc\.exe\s+(create|delete|config|start|stop)\b",
            r"\bnew-service\b",
            r"\bremove-service\b",
            r"\bset-service\b",
            r"\bstop-service\b",
            r"\bstart-service\b",

            # Firewall
            r"\bnetsh\b.*firewall",
            r"\bnetsh\b.*advfirewall",
            r"\bnew-netfirewallrule\b",
            r"\bremove-netfirewallrule\b",
            r"\bset-netfirewallrule\b",

            # Drivers
            r"\bpnputil\b",
            r"\bdism\b.*driver",
            r"\bdevcon\b",

            # Boot / partitions
            r"\bbcdedit\b",
            r"\bdiskpart\b",
            r"\bformat(\.com|\.exe)?\b",
            r"\bmountvol\b",

            # Shutdown / restart
            r"\bshutdown(\.exe)?\b",
            r"\brestart-computer\b",
            r"\bstop-computer\b",

            # Power/system configuration
            r"\bpowercfg\b",
            r"\bset-computername\b",

            # Process termination
            r"\btaskkill(\.exe)?\b",
            r"\bstop-process\b"
        ]

        for pattern in sensitive_patterns:

            if re.search(
                pattern,
                text,
                re.IGNORECASE
            ):
                return True

        return False

    # =========================================================
    # RUN COMMAND
    # =========================================================

    def run_command(
        self,
        command,
        cwd=None,
        approved=False
    ):

        if not command:

            return {
                "success": False,
                "error":
                    "Command is empty."
            }

        command = str(
            command
        ).strip()

        sensitive = (
            self._is_sensitive_command(
                command
            )
        )

        if sensitive and not approved:

            return {
                "success": False,
                "requires_approval": True,
                "operation": command,
                "reason":
                    "This command can modify a sensitive Windows system component.",
                "message":
                    "User approval is required before executing this command."
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
                timeout=120
            )

            return {
                "success":
                    result.returncode == 0,

                "returncode":
                    result.returncode,

                "stdout":
                    result.stdout,

                "stderr":
                    result.stderr
            }

        except subprocess.TimeoutExpired:

            return {
                "success": False,
                "error":
                    "Command timed out after 120 seconds."
            }

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }

    # =========================================================
    # APPROVAL OBJECT
    # =========================================================

    def request_approval(
        self,
        operation,
        reason=""
    ):

        return {
            "success": False,
            "requires_approval": True,
            "operation": operation,
            "reason": reason,
            "message":
                "User approval is required."
        }

    # =========================================================
    # DESCRIBE
    # =========================================================

    def describe(self):

        return {

            "name": self.name,

            "description":
                self.description,

            "actions": {

                "cpu": {
                    "description":
                        "Get CPU information.",
                    "parameters": {}
                },

                "memory": {
                    "description":
                        "Get RAM information.",
                    "parameters": {}
                },

                "disk": {
                    "description":
                        "Get disk information.",
                    "parameters": {}
                },

                "network": {
                    "description":
                        "Get network information.",
                    "parameters": {}
                },

                "operating_system": {
                    "description":
                        "Get operating system information.",
                    "parameters": {}
                },

                "processes": {
                    "description":
                        "Get running processes.",
                    "parameters": {}
                },

                "status": {
                    "description":
                        "Get complete system status.",
                    "parameters": {}
                },

                "diagnose": {
                    "description":
                        "Diagnose the computer.",
                    "parameters": {}
                },

                "run_command": {
                    "description":
                        "Execute a Windows command. Sensitive commands require user approval.",
                    "parameters": {

                        "command": {
                            "type": "string",
                            "required": True
                        },

                        "cwd": {
                            "type": "string",
                            "required": False
                        }
                    }
                },

                "request_approval": {
                    "description":
                        "Request user approval for a sensitive operation.",
                    "parameters": {

                        "operation": {
                            "type": "string",
                            "required": True
                        },

                        "reason": {
                            "type": "string",
                            "required": False
                        }
                    }
                }
            }
        }