# Telegram AED/MMK exchange bot

Uses only the rates you set; it does not fetch market rates. Stores rates in SQLite and keeps them across restarts. Quotes continue when stale and carry English or Burmese warnings.

## BotFather and first setup

1. Open [@BotFather](https://t.me/BotFather), send `/newbot`, choose a display name and a unique username ending in `bot`.
2. Copy the token into a private `.env` file on your server. Never send it in chat or commit it.
3. Open the newly created bot and send `/start`.
4. Set commands in BotFather with `/setcommands`:

   ```text
   start - Start the exchange assistant
   help - Show calculator and help
   language - Choose English or Burmese
   contact - Contact the administrator
   setrate - Admin: set AED/MMK rates
   rates - Admin: view current rates
   status - Admin: view bot status
   ```

## Run on a server

Install Python 3.11+, install dependencies with `pip install -r requirements.txt`, set the environment variables in `.env.example` in the hosting provider's secret/environment settings, then run `python bot.py`. Keep the SQLite file on persistent storage. Run one bot process only.

`ADMIN_TELEGRAM_ID` must be your numeric Telegram user ID. Set this before starting; only that ID can change or inspect rates. `ADMIN_USERNAME` is optional and allows `/contact` to link directly to you. Without it, customer messages sent to `/contact` are forwarded to the admin. For direct replies use Telegram's forwarded message context.

## Rate meaning

`/setrate 1200 1250` sets AED→MMK to 1 AED = 1,200 MMK, and the reverse quote as 1 AED = 1,250 MMK (so MMK amount is divided by 1,250). Values are illustrative examples only. Enter your own rates. Every update resets the 24-hour reminder timer.

The bot checks every five minutes and sends one private reminder once a rate update becomes 24 hours old. Customers continue receiving quotes with a prominent bilingual stale-rate warning. `/language en` and `/language my` select the preferred response language.
