import sys
import time
import webbrowser
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "chat_app.py"
URL = "http://127.0.0.1:5001/"

# لو شغال بالفعل، افتح الصفحة فقط
try:
    urllib.request.urlopen(URL, timeout=1)
    webbrowser.open(URL)
    raise SystemExit
except Exception:
    pass

# شغّل Flask
import subprocess

subprocess.Popen(
    [sys.executable, str(APP)],
    cwd=str(ROOT),
    creationflags=0x08000000,
    close_fds=True
)

# استنى لحد ما السيرفر يشتغل
for _ in range(40):
    time.sleep(0.5)

    try:
        urllib.request.urlopen(URL, timeout=1)
        webbrowser.open(URL)
        raise SystemExit
    except Exception:
        pass
