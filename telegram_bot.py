import os
import sqlite3
from datetime import date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


DB_PATH = os.path.join(os.getcwd(), "instance", "bierkaessle.sqlite3")
BEER_PRICE = float(os.environ.get("BEER_PRICE", "1.50"))


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_id INTEGER UNIQUE,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS beers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            drinking_date DATE NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    conn.commit()
    conn.close()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_by_telegram_id(tg_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
    user = cur.fetchone()
    conn.close()
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Willkommen beim VfB Grötzingen AH Bierkässle Bot!\n\n"
        "Verfügbare Befehle:\n"
        "/link <username> – Telegram mit deinem Web-Account verknüpfen\n"
        "/bier <anzahl> – Biere für heute eintragen (Standard: 1)\n"
        "/status – deinen aktuellen Monatsstand anzeigen\n"
        "/help – diese Hilfe anzeigen"
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Bitte so verwenden: /link <username>")
        return

    username = context.args[0].strip()
    telegram_id = update.effective_user.id

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cur.fetchone()

    if user is None:
        conn.close()
        await update.message.reply_text(
            "Benutzername nicht gefunden. Bitte zuerst in der Web-App registrieren."
        )
        return

    cur.execute(
        "UPDATE users SET telegram_id = ? WHERE id = ?",
        (telegram_id, user["id"]),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Telegram-Konto wurde mit '{user['username']}' verknüpft."
    )


async def bier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = get_user_by_telegram_id(update.effective_user.id)

    if user is None:
        await update.message.reply_text(
            "Dein Telegram-Konto ist noch nicht verknüpft. Bitte zuerst /link <username> nutzen."
        )
        return

    amount = 1
    if context.args:
        try:
            amount = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "Bitte eine ganze Zahl angeben, z. B. /bier 3"
            )
            return

    if amount <= 0:
        await update.message.reply_text("Die Anzahl muss größer als 0 sein.")
        return

    today = date.today().isoformat()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO beers (user_id, drinking_date, amount) VALUES (?, ?, ?)",
        (user["id"], today, amount),
    )
    conn.commit()
    conn.close()

    euros = amount * BEER_PRICE
    text = (
        f"Eingetragen: {amount} Bier(e) für heute ({today}).\n"
        f"Kosten: {euros:.2f} €"
    )
    await update.message.reply_text(text)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = get_user_by_telegram_id(update.effective_user.id)

    if user is None:
        await update.message.reply_text(
            "Dein Telegram-Konto ist noch nicht verknüpft. Bitte zuerst /link <username> nutzen."
        )
        return

    today = date.today()
    month_str = f"{today.year:04d}-{today.month:02d}"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS beers
        FROM beers
        WHERE user_id = ? AND strftime('%Y-%m', drinking_date) = ?
        """,
        (user["id"], month_str),
    )
    row = cur.fetchone()
    conn.close()

    beers = row["beers"] or 0
    euros = beers * BEER_PRICE

    await update.message.reply_text(
        f"Dein Stand für {month_str}: {beers} Bier(e) = {euros:.2f} €"
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ist nicht gesetzt")

    init_db()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(CommandHandler("bier", bier))
    app.add_handler(CommandHandler("status", status))

    app.run_polling()


if __name__ == "__main__":
    main()
