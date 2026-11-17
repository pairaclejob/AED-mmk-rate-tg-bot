import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_TELEGRAM_ID"])
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
DB_PATH = os.getenv("DATABASE_PATH", "rates.sqlite3")
REMINDER_HOURS = 24
logging.basicConfig(level=logging.INFO)

EN_STALE = "⚠️ This rate is over 24 hours old. Please confirm it with the admin before transferring."
MY_STALE = "⚠️ ဤငွေလဲနှုန်းကို နောက်ဆုံးပြင်ဆင်ထားသည်မှာ ၂၄ နာရီကျော်ပါပြီ။ ငွေလွှဲမပြုလုပ်မီ Admin ထံ အတည်ပြုပါ။"


def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en')")
    con.commit()
    return con


def get(key, default=""):
    with db() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def put(key, value):
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def is_admin(update):
    return update.effective_user and update.effective_user.id == ADMIN_ID


def stale():
    raw = get("updated_at")
    if not raw:
        return True
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(raw) >= timedelta(hours=REMINDER_HOURS)
    except ValueError:
        return True


def num(s):
    try:
        value = Decimal(s.replace(",", ""))
        return value if value > 0 and value.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


def fmt(n):
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def parse_quote(text):
    """Recognize common English/Burmese shorthand and explicit currency pairs."""
    s = text.lower().replace("ကျပ်", " mmk").replace("မြန်မာငွေ", " mmk").replace("ဒေါ်လာ", " aed")
    amount_match = re.search(r"\d[\d,]*(?:\.\d+)?", s)
    if not amount_match:
        return None
    amount = num(amount_match.group())
    if not amount:
        return None
    has_aed = bool(re.search(r"\baed\b| dirham|\bdirhams\b|ဒ်?ရမ်", s))
    has_mmk = bool(re.search(r"\bmmk\b|\bkyat\b|\bkyats\b|ကျပ်|မြန်မာငွေ", text.lower()))
    to_mmk = bool(re.search(r"\bto\s*mmk\b|\bin\s*mmk\b|\bmmk\s*ရမ|ရမယ်|ရမလဲ|ရရှိ", s))
    to_aed = bool(re.search(r"\bto\s*aed\b|\bin\s*aed\b|\baed\s*ရမ|ရမယ်|ရမလဲ|ရရှိ", s))
    if has_aed and (to_mmk or not has_mmk):
        return (amount, "aed_mmk")
    if has_mmk and (to_aed or not has_aed):
        return (amount, "mmk_aed")
    return None


def quote(amount, direction, lang):
    rate_key = "aed_mmk" if direction == "aed_mmk" else "mmk_aed"
    rate = num(get(rate_key))
    if not rate:
        return ("Rates are not set yet. Please contact the admin." if lang == "en" else "ငွေလဲနှုန်း မသတ်မှတ်ရသေးပါ။ Admin ထံ ဆက်သွယ်ပါ။")
    result = amount * rate if direction == "aed_mmk" else amount / rate
    if lang == "my":
        text = (f"{fmt(amount)} AED အတွက် **{fmt(result)} ကျပ်** ရရှိပါမည်။" if direction == "aed_mmk"
                else f"{fmt(amount)} ကျပ်အတွက် **{fmt(result)} AED** ရရှိပါမည်။")
        return text + ("\n\n" + MY_STALE if stale() else "")
    text = (f"For {fmt(amount)} AED, you will receive **{fmt(result)} MMK**." if direction == "aed_mmk"
            else f"For {fmt(amount)} MMK, you will receive **{fmt(result)} AED**.")
    return text + ("\n\n" + EN_STALE if stale() else "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(id,language) VALUES(?, 'en')", (update.effective_user.id,))
    await update.message.reply_text("Welcome! Send an amount like ‘20 AED to MMK’ or ‘150000 MMK to AED’. Use /language en or /language my.\nကြိုဆိုပါတယ်။ 20 AED to MMK သို့မဟုတ် 150000 MMK to AED ဟု ရိုက်ထည့်နိုင်ပါသည်။", parse_mode="Markdown")


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ("en", "my"):
        await update.message.reply_text("Use /language en or /language my")
        return
    lang = context.args[0].lower()
    with db() as con:
        con.execute("INSERT INTO users(id,language) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET language=excluded.language", (update.effective_user.id, lang))
    await update.message.reply_text("Language set to English." if lang == "en" else "ဘာသာစကားကို မြန်မာဘာသာအဖြစ် ပြောင်းလဲပြီးပါပြီ။")


async def setrate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) != 2 or not all(num(a) for a in context.args):
        await update.message.reply_text("Usage: /setrate AED_TO_MMK MMK_PER_AED\nExample: /setrate 1200 1250 (illustrative only)")
        return
    put("aed_mmk", num(context.args[0]))
    put("mmk_aed", num(context.args[1]))
    put("updated_at", datetime.now(timezone.utc).isoformat())
    put("reminded_for", "")
    await update.message.reply_text(f"Rates saved. AED → MMK: {fmt(num(context.args[0]))}; MMK → AED rate: {fmt(num(context.args[1]))} MMK per AED. Reminder reset for 24 hours.")


async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Rates are available through quotations. /rates is admin-only.")
        return
    a, m = get("aed_mmk"), get("mmk_aed")
    await update.message.reply_text(f"AED → MMK: {a or 'not set'}\nMMK → AED: {m or 'not set'} MMK per AED\nLast update: {get('updated_at','never')}\nStatus: {'STALE' if stale() else 'current'}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(f"Bot active. Rates {'stale' if stale() else 'current'}; updated {get('updated_at','never')}.")


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("You are the administrator.")
        return
    username = ADMIN_USERNAME.lstrip("@")
    if username:
        await update.message.reply_text(f"Contact the admin: https://t.me/{username}")
    else:
        await update.message.reply_text("Send your message here and it will be forwarded to the admin.")
        try:
            await context.bot.forward_message(ADMIN_ID, update.effective_chat.id, update.message.message_id)
            await context.bot.send_message(ADMIN_ID, f"Customer handoff from {update.effective_user.full_name} (Telegram ID {update.effective_user.id}). Reply to them directly in Telegram.")
        except Exception:
            await update.message.reply_text("I could not forward that message. Please try again later.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text("Admin: /setrate <AED→MMK> <MMK per AED>, /rates, /status. Customers: send a currency amount, /language en|my, /contact.")
    else:
        await update.message.reply_text("Send e.g. 20 AED to MMK or 150000 MMK to AED. Use /language en or /language my; /contact for help.\nဥပမာ 20 AED to MMK သို့မဟုတ် 150000 MMK to AED ဟု ရိုက်ထည့်ပါ။")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    # While waiting for admin input, a plain `number number` is a convenient update.
    if is_admin(update) and re.fullmatch(r"\s*\d[\d,.]*\s+\d[\d,.]*\s*", msg.text):
        context.args = re.findall(r"\d[\d,.]*", msg.text)
        await setrate(update, context)
        return
    with db() as con:
        row = con.execute("SELECT language FROM users WHERE id=?", (update.effective_user.id,)).fetchone()
    lang = row[0] if row else "en"
    parsed = parse_quote(msg.text)
    if parsed:
        await msg.reply_text(quote(*parsed, lang), parse_mode="Markdown")
    elif re.search(r"rate|price|exchange|စျေး|နှုန်း", msg.text.lower()):
        await msg.reply_text("Send a full question such as 20 AED to MMK or 150000 MMK to AED. Use /contact for a personal quote.\n20 AED to MMK သို့မဟုတ် 150000 MMK to AED ဟု အပြည့်အစုံ ရိုက်ထည့်ပါ။")
    else:
        await contact(update, context)


async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    updated = get("updated_at")
    if not updated:
        return
    if stale() and get("reminded_for") != updated:
        await context.bot.send_message(ADMIN_ID, "⏰ Your AED/MMK rates have not been updated for 24 hours. Update them with /setrate <AED→MMK> <MMK per AED>. Quotes will continue with a prominent stale-rate warning.")
        put("reminded_for", updated)


def main():
    db().close()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("language", language))
    app.add_handler(CommandHandler("setrate", setrate))
    app.add_handler(CommandHandler("rates", rates))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("contact", contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(reminder_job, interval=300, first=30)
    app.run_polling()


if __name__ == "__main__":
    main()
