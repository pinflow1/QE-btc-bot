# BTC Price Tracker Bot

A Telegram bot that tracks Bitcoin prices and sends alerts.

## Commands

- `/start` — Show help
- `/price` — Get current BTC/USD price
- `/alert <price>` — Set a price alert
- `/alerts` — List your alerts
- `/removealert <index>` — Remove an alert

## Setup (local)

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram and copy the token.
2. `pip install -r requirements.txt`
3. Set the token:
   ```
   export TELEGRAM_BOT_TOKEN=your_token_here
   ```
4. Run it:
   ```
   python btc_bot.py
   ```

## Deploy to Render

1. Push this repo to GitHub.
2. Create a new Web Service on [Render](https://render.com), pointing at this repo (it will pick up `render.yaml` automatically).
3. In the Render dashboard, set the `TELEGRAM_BOT_TOKEN` environment variable to your bot's token.
4. Deploy. The bot polls Telegram for commands and checks the BTC price every 60 seconds (configurable via `CHECK_INTERVAL_SECONDS`) to fire any alerts.

Notes:
- Price data comes from the free CoinGecko API (no key required).
- Alerts are stored in a local `alerts.json` file. On Render's free tier the filesystem is ephemeral, so alerts reset on redeploy/restart — fine for personal use, but let me know if you want a proper database instead.
- 
