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


def _start_tunnel():
    try:
        from src.dashboard.tunnel import start_tunnel
        if start_tunnel(PORT):
            print("Cloudflare tunnel starting (URL file me ayega)...")
    except Exception as e:
        print("Tunnel skipped:", e)


def _start_telegram_polling():
    """Bot commands ('dashboard', /last, /status) suno — alag thread, apna loop."""
    try:
        import asyncio
        import os
        from src.paper.telegram_bot import run_bot_polling, TelegramConfig
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token:
            print("Telegram polling skipped (no token)")
            return
        asyncio.run(run_bot_polling(TelegramConfig(token, chat)))
    except Exception as e:
        print("Telegram polling skipped:", e)


threading.Thread(target=_start_tunnel, daemon=True).start()
threading.Thread(target=_start_telegram_polling, daemon=True).start()

print('Starting HTTP server...')
server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
server.serve_forever()