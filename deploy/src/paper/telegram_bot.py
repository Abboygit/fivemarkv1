"""Telegram bot for paper engine notifications — trade entry, exit, P&L."""
import os
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market.binance import Candle

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = object

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telegram_bot")


@dataclass
class TelegramConfig:
    token: str
    chat_id: str
    enabled: bool = True


class TelegramNotifier:
    """Async Telegram notifier for trade events."""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.bot: Optional[Bot] = None
        self._last_trade_info: Optional[dict] = None

    async def start(self):
        if not self.config.enabled or not TELEGRAM_AVAILABLE:
            log.info("Telegram disabled or python-telegram-bot not installed")
            return
        if not self.config.token or not self.config.chat_id:
            log.warning("Telegram token/chat_id not set — notifications disabled")
            self.config.enabled = False
            return
        self.bot = Bot(token=self.config.token)
        try:
            me = await self.bot.get_me()
            log.info(f"Telegram bot connected: @{me.username}")
            await self.send("🤖 Five Mark V1 — Bot started\n✅ Notifications enabled")
        except TelegramError as e:
            log.error(f"Telegram connect failed: {e}")
            self.config.enabled = False

    async def send(self, text: str):
        if not self.config.enabled:
            return
        if self.bot is None:  # lazy init — start() ka intezar nahi (journal hooks seedha send karte hain)
            if not TELEGRAM_AVAILABLE or not self.config.token:
                return
            self.bot = Bot(token=self.config.token)
        try:
            await self.bot.send_message(
                chat_id=self.config.chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except TelegramError as e:
            log.error(f"Telegram send failed: {e}")

    def fmt_money(self, x: float) -> str:
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.2f}"

    def fmt_r(self, x: float) -> str:
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.2f}R"

    async def notify_entry(self, trade_id: str, symbol: str, tf: str, side: str,
                           entry: float, stop: float, target: float, qty: float,
                           risk_cash: float, rr: float, setup: str):
        """Called when trade opens."""
        if not self.config.enabled:
            return
        emoji = "🟢" if side == "long" else "🔴"
        txt = (
            f"{emoji} <b>ENTRY</b> {symbol} {tf}\n"
            f"Side: {side.upper()}\n"
            f"Entry: {entry:.4f}\n"
            f"Stop: {stop:.4f}\n"
            f"Target: {target:.4f}\n"
            f"Risk: ${risk_cash:.2f} | Qty: {qty:.6f}\n"
            f"R:R: {rr:.2f}\n"
            f"Setup: {setup}\n"
            f"ID: {trade_id}"
        )
        await self.send(txt)

    async def notify_exit(self, trade_id: str, symbol: str, tf: str, side: str,
                          entry: float, exit_price: float, pnl: float,
                          r_multiple: float, exit_reason: str, bars_held: int,
                          mfe_r: float = 0.0, mae_r: float = 0.0,
                          partial_r: float = 0.0):
        """Called when trade closes — shows P&L + last trade summary."""
        if not self.config.enabled:
            return

        win = pnl > 0
        emoji = "✅" if win else "❌"
        reason_emoji = {
            "target": "🎯",
            "stop": "🛑",
            "trailing": "📈",
            "time": "⏰",
        }.get(exit_reason, "📤")

        txt = (
            f"{emoji} <b>EXIT</b> {symbol} {tf}\n"
            f"Side: {side.upper()}\n"
            f"Entry: {entry:.4f} → Exit: {exit_price:.4f}\n"
            f"P&L: ${self.fmt_money(pnl)} ({self.fmt_r(r_multiple)})\n"
            f"Reason: {reason_emoji} {exit_reason}\n"
            f"Bars held: {bars_held}\n"
            f"MFE: {mfe_r:.2f}R | MAE: {mae_r:.2f}R"
        )
        if partial_r:
            txt += f"\nPartial: {partial_r:.2f}R"

        await self.send(txt)
        self._last_trade_info = {
            "symbol": symbol, "side": side, "pnl": pnl,
            "r": r_multiple, "reason": exit_reason
        }

    async def notify_last_trade_summary(self):
        """Manual command: /last — shows last closed trade."""
        if not self._last_trade_info:
            await self.send("📭 No closed trades yet.")
            return
        t = self._last_trade_info
        emoji = "✅" if t["pnl"] > 0 else "❌"
        await self.send(
            f"📊 <b>Last Trade</b>\n"
            f"{emoji} {t['symbol']} {t['side'].upper()}\n"
            f"P&L: ${self.fmt_money(t['pnl'])} ({self.fmt_r(t['r'])})\n"
            f"Exit: {t['reason']}"
        )

    async def notify_engine_status(self, equity: float, realized: float,
                                   open_trades: int, win_rate: float, avg_r: float):
        """Periodic summary (e.g., every hour or on request)."""
        if not self.config.enabled:
            return
        txt = (
            f"📈 <b>Engine Status</b>\n"
            f"Equity: ${equity:,.2f}\n"
            f"Realized P&L: ${self.fmt_money(realized)}\n"
            f"Open trades: {open_trades}\n"
            f"Win rate: {win_rate:.1f}%\n"
            f"Avg R: {avg_r:.2f}"
        )
        await self.send(txt)


# Global instance for easy import
_notifier: Optional[TelegramNotifier] = None


def get_notifier(config: Optional[TelegramConfig] = None) -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        if config is None:
            config = TelegramConfig(
                token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
                enabled=bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
            )
        _notifier = TelegramNotifier(config)
    return _notifier


async def run_bot_polling(config: TelegramConfig):
    """Run bot with long-polling (for commands like /last)."""
    if not TELEGRAM_AVAILABLE:
        log.error("python-telegram-bot not installed: pip install python-telegram-bot")
        return

    from telegram.ext import Application, CommandHandler, ContextTypes

    notifier = TelegramNotifier(config)
    await notifier.start()

    app = Application.builder().token(config.token).build()

    async def last_cmd(update, context: ContextTypes.DEFAULT_TYPE):
        await notifier.notify_last_trade_summary()

    async def status_cmd(update, context: ContextTypes.DEFAULT_TYPE):
        # You'd hook engine here
        await update.message.reply_text("Use /last for last trade.")

    app.add_handler(CommandHandler("last", last_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    log.info("Telegram polling started")
    await app.run_polling()


# Sync wrapper for journal.py integration
async def _async_notify(coro):
    try:
        await coro
    except Exception as e:
        log.error(f"Telegram notify error: {e}")


def notify_entry_sync(trade_id: str, symbol: str, tf: str, side: str,
                      entry: float, stop: float, target: float, qty: float,
                      risk_cash: float, rr: float, setup: str):
    """Call from journal.py (sync context) — fire-and-forget."""
    notifier = get_notifier()
    if notifier.config.enabled:
        asyncio.run(_async_notify(notifier.notify_entry(
            trade_id, symbol, tf, side, entry, stop, target, qty,
            risk_cash, rr, setup
        )))


def notify_exit_sync(trade_id: str, symbol: str, tf: str, side: str,
                     entry: float, exit_price: float, pnl: float,
                     r_multiple: float, exit_reason: str, bars_held: int,
                     mfe_r: float = 0.0, mae_r: float = 0.0,
                     partial_r: float = 0.0):
    """Call from journal.py _close() — fire-and-forget."""
    notifier = get_notifier()
    if notifier.config.enabled:
        asyncio.run(_async_notify(notifier.notify_exit(
            trade_id, symbol, tf, side, entry, exit_price, pnl,
            r_multiple, exit_reason, bars_held, mfe_r, mae_r, partial_r
        )))


def notify_status_sync(equity: float, realized: float, open_trades: int,
                       win_rate: float, avg_r: float):
    """Periodic status — call from dashboard loop or scheduler."""
    notifier = get_notifier()
    if notifier.config.enabled:
        asyncio.run(_async_notify(notifier.notify_engine_status(
            equity, realized, open_trades, win_rate, avg_r
        )))


def notify_text_sync(text: str):
    """Seedha text bhejo (startup ping, heartbeat). No-op jab disabled."""
    notifier = get_notifier()
    if notifier.config.enabled:
        asyncio.run(_async_notify(notifier.send(text)))

if __name__ == "__main__":
    # Test: python -m src.paper.telegram_bot
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        asyncio.run(run_bot_polling(TelegramConfig(token, chat_id)))
    else:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars")