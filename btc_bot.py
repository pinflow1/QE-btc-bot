import os
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))
DATA_FILE = os.environ.get("ALERTS_FILE", "alerts.json")
PORT = int(os.environ.get("PORT", "10000"))

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin&vs_currencies=usd"
)

_lock = threading.Lock()


# ---------- persistence ----------

def load_alerts() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_alerts(alerts: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(alerts, f)


# ---------- price fetching ----------

def get_btc_price() -> float:
    resp = requests.get(COINGECKO_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()["bitcoin"]["usd"]


# ---------- command handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*BTC Price Tracker Bot*\n\n"
        "Commands:\n"
        "/price - Get current BTC/USD price\n"
        "/alert <price> - Set a price alert\n"
        "/alerts - List your alerts\n"
        "/removealert <index> - Remove an alert\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = get_btc_price()
        await update.message.reply_text(f"BTC/USD: ${p:,.2f}")
    except Exception as e:
        logger.exception("price fetch failed")
        await update.message.reply_text("Couldn't fetch the price right now, try again shortly.")


async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /alert <price>\nExample: /alert 65000")
        return
    try:
        target = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid number, e.g. /alert 65000")
        return

    with _lock:
        alerts = load_alerts()
        alerts.setdefault(chat_id, [])
        alerts[chat_id].append(target)
        save_alerts(alerts)

    await update.message.reply_text(f"Alert set: I'll notify you when BTC hits ${target:,.2f}")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    with _lock:
        alerts = load_alerts()
    user_alerts = alerts.get(chat_id, [])
    if not user_alerts:
        await update.message.reply_text("You have no active alerts. Set one with /alert <price>")
        return
    lines = [f"{i}. ${v:,.2f}" for i, v in enumerate(user_alerts)]
    await update.message.reply_text("Your alerts:\n" + "\n".join(lines))


async def remove_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /removealert <index>\nSee indexes with /alerts")
        return
    try:
        idx = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid index number.")
        return

    with _lock:
        alerts = load_alerts()
        user_alerts = alerts.get(chat_id, [])
        if idx < 0 or idx >= len(user_alerts):
            await update.message.reply_text("No alert with that index. See /alerts")
            return
        removed = user_alerts.pop(idx)
        alerts[chat_id] = user_alerts
        save_alerts(alerts)

    await update.message.reply_text(f"Removed alert for ${removed:,.2f}")


# ---------- background alert checker ----------

def alert_checker_loop(bot_token: str):
    from telegram import Bot
    import asyncio

    bot = Bot(token=bot_token)

    async def check_once():
        try:
            current_price = get_btc_price()
        except Exception:
            logger.exception("background price fetch failed")
            return

        with _lock:
            alerts = load_alerts()
            changed = False
            for chat_id, targets in list(alerts.items()):
                remaining = []
                for target in targets:
                    # Trigger if price crossed the target since we don't track direction,
                    # notify once then remove it.
                    if abs(current_price - target) / target <= 0.001 or (
                        current_price >= target
                    ):
                        try:
                            asyncio.run_coroutine_threadsafe(
                                bot.send_message(
                                    chat_id=int(chat_id),
                                    text=(
                                        f"🚨 BTC hit your alert price!\n"
                                        f"Target: ${target:,.2f}\n"
                                        f"Current: ${current_price:,.2f}"
                                    ),
                                ),
                                loop,
                            ).result(timeout=15)
                        except Exception:
                            logger.exception("failed to send alert message")
                            remaining.append(target)
                        changed = True
                    else:
                        remaining.append(target)
                alerts[chat_id] = remaining
            if changed:
                save_alerts(alerts)

    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    while True:
        asyncio.run_coroutine_threadsafe(check_once(), loop).result(timeout=30)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------- tiny health check server (Render web services need a bound port) ----------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # silence default request logging


def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=alert_checker_loop, args=(BOT_TOKEN,), daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("alert", alert))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(CommandHandler("removealert", remove_alert))

    # Ensure the main thread has an active event loop before PTB's run_polling
    # (older PTB versions call the now-removed implicit-loop-creation behavior,
    # which Python 3.14+ no longer supports).
    import asyncio as _asyncio
    try:
        _asyncio.get_event_loop()
    except RuntimeError:
        _asyncio.set_event_loop(_asyncio.new_event_loop())

    logger.info("Bot starting (polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
                                    
