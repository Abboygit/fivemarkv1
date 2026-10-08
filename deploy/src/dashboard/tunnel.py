"""Cloudflare quick tunnel — dashboard ko public https URL (zero-config).

Purane five-ict-v2 setup me bhi quick tunnel tha. URL har restart par badalta
hai, isliye tunnel process URL ko URL_FILE me likhta hai; Telegram handler
har message par file se taaza URL padhta hai (stale env nahi).
"""
import re
import subprocess
import threading
import time
from pathlib import Path

URL_FILE = Path(__file__).resolve().parents[2] / "dashboard-url.txt"  # deploy/dashboard-url.txt
URL_RE = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")


def _drain_and_capture(proc: "subprocess.Popen") -> None:
    url = None
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            if url is None:
                m = URL_RE.search(line)
                if m:
                    url = m.group(0)
                    try:
                        URL_FILE.write_text(url)
                    except OSError:
                        pass
    except Exception:
        pass


def start_tunnel(port: int = 8091) -> bool:
    """cloudflared quick tunnel background me chalao. True = process chala (URL file me ayega)."""
    try:
        # Purana orphan tunnel ho to hatao (is VPS par sirf hamara tunnel hota hai)
        subprocess.run(["pkill", "-f", "cloudflared tunnel --url"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(1)
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        print("cloudflared nahi mila — public link skip (local dashboard chalta rahega)")
        return False
    threading.Thread(target=_drain_and_capture, args=(proc,), daemon=True).start()
    return True


def get_public_url() -> str:
    """Taaza tunnel URL (file se). Nahi mila to ''."""
    import os
    env = os.getenv("DASHBOARD_PUBLIC_URL", "").strip()
    if env:
        return env
    try:
        return URL_FILE.read_text().strip()
    except OSError:
        return ""
