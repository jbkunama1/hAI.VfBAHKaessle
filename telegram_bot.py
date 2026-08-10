import calendar
import json
import math
import os
import sqlite3
import sys
from datetime import date, datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


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

def _book(user, drink_key: str, amount: int):
    """Legt den DB-Eintrag an und liefert (info, today) zurück."""
    info = DRINK_CATALOG[drink_key]
    today = date.today().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO beers (user_id, drinking_date, amount, drink_type, price_per_unit) VALUES (?, ?, ?, ?, ?)",
        (user["id"], today, amount, drink_key, info["price"]),
    )
    conn.commit()
    conn.close()
    return info, today


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

    info, today = _book(user, drink_key, amount)

    euros = amount * info["price"]
    await update.message.reply_text(
        f"✅ {amount}× {info['label']} für {today} eingetragen.\nKosten: {euros:.2f} €"
    )


# ──────────────────────────── Report-Helfer ────────────────────────────

def _query_month_overview(ms: str):
    """Zeilen für die Monatsübersicht aller Spieler."""
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
    return rows


def _format_overview(rows, ms: str) -> str:
    if not rows:
        return f"Noch keine Einträge für {ms}."

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
    return "\n".join(lines)


def _query_user_status(user_id: int, ms: str):
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
        (user_id, ms),
    ).fetchone()
    conn.close()
    return row


def _format_status(row, ms: str) -> str:
    return (
        f"📊 Dein Stand {ms}:\n"
        f"Getränke gesamt:  {row['total_drinks']}  ({row['total_euros']:.2f} €)\n"
        f"✅ Bezahlt:       {row['paid_euros']:.2f} €\n"
        f"⚠️ Offen:         {row['open_euros']:.2f} €"
    )


def _query_user_entries(user_id: int, ms: str):
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
        (user_id, ms),
    ).fetchall()
    conn.close()
    return rows


def _format_entries(rows, ms: str) -> str:
    if not rows:
        return f"Keine Einträge für {ms}."

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
    return "\n".join(lines)


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
    rows = _query_month_overview(ms)
    text = _format_overview(rows, ms)
    await update.message.reply_text(text)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Nicht verknüpft. Bitte /link <username> nutzen.")
        return

    ms = month_str_today()
    row = _query_user_status(user["id"], ms)
    await update.message.reply_text(_format_status(row, ms))


async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Eigene Einträge des laufenden Monats mit Zahlstatus."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Nicht verknüpft. Bitte /link <username> nutzen.")
        return

    ms = month_str_today()
    rows = _query_user_entries(user["id"], ms)
    text = _format_entries(rows, ms)
    await update.message.reply_text(text)


# ──────────────────────────── Inline-Buttons / Menüs ────────────────────────────

def build_main_menu(admin: bool = False) -> InlineKeyboardMarkup:
    """Hauptmenü: Übersicht über alle Aktionen."""
    keyboard = []
    row = []
    for key, info in DRINK_CATALOG.items():
        if len(row) == 2:
            keyboard.append(row)
            row = []
        row.append(InlineKeyboardButton(info["label"], callback_data=f"drink:{key}"))
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("📊 Monatsübersicht", callback_data="overview")])
    keyboard.append([InlineKeyboardButton("👤 Mein Status", callback_data="status")])
    keyboard.append([InlineKeyboardButton("📋 Meine Einträge", callback_data="list")])
    if admin:
        keyboard.append([InlineKeyboardButton("🔑 Admin-Bereich", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)


def build_drink_menu() -> InlineKeyboardMarkup:
    """Getränke-Auswahl mit Mengen-Buttons."""
    keyboard = []
    for key, info in DRINK_CATALOG.items():
        keyboard.append([InlineKeyboardButton(f"{info['label']} ({info['price']:.2f} €)", callback_data=f"drink:{key}")])
    keyboard.append([InlineKeyboardButton("↩️ Zurück zum Menü", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def build_admin_menu() -> InlineKeyboardMarkup:
    """Administration: nur für Admins sichtbar."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Gesamtübersicht", callback_data="admin_overview")],
        [InlineKeyboardButton("⚠️ Offene Beträge", callback_data="admin_open")],
        [InlineKeyboardButton("↩️ Zurück zum Menü", callback_data="menu")],
    ])


def _require_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> sqlite3.Row | None:
    """Holt den verknüpften User oder antwortet mit Fehlermeldung."""
    user = get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        context.bot.loop.create_task(
            update.effective_chat.send_message(
                "🔗 Nicht verknüpft. Bitte zuerst /link <username> verwenden."
            )
        )
        return None
    return user


# ──────────────────────────── Callback-Handler ────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zentrale Verarbeitung aller Inline-Button-Klicks."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    ms = month_str_today()

    user = get_user_by_telegram_id(update.effective_user.id)
    admin = bool(user and is_admin(user))

    # ── Zurück zum Hauptmenü ──
    if data == "menu":
        text = "🍺 Hauptmenü"
        await query.edit_message_text(text, reply_markup=build_main_menu(admin))
        return

    # ── Getränk wählen: Getränk im Menü angeklickt → Mengenauswahl anzeigen ──
    if data.startswith("drink:"):
        drink_key = data.split(":", 1)[1]
        if drink_key not in DRINK_CATALOG:
            await query.edit_message_text("❓ Unbekanntes Getränk.", reply_markup=build_main_menu(admin))
            return
        info = DRINK_CATALOG[drink_key]
        keyboard = [[InlineKeyboardButton(str(n), callback_data=f"qty:{drink_key}:{n}") for n in range(1, 6)]]
        keyboard.append([InlineKeyboardButton("↩️ Abbrechen", callback_data="menu")])
        await query.edit_message_text(
            f"🥤 {info['label']} ({info['price']:.2f} €) – Anzahl wählen:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ── Menge wählen → Buchung durchführen ──
    if data.startswith("qty:"):
        if user is None:
            await query.edit_message_text("🔗 Nicht verknüpft. Bitte zuerst /link <username>.")
            return
        _, drink_key, amount_str = data.split(":", 2)
        amount = int(amount_str)
        info, today = _book(user, drink_key, amount)
        euros = amount * info["price"]
        await query.edit_message_text(
            f"✅ {amount}× {info['label']} für {today} eingetragen.\n"
            f"Kosten: {euros:.2f} €",
            reply_markup=build_main_menu(admin),
        )
        return

    # ── Übersicht aller Spieler ──
    if data == "overview" or data == "admin_overview":
        rows = _query_month_overview(ms)
        text = _format_overview(rows, ms)
        await query.edit_message_text(text, reply_markup=build_main_menu(admin))
        return

    # ── Eigener Status ──
    if data == "status":
        if user is None:
            await query.edit_message_text("🔗 Nicht verknüpft. Bitte zuerst /link <username>.")
            return
        row = _query_user_status(user["id"], ms)
        await query.edit_message_text(_format_status(row, ms), reply_markup=build_main_menu(admin))
        return

    # ── Eigene Einträge mit Löschen-Buttons ──
    if data == "list":
        if user is None:
            await query.edit_message_text("🔗 Nicht verknüpft. Bitte zuerst /link <username>.")
            return
        rows = _query_user_entries(user["id"], ms)
        text = _format_entries(rows, ms)
        keyboard = [[InlineKeyboardButton("🗑 letzte Aktion rückgängig", callback_data="undo")]]
        keyboard.append([InlineKeyboardButton("↩️ Zurück zum Menü", callback_data="menu")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ── Letzte eigene Aktion rückgängig machen ──
    if data == "undo":
        if user is None:
            await query.edit_message_text("🔗 Nicht verknüpft. Bitte zuerst /link <username>.")
            return
        conn = get_conn()
        last = conn.execute(
            "SELECT id, amount, drink_type FROM beers WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if last is None:
            conn.close()
            await query.edit_message_text("Kein Eintrag gefunden.", reply_markup=build_main_menu(admin))
            return
        conn.execute("DELETE FROM beers WHERE id = ?", (last["id"],))
        conn.execute("DELETE FROM payments WHERE beer_id = ?", (last["id"],))
        conn.commit()
        conn.close()
        label = DRINK_CATALOG.get(last["drink_type"], {}).get("label", last["drink_type"])
        # Danach zurück zur Liste
        rows = _query_user_entries(user["id"], ms)
        text = _format_entries(rows, ms)
        keyboard = [[InlineKeyboardButton("🗑 letzte Aktion rückgängig", callback_data="undo")]]
        keyboard.append([InlineKeyboardButton("↩️ Zurück zum Menü", callback_data="menu")])
        await query.edit_message_text(
            f"🗑 Letzten Eintrag (#{last['id']}, {last['amount']}× {label}) gelöscht.\n\n{text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ── Link-Info ──
    if data == "link_info":
        await query.edit_message_text(
            "🔗 Um den Bot mit deinem Web-Konto zu verknüpfen, sende:\n/link <dein_benutzername>",
            reply_markup=build_main_menu(admin),
        )
        return

    # ── Admin-Bereich ──
    if data == "admin":
        if not admin:
            await query.edit_message_text("⛔ Keine Admin-Rechte.", reply_markup=build_main_menu(False))
            return
        await query.edit_message_text("🔑 Admin-Bereich", reply_markup=build_admin_menu())
        return

    # ── Admin: Offene Beträge mit Bezahl-Buttons ──
    if data == "admin_open":
        if not admin:
            await query.edit_message_text("⛔ Keine Admin-Rechte.")
            return
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT b.id, b.amount, b.drink_type, b.drinking_date, u.username,
                   b.amount * b.price_per_unit AS euros
            FROM beers b
            JOIN users u ON u.id = b.user_id
            LEFT JOIN payments p ON p.beer_id = b.id
            WHERE COALESCE(p.is_paid, 0) = 0
            ORDER BY b.drinking_date DESC, b.id DESC
            LIMIT 20
            """
        ).fetchall()
        conn.close()
        if not rows:
            await query.edit_message_text("✅ Keine offenen Beträge.", reply_markup=build_main_menu(admin))
            return
        lines = ["⚠️ Offene Einträge:\n"]
        keyboard = []
        for r in rows:
            lines.append(f"#{r['id']} {r['username']}: {r['amount']}× {DRINK_CATALOG.get(r['drink_type'], {}).get('label', r['drink_type'])} – {r['euros']:.2f} €")
            keyboard.append([InlineKeyboardButton(f"#{r['id']} {r['username']} – bezahlt (Bar)", callback_data=f"pay:{r['id']}:BAR")])
            keyboard.append([InlineKeyboardButton(f"#{r['id']} {r['username']} – bezahlt (PayPal)", callback_data=f"pay:{r['id']}:PAYPAL")])
        keyboard.append([InlineKeyboardButton("↩️ Zurück zum Menü", callback_data="menu")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ── Admin: Zahlung als bezahlt markieren ──
    if data.startswith("pay:"):
        if not admin:
            await query.edit_message_text("⛔ Keine Admin-Rechte.")
            return
        _, beer_id_str, method = data.split(":", 2)
        beer_id = int(beer_id_str)
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO payments (beer_id, is_paid, method, marked_by_user_id)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(beer_id) DO UPDATE SET
                is_paid = 1,
                method = excluded.method,
                marked_by_user_id = excluded.marked_by_user_id,
                marked_at = CURRENT_TIMESTAMP
            """,
            (beer_id, method, user["id"]),
        )
        conn.commit()
        conn.close()
        await query.edit_message_text(f"✅ Eintrag #{beer_id} als bezahlt markiert ({method}).", reply_markup=build_main_menu(admin))
        return

    # ── Fallback: unbekannte Aktion ──
    await query.edit_message_text("Unbekannte Aktion.", reply_markup=build_main_menu(admin))


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Öffnet das Hauptmenü mit Inline-Buttons."""
    user = get_user_by_telegram_id(update.effective_user.id)
    admin = bool(user and is_admin(user))
    await update.message.reply_text("🍺 Hauptmenü", reply_markup=build_main_menu(admin))


# ──────────────────────────── Automatische Statusnachrichten (an Admins) ────────────────────────────

STATUS_STATE_FILE = os.path.join(os.path.dirname(DB_PATH), "status_state.json")
STATUS_CONFIG_FILE = os.path.join(os.path.dirname(DB_PATH), "status_config.json")

def _load_status_config() -> dict:
    """Lädt Status-Konfiguration vom Shared Volume (z.B. daily_time und poll_seconds)."""
    try:
        with open(STATUS_CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _status_daily_time() -> time:
    """Uhrzeit der Tages-/Monatsmeldung, konfigurierbar per Admin-UI (status_config.json) oder STATUS_DAILY_TIME (HH:MM)."""
    config = _load_status_config()
    raw = config.get("daily_time") or os.environ.get("STATUS_DAILY_TIME") or "23:00"
    try:
        hour, minute = [int(p) for p in raw.split(":")]
        return time(hour, minute)
    except Exception:
        print(f"[Status] Ungültiges STATUS_DAILY_TIME={raw!r}, verwende 23:00", file=sys.stderr)
        return time(23, 0)


def _status_poll_seconds() -> float:
    """Poll-Intervall für neue Einträge, konfigurierbar per STATUS_POLL_SECONDS (Sekunden) ODER admin UI."""
    config = _load_status_config()
    try:
        value = float(config.get("poll_seconds") or os.environ.get("STATUS_POLL_SECONDS") or "30")
        if value >= 5 and math.isfinite(value):
            return value
    except Exception:
        pass
    print("[Status] Ungültiges STATUS_POLL_SECONDS, verwende 30s", file=sys.stderr)
    return 30.0


async def _status_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tick-Job (jede Minute): prüft ob Tages-/Monatsmeldung fällig ist."""
    now = datetime.now()
    cfg_time = _status_daily_time()
    # Nur zur konfigurierten Minute feuern
    if now.hour != cfg_time.hour or now.minute != cfg_time.minute:
        return

    today_iso = date.today().isoformat()
    state = _load_status_state()

    # Monatsmeldung? (am letzten Tag des Monats)
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    is_last_day = (now.day == last_day_of_month)
    month_key = today_iso[:7]  # YYYY-MM

    if is_last_day and state.get("last_monthly") != month_key:
        await _send_monthly_summary(context)
        state["last_monthly"] = month_key
        state["last_daily"] = today_iso # Monat deckt Tag ab
        _save_status_state(state)
        return

    # Tagesmeldung?
    if state.get("last_daily") != today_iso:
        await _send_daily_summary(context)
        state["last_daily"] = today_iso
        _save_status_state(state)


def _load_status_state() -> dict:
    try:
        with open(STATUS_STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_beer_id": 0, "last_user_id": 0}


def _save_status_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATUS_STATE_FILE), exist_ok=True)
    tmp = STATUS_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATUS_STATE_FILE)


def _admin_telegram_ids() -> list[int]:
    """Liefert die Telegram-IDs aller Admins, die den Bot verknüpft haben."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT telegram_id FROM users WHERE is_admin = 1 AND telegram_id IS NOT NULL"
    ).fetchall()
    conn.close()
    ids = [r["telegram_id"] for r in rows]
    if not ids:
        admin_names = [n.strip() for n in os.environ.get("ADMIN_USERNAMES", "").split(",") if n.strip()]
        if admin_names:
            placeholders = ",".join("?" for _ in admin_names)
            conn = get_conn()
            rows = conn.execute(
                f"SELECT telegram_id FROM users WHERE username IN ({placeholders}) AND telegram_id IS NOT NULL",
                admin_names,
            ).fetchall()
            conn.close()
            ids = [r["telegram_id"] for r in rows]
    return ids


async def _send_to_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Sendet eine Nachricht an alle Admin-Telegram-IDs."""
    for tg_id in _admin_telegram_ids():
        try:
            await context.bot.send_message(chat_id=tg_id, text=text)
        except Exception as exc:  # einzelner Fehler darf andere Admins nicht blockieren
            print(f"[Status] Senden an {tg_id} fehlgeschlagen: {exc}", file=sys.stderr)


async def _poll_new_items(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Meldet neue Nutzer und Einträge seit dem letzten Lauf an die Admins."""
    first_run = not os.path.exists(STATUS_STATE_FILE)
    state = _load_status_state()
    last_beer = state.get("last_beer_id", 0)
    last_user = state.get("last_user_id", 0)

    conn = get_conn()
    new_beers = conn.execute(
        """
        SELECT b.id, b.drinking_date, b.amount, b.drink_type, u.username
        FROM beers b
        JOIN users u ON u.id = b.user_id
        WHERE b.id > ?
        ORDER BY b.id ASC
        """,
        (last_beer,),
    ).fetchall()
    new_users = conn.execute(
        "SELECT id, username FROM users WHERE id > ? ORDER BY id ASC",
        (last_user,),
    ).fetchall()
    conn.close()

    if new_beers:
        state["last_beer_id"] = new_beers[-1]["id"]
    if new_users:
        state["last_user_id"] = new_users[-1]["id"]

    if first_run:
        # Beim ersten Start nur den Stand merken, keine Altlasten melden.
        _save_status_state(state)
        return

    for u in new_users:
        await _send_to_admins(
            context,
            f"🆕 Neuer Nutzer registriert: {u['username']}\n"
            "→ Zum Verknüpfen mit dem Bot: /link <username>",
        )
    for b in new_beers:
        label = DRINK_CATALOG.get(b["drink_type"], {}).get("label", b["drink_type"])
        await _send_to_admins(
            context,
            f"🍺 Neuer Eintrag von {b['username']}:\n"
            f"{b['amount']}× {label} am {b['drinking_date']}",
        )

    _save_status_state(state)


async def _send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tägliche Zusammenfassung um 23 Uhr."""
    today = date.today()
    today_iso = today.isoformat()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT b.amount, b.drink_type, b.price_per_unit, u.username
        FROM beers b
        JOIN users u ON u.id = b.user_id
        WHERE b.drinking_date = ?
        """,
        (today_iso,),
    ).fetchall()
    new_users = conn.execute(
        "SELECT username FROM users WHERE date(created_at) = ?",
        (today_iso,),
    ).fetchall()
    conn.close()

    total_drinks = sum(r["amount"] for r in rows)
    total_euros = sum(r["amount"] * r["price_per_unit"] for r in rows)
    beers = sum(r["amount"] for r in rows if r["drink_type"] == "bier")
    radler = sum(r["amount"] for r in rows if r["drink_type"] == "radler")
    cola = sum(r["amount"] for r in rows if r["drink_type"] == "cola")
    wasser = sum(r["amount"] for r in rows if r["drink_type"] == "wasser")

    if total_drinks == 0 and not new_users:
        return  # nichts zu melden

    lines = [f"📊 Tagesübersicht {today_iso}:\n"]
    if total_drinks > 0:
        parts = [f"{total_drinks} Getränke"]
        if beers:
            parts.append(f"🍺 {beers}")
        if radler:
            parts.append(f"🍋 {radler}")
        if cola:
            parts.append(f"🥤 {cola}")
        if wasser:
            parts.append(f"💧 {wasser}")
        lines.append(" | ".join(parts))
        lines.append(f"💰 Umsatz: {total_euros:.2f} €")
    if new_users:
        lines.append(
            f"🆕 Neue Nutzer: {', '.join(u['username'] for u in new_users)}"
        )
    await _send_to_admins(context, "\n".join(lines))


async def _send_monthly_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Monatsübersicht am Monatsende."""
    ms = month_str_today()
    rows = _query_month_overview(ms)
    text = _format_overview(rows, ms)
    await _send_to_admins(context, text)


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
    app.add_handler(CommandHandler("menu",           menu))
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
    app.add_handler(CallbackQueryHandler(button_handler))

    # ── Automatische Statusnachrichten (nur an Admins) ──
    # Tick-Job prüft jede Minute, ob die tägliche/monatliche Meldung fällig ist (Live-Update fähig).
    app.job_queue.run_repeating(_status_tick, interval=60, first=10)
    # Poll-Job prüft auf neue Einträge (Interval benötigt Bot-Neustart).
    app.job_queue.run_repeating(_poll_new_items, interval=_status_poll_seconds(), first=30)

    app.run_polling()


if __name__ == "__main__":
    main()
