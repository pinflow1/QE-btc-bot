import logging
import asyncio
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import aiohttp

# ─── CONFIG ─────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN", "8901119327:AAHf19GS27It-ssOBTReXk3sS_JH1dC4s60")
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

# In-memory alert storage: {user_id: [target_price, ...]}
ALERTS = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── HELPERS ────────────────────────────────────────────
async def fetch_btc_price() -> float:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            COINGECKO_API,
            params={"ids": "bitcoin", "vs_currencies": "usd"}
        ) as resp:
            if resp.status != 200:
                raise ConnectionError(f"API returned {resp.status}")
            data = await resp.json()
            return float(data["bitcoin"]["usd"])

# ─── COMMANDS ───────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *BTC Price Tracker*\n\n"
        "• /price — Get current BTC/USD price\n"
        "• /alert `<price>` — Set a price alert\n"
        "• /alerts — List your active alerts\n"
        "• /removealert `<index>` — Remove an alert\n\n"
        "_Alerts are checked every 60 seconds._",
        parse_mode="Markdown"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = await fetch_btc_price()
        await update.message.reply_text(
            f"💰 *BTC Price*\n`${p:,.2f}` USD",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        await update.message.reply_text("❌ Couldn't fetch price. Try again in a moment.")

async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/alert 75000`", parse_mode="Markdown")
        return

    try:
        target = float(context.args[0])
        if target <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid positive number.")
        return

    ALERTS.setdefault(user_id, []).append(target)
    await update.message.reply_text(
        f"✅ Alert set for `${target:,.2f}`\nI'll message you when BTC crosses it.",
        parse_mode="Markdown"
    )

async def alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_alerts = ALERTS.get(user_id, [])
    if not user_alerts:
        await update.message.reply_text("You have no active alerts.")
        return

    lines = [f"*{i}.* `${p:,.2f}`" for i, p in enumerate(user_alerts, 1)]
    await update.message.reply_text(
        "🚨 *Your Alerts*\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def removealert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/removealert 1`", parse_mode="Markdown")
        return

    try:
        idx = int(context.args[0]) - 1
        user_alerts = ALERTS.get(user_id, [])
        if 0 <= idx < len(user_alerts):
            removed = user_alerts.pop(idx)
            if not user_alerts:
                del ALERTS[user_id]
            await update.message.reply_text(f"✅ Removed alert for `${removed:,.2f}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Invalid index. Use /alerts to see your list.")
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid index number.")

# ─── BACKGROUND JOB ─────────────────────────────────────
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    try:
        price_now = await fetch_btc_price()
        logger.info(f"Alert check: BTC @ ${price_now:,.2f}")

        for user_id, targets in list(ALERTS.items()):
            for target in targets[:]:
                if price_now >= target:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🚨 *BTC Alert Triggered!*\n"
                             f"Target: `${target:,.2f}`\n"
                             f"Current: `${price_now:,.2f}`",
                        parse_mode="Markdown"
                    )
                    ALERTS[user_id].remove(target)

            if not ALERTS[user_id]:
                del ALERTS[user_id]
    except Exception as e:
        logger.error(f"Alert check error: {e}")

# ─── MAIN ───────────────────────────────────────────────
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("alert", alert))
    application.add_handler(CommandHandler("alerts", alerts))
    application.add_handler(CommandHandler("removealert", removealert))

    application.job_queue.run_repeating(check_alerts, interval=60, first=10)

    application.run_polling()

if __name__ == "__main__":
    main()
