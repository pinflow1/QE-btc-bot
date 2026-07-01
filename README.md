# BTC Price Tracker Bot

A Telegram bot that tracks Bitcoin prices and sends alerts.

## Commands

- `/start` — Show help
- `/price` — Get current BTC/USD price
- `/alert <price>` — Set a price alert
- `/alerts` — List your alerts
- `/removealert <index>` — Remove an alert

## Deploy to Render

1. Fork this repo
2. Create a new Web Service on [Render](https://render.com)
3. Connect your GitHub repo
4. Set environment variable: `BOT_TOKEN`
5. Deploy

## Run Locally

```bash
pip install -r requirements.txt
BOT_TOKEN=your_token python btc_bot.py
