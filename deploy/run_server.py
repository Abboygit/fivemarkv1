import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # portable: Win+VPS
from src.dashboard.server import loop, Handler, PORT
from http.server import ThreadingHTTPServer
import threading

print('Starting loop thread...')
t = threading.Thread(target=loop, daemon=True)
t.start()

try:  # startup ping — Telegram env ho to "Bot started" jaisa proof turant mile
    from src.paper.telegram_bot import notify_text_sync
    notify_text_sync("🤖 Five Mark V1 started — paper forward live (BTCUSDT 5m/1h)")
except Exception as e:
    print("Telegram startup ping skipped:", e)

print('Starting HTTP server...')
server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
server.serve_forever()