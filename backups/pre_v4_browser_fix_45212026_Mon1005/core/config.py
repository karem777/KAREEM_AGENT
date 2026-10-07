from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "settings.json"

DEFAULT_CONFIG = {
    "agent_name": "Kareem Agent",
    "version": "0.1.0",
    "workspace": "workspace",
    "memory": "memory",
    "models": "models"
}


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, indent=4),
            encoding="utf-8-sig"
        )

    return json.loads(
        CONFIG_FILE.read_text(encoding="utf-8-sig")
    )

