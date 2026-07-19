import os
import sqlite3
from datetime import date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


DB_PATH = os.path.join(os.getcwd(), "instance", "bierkaessle.sqlite3")
BEER_PRICE = float(os.environ.get("BEER_PRICE", "1.50"))

# ──────────────────────────── Getränke-Katalog ────────────────────────────
DRINK_CATALOG = {
    "bier":   {"label": "🍺 Bier",            "price": 1.50},
    "radler": {"label": "🍋 Radler",           "price": 1.50},
    "cola":   {"label": "🥤 Cola/Fanta/Mezzo",  "price": 1.50},
    "wasser": {"label": "💧 Wasser",            "price": 1.00},
}


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
            drink_type TEXT NOT NULL DEFAULT 'bier',
            price_per_unit REAL NOT NULL DEFAULT 1.50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beer_id INTEGER NOT NULL UNIQUE,
            is_paid INTEGER NOT NULL DEFAULT 0,
            method TEXT CHECK(method IN ('BAR','PAYPAL') OR method IS NULL),
            marked_by_user_id INTEGER,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(beer_id) REFERENCES beers(id),
            FOREIGN KEY(marked_by_user_id) REFERENCES users(id)
        );
        """
    )
    try:
        conn.execute("ALTER TABLE beers ADD COLUMN drink_type TEXT NOT NULL DEFAULT 'bier'")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE beers ADD COLUMN price_per_unit REAL NOT NULL DEFAULT 1.50")
    except Exception:
        pass
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


def is_admin(user) -> bool:
    if user is None:
        return False
    if user["is_admin"]:
        return True
    admin_names = [n.strip() for n in os.environ.get("ADMIN_USERNAMES", "").split(",") if n.strip()]
    return user["username"] in admin_names


def month_str_today() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


# ──────────────────────────── Hilfsfunktion Eintrag ────────────────────────────

async def _eintragen(update: Update, drink_key: str, args) -> None:
    """Gemeinsame Logik für alle Direktbefehle (/bier, /radler, /cola, /wasser)."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Nicht verknüpft. Bitte /link <username> nutzen.")
        return

    amount = 1
    if args:
        try:
            amount = int(args[0])
        except ValueError:
            info = DRINK_CATALOG[drink_key]
            await update.message.reply_text(
                f"Bitte eine ganze Zahl angeben, z. B. /{drink_key} 3"
            )
            return

    if amount <= 0:
        await update.message.reply_text("Die Anzahl muss größer als 0 sein.")
        return

    today = date.today().isoformat()
    info = DRINK_CATALOG[drink_key]
    price = info["price"]
    conn = get_conn()
    conn.execute(
        "INSERT INTO beers (user_id, drinking_date, amount, drink_type, price_per_unit) VALUES (?, ?, ?, ?, ?)",
        (user["id"], today, amount, drink_key, price),
    )
    conn.commit()
    conn.close()

    euros = amount * price
    await update.message.reply_text(
        f"✅ {amount}× {info['label']} für {today} eingetragen.\nKosten: {euros:.2f} €"
    )


# ──────────────────────────── Befehle ────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = get_user_by_telegram_id(update.effective_user.id)
    admin_hint = ""
    if user and is_admin(user):
        admin_hint = (
            "\n\n🔑 Admin-Befehle:\n"
            "/admin_liste – Monatsstand aller Spieler\n"
            "/admin_offen – nur offene Beträge\n"
            "/admin_zahlung <id> <bar|paypal> – Zahlung markieren\n"
            "/admin_zahlung <id> reset – Zahlung zurücksetzen"
        )
    text = (
        "🍺 VfB Grötzingen AH Bierkässle Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 Befehle:\n"
        "/link <username>   – Telegram mit Web-Account verknüpfen\n\n"
        "🥤 Getränke eintragen:\n"
        "/bier [anzahl]     – 🍺 Bier             1,50 €\n"
        "/radler [anzahl]   – 🍋 Radler            1,50 €\n"
        "/cola [anzahl]     – 🥤 Cola/Fanta/Mezzo  1,50 €\n"
        "/wasser [anzahl]   – 💧 Wasser            1,00 €\n"
        "/getraenke         – vollständige Preisliste\n\n"
        "📊 Auswertung:\n"
        "/uebersicht – Monatsstand aller Spieler (wie Startseite)\n"
        "/status     – eigener Monatsstand (Summe + offen/bezahlt)\n"
        "/liste      – eigene Einzeleinträge diesen Monat\n\n"
        "/help       – diese Hilfe"
        + admin_hint
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def getraenke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt die aktuelle Preisliste."""
    lines = ["🧾 Preisliste:\n"]
    for key, info in DRINK_CATALOG.items():
        lines.append(f"{info['label']}: {info['price']:.2f} €  →  /{key} [anzahl]")
    await update.message.reply_text("\n".join(lines))


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

    cur.execute("UPDATE users SET telegram_id = ? WHERE id = ?", (telegram_id, user["id"]))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Telegram mit '{user['username']}' verknüpft.")


async def bier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/bier [anzahl] – 🍺 Bier à 1,50 €"""
    await _eintragen(update, "bier", context.args)


async def radler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/radler [anzahl] – 🍋 Radler à 1,50 €"""
    await _eintragen(update, "radler", context.args)


async def cola(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cola [anzahl] – 🥤 Cola/Fanta/Mezzo à 1,50 €"""
    await _eintragen(update, "cola", context.args)


async def wasser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/wasser [anzahl] – 💧 Wasser à 1,00 €"""
    await _eintragen(update, "wasser", context.args)


async def uebersicht(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Monatsübersicht aller Spieler – wie die Startseite der Web-App."""
    ms = month_str_today()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            u.username,
            COALESCE(SUM(b.amount), 0) AS total_drinks,
            COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros,
            COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=1 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS paid_euros,
            COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=0 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS open_euros
        FROM users u
        LEFT JOIN beers b
            ON u.id = b.user_id
            AND strftime('%Y-%m', b.drinking_date) = ?
        LEFT JOIN payments p ON p.beer_id = b.id
        GROUP BY u.id
        HAVING total_drinks > 0
        ORDER BY total_euros DESC
        """,
        (ms,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"Noch keine Einträge für {ms}.")
        return

    lines = [f"📊 Monatsübersicht {ms}:\n"]
    t_drinks = 0
    t_total = t_paid = t_open = 0.0
    for r in rows:
        t_drinks += r["total_drinks"]
        t_total  += r["total_euros"]
        t_paid   += r["paid_euros"]
        t_open   += r["open_euros"]
        paid_icon = "✅" if r["open_euros"] == 0 else "⚠️"
        lines.append(
            f"{paid_icon} {r['username']}: {r['total_drinks']} 🥤 | "
            f"{r['total_euros']:.2f} € | offen: {r['open_euros']:.2f} €"
        )
    lines.append(
        f"\n▶ Gesamt: {int(t_drinks)} Getränke | {t_total:.2f} €\n"
        f"✅ bezahlt: {t_paid:.2f} €  ⚠️ offen: {t_open:.2f} €"
    )
    await update.message.reply_text("\n".join(lines))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Nicht verknüpft. Bitte /link <username> nutzen.")
        return

    ms = month_str_today()
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(b.amount), 0) AS total_drinks,
            COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros,
            COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=1 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS paid_euros,
            COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=0 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS open_euros
        FROM beers b
        LEFT JOIN payments p ON p.beer_id = b.id
        WHERE b.user_id = ? AND strftime('%Y-%m', b.drinking_date) = ?
        """,
        (user["id"], ms),
    ).fetchone()
    conn.close()

    await update.message.reply_text(
        f"📊 Dein Stand {ms}:\n"
        f"Getränke gesamt:  {row['total_drinks']}  ({row['total_euros']:.2f} €)\n"
        f"✅ Bezahlt:       {row['paid_euros']:.2f} €\n"
        f"⚠️ Offen:         {row['open_euros']:.2f} €"
    )


async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Eigene Einträge des laufenden Monats mit Zahlstatus."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Nicht verknüpft. Bitte /link <username> nutzen.")
        return

    ms = month_str_today()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT b.id, b.drinking_date, b.amount, b.drink_type, b.price_per_unit,
               COALESCE(p.is_paid, 0) AS is_paid,
               p.method
        FROM beers b
        LEFT JOIN payments p ON p.beer_id = b.id
        WHERE b.user_id = ? AND strftime('%Y-%m', b.drinking_date) = ?
        ORDER BY b.drinking_date DESC
        """,
        (user["id"], ms),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"Keine Einträge für {ms}.")
        return

    lines = [f"🍺 Deine Einträge {ms}:\n"]
    total_euros = 0.0
    for r in rows:
        status_icon = "✅" if r["is_paid"] else "⚠️"
        method = f" ({r['method']})".lower() if r["method"] else ""
        label = DRINK_CATALOG.get(r["drink_type"], {}).get("label", r["drink_type"])
        euros = r["amount"] * r["price_per_unit"]
        total_euros += euros
        lines.append(
            f"{status_icon} #{r['id']} | {r['drinking_date']} | "
            f"{r['amount']}× {label} = {euros:.2f} €{method}"
        )
    lines.append(f"\nGesamt: {total_euros:.2f} €")
    await update.message.reply_text("\n".join(lines))


# ──────────────────────────── Admin ────────────────────────────

async def admin_liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: Monatsstand aller Spieler."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if not is_admin(user):
        await update.message.reply_text("⛔ Keine Admin-Rechte.")
        return

    ms = month_str_today()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT u.username,
               COALESCE(SUM(b.amount), 0) AS total_drinks,
               COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros,
               COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=1 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS paid_euros,
               COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=0 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS open_euros
        FROM users u
        LEFT JOIN beers b ON u.id = b.user_id AND strftime('%Y-%m', b.drinking_date) = ?
        LEFT JOIN payments p ON p.beer_id = b.id
        GROUP BY u.id
        HAVING total_drinks > 0
        ORDER BY total_euros DESC
        """,
        (ms,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"Keine Einträge für {ms}.")
        return

    lines = [f"📋 Monatsstand {ms}:\n"]
    t_drinks = t_paid = t_open = 0.0
    for r in rows:
        t_drinks += r["total_drinks"]
        t_paid += r["paid_euros"]
        t_open += r["open_euros"]
        lines.append(
            f"{r['username']}: {r['total_drinks']} 🥤 | "
            f"✅ {r['paid_euros']:.2f} € | "
            f"⚠️ {r['open_euros']:.2f} €"
        )
    lines.append(
        f"\n▶ Gesamt: {int(t_drinks)} Getränke\n"
        f"✅ {t_paid:.2f} €  ⚠️ {t_open:.2f} €"
    )
    await update.message.reply_text("\n".join(lines))


async def admin_offen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: nur Spieler mit offenen Beträgen."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if not is_admin(user):
        await update.message.reply_text("⛔ Keine Admin-Rechte.")
        return

    ms = month_str_today()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT u.username,
               COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=0 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS open_euros
        FROM users u
        LEFT JOIN beers b ON u.id = b.user_id AND strftime('%Y-%m', b.drinking_date) = ?
        LEFT JOIN payments p ON p.beer_id = b.id
        GROUP BY u.id
        HAVING open_euros > 0
        ORDER BY open_euros DESC
        """,
        (ms,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"✅ Alle Beträge für {ms} sind bezahlt!")
        return

    lines = [f"⚠️ Offene Beträge {ms}:\n"]
    for r in rows:
        lines.append(f"{r['username']}: {r['open_euros']:.2f} € offen")
    await update.message.reply_text("\n".join(lines))


async def admin_zahlung(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /admin_zahlung <beer_id> <bar|paypal|reset>"""
    user = get_user_by_telegram_id(update.effective_user.id)
    if not is_admin(user):
        await update.message.reply_text("⛔ Keine Admin-Rechte.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Verwendung: /admin_zahlung <beer_id> <bar|paypal|reset>\n"
            "Die beer_id steht in /liste oder /admin_liste hinter #."
        )
        return

    try:
        beer_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("beer_id muss eine Zahl sein.")
        return

    method_raw = context.args[1].upper()
    if method_raw == "RESET":
        is_paid = 0
        method = None
    elif method_raw in ("BAR", "PAYPAL"):
        is_paid = 1
        method = method_raw
    else:
        await update.message.reply_text("Methode muss bar, paypal oder reset sein.")
        return

    conn = get_conn()
    entry = conn.execute("SELECT id FROM beers WHERE id = ?", (beer_id,)).fetchone()
    if entry is None:
        conn.close()
        await update.message.reply_text(f"Kein Eintrag mit ID {beer_id} gefunden.")
        return

    conn.execute(
        """
        INSERT INTO payments (beer_id, is_paid, method, marked_by_user_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(beer_id) DO UPDATE SET
            is_paid = excluded.is_paid,
            method = excluded.method,
            marked_by_user_id = excluded.marked_by_user_id,
            marked_at = CURRENT_TIMESTAMP
        """,
        (beer_id, is_paid, method, user["id"]),
    )
    conn.commit()
    conn.close()

    if method_raw == "RESET":
        await update.message.reply_text(f"🔄 Eintrag #{beer_id} auf offen zurückgesetzt.")
    else:
        await update.message.reply_text(
            f"✅ Eintrag #{beer_id} als bezahlt markiert ({method_raw}).")


# ──────────────────────────── Main ────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ist nicht gesetzt")

    init_db()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",          start))
    app.add_handler(CommandHandler("help",           help_cmd))
    app.add_handler(CommandHandler("link",           link))
    app.add_handler(CommandHandler("bier",           bier))
    app.add_handler(CommandHandler("radler",         radler))
    app.add_handler(CommandHandler("cola",           cola))
    app.add_handler(CommandHandler("wasser",         wasser))
    app.add_handler(CommandHandler("getraenke",      getraenke))
    app.add_handler(CommandHandler("uebersicht",     uebersicht))
    app.add_handler(CommandHandler("status",         status))
    app.add_handler(CommandHandler("liste",          liste))
    app.add_handler(CommandHandler("admin_liste",    admin_liste))
    app.add_handler(CommandHandler("admin_offen",    admin_offen))
    app.add_handler(CommandHandler("admin_zahlung",  admin_zahlung))

    app.run_polling()


if __name__ == "__main__":
    main()
