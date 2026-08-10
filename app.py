import csv
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from datetime import date, datetime

from flask import (
    Flask, render_template, request, redirect, url_for, session, g, flash, make_response,
    send_file,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_USERNAMES"]
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v, "").strip()]
if _missing:
    print(
        f"[FEHLER] Fehlende Pflicht-Umgebungsvariablen: {', '.join(_missing)}\n"
        "Bitte in der .env auf dem Host setzen. Anwendung wird beendet.",
        file=sys.stderr,
    )
    sys.exit(1)

DRINK_CATALOG = [
    {"key": "bier", "label": "\U0001F37A Bier", "price": 1.50},
    {"key": "radler", "label": "\U0001F34B Radler", "price": 1.50},
    {"key": "cola", "label": "\U0001F964 Cola/Fanta/Mezzo", "price": 1.50},
    {"key": "wasser", "label": "\U0001F4A7 Wasser", "price": 1.00},
]
DRINK_PRICE = {d["key"]: d["price"] for d in DRINK_CATALOG}
DRINK_LABEL = {d["key"]: d["label"] for d in DRINK_CATALOG}

SUPPORTED_LANGUAGES = {"de", "en"}
DEFAULT_LANGUAGE = "de"
SUPPORTED_THEMES = {"dark", "light"}
DEFAULT_THEME = "dark"

ALLOWED_REDIRECT_ENDPOINTS = {
    "index", "login", "register", "about", "dashboard", "summary",
    "admin_dashboard", "admin_report_balances", "profile", "forgot_password",
}

_MOBILE_UA_RE = re.compile(
    r"(android|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile|tablet|"
    r"webos|windows phone|kindle|silk|fennec|symbian|palm|series60)",
    re.IGNORECASE,
)


def detect_mobile():
    ua = request.headers.get("User-Agent", "")
    return bool(_MOBILE_UA_RE.search(ua))


TRANSLATIONS = {
    "app.title": {"de": "VfB Gr\u00f6tzingen - AH Bierk\u00e4ssle", "en": "VfB Gr\u00f6tzingen - AH Beer Cash Box"},
    "nav.about": {"de": "\u00dcber uns", "en": "About"},
    "nav.dashboard": {"de": "Eintragen", "en": "Add entries"},
    "nav.summary": {"de": "Monats\u00fcbersicht", "en": "Monthly summary"},
    "nav.admin": {"de": "\U0001F6E0\uFE0F Admin", "en": "\U0001F6E0\uFE0F Admin"},
    "nav.logout": {"de": "Logout", "en": "Logout"},
    "nav.login": {"de": "Login", "en": "Login"},
    "nav.register": {"de": "Registrieren", "en": "Register"},
    "nav.profile": {"de": "Mein Profil", "en": "My profile"},
    "switch.language": {"de": "Sprache", "en": "Language"},
    "switch.theme": {"de": "Theme", "en": "Theme"},
    "theme.dark": {"de": "Dunkel", "en": "Dark"},
    "theme.light": {"de": "Hell", "en": "Light"},
    "flash.login_required": {"de": "Bitte zuerst einloggen.", "en": "Please log in first."},
    "flash.admin_required": {"de": "Admin-Rechte erforderlich.", "en": "Admin rights required."},
    "flash.empty_username_password": {
        "de": "Benutzername und Passwort d\u00fcrfen nicht leer sein.",
        "en": "Username and password must not be empty.",
    },
    "flash.username_taken": {"de": "Benutzername ist bereits vergeben.", "en": "Username is already taken."},
    "flash.register_success": {"de": "Registrierung erfolgreich. Bitte einloggen.", "en": "Registration successful. Please log in."},
    "flash.login_failed": {"de": "Benutzername oder Passwort falsch.", "en": "Wrong username or password."},
    "flash.welcome": {"de": "Willkommen, {username}!", "en": "Welcome, {username}!"},
    "flash.logout_success": {"de": "Erfolgreich ausgeloggt.", "en": "Successfully logged out."},
    "flash.invalid_amount": {"de": "Bitte eine g\u00fcltige Anzahl eintragen.", "en": "Please enter a valid amount."},
    "flash.entry_saved": {"de": "Eintrag gespeichert.", "en": "Entry saved."},
    "flash.user_not_found": {"de": "User nicht gefunden.", "en": "User not found."},
    "flash.username_empty": {"de": "Benutzername darf nicht leer sein.", "en": "Username must not be empty."},
    "flash.telegram_id_number": {"de": "Telegram-ID muss eine Zahl sein.", "en": "Telegram ID must be a number."},
    "flash.self_remove_admin": {
        "de": "Du kannst dir die eigenen Admin-Rechte nicht entziehen.",
        "en": "You cannot remove your own admin rights.",
    },
    "flash.telegram_id_taken": {
        "de": "Telegram-ID ist bereits einem anderen User zugeordnet.",
        "en": "Telegram ID is already assigned to another user.",
    },
    "flash.user_updated": {"de": "User aktualisiert.", "en": "User updated."},
    "flash.delete_admin_forbidden": {"de": "Admins d\u00fcrfen nicht gel\u00f6scht werden.", "en": "Admins cannot be deleted."},
    "flash.delete_self_forbidden": {"de": "Du kannst dich nicht selbst l\u00f6schen.", "en": "You cannot delete yourself."},
    "flash.user_deleted": {"de": "User '{username}' wurde gel\u00f6scht.", "en": "User '{username}' was deleted."},
    "flash.entry_not_found": {"de": "Eintrag nicht gefunden.", "en": "Entry not found."},
    "flash.entry_updated": {"de": "Eintrag aktualisiert.", "en": "Entry updated."},
    "flash.entry_deleted": {"de": "Eintrag gel\u00f6scht.", "en": "Entry deleted."},
    "flash.entry_permission_denied": {"de": "Keine Berechtigung f\u00fcr diesen Eintrag.", "en": "No permission for this entry."},
    "flash.payment_method_required": {"de": "Bitte eine g\u00fcltige Zahlart w\u00e4hlen.", "en": "Please choose a valid payment method."},
    "flash.payment_updated": {"de": "Zahlstatus aktualisiert.", "en": "Payment status updated."},
    "flash.rate_limit": {
        "de": "Zu viele Versuche. Bitte kurz warten.",
        "en": "Too many attempts. Please wait a moment.",
    },
    "flash.password_changed": {"de": "Passwort erfolgreich ge\u00e4ndert.", "en": "Password changed successfully."},
    "flash.password_current_wrong": {"de": "Aktuelles Passwort ist falsch.", "en": "Current password is incorrect."},
    "flash.password_mismatch": {"de": "Die neuen Passw\u00f6rter stimmen nicht \u00fcberein.", "en": "The new passwords do not match."},
    "flash.password_empty": {"de": "Bitte ein neues Passwort eingeben.", "en": "Please enter a new password."},
    "flash.profile_updated": {"de": "Profil aktualisiert.", "en": "Profile updated."},
    "flash.invalid_email": {"de": "Bitte eine g\u00fcltige E-Mail-Adresse eingeben.", "en": "Please enter a valid email address."},
    "flash.invalid_birthday": {"de": "Bitte ein g\u00fcltiges Geburtsdatum eingeben.", "en": "Please enter a valid birthday."},
    "flash.reset_request_sent": {
        "de": "Deine Anfrage wurde an den Admin gesendet. Du wirst benachrichtigt, sobald ein neues Passwort vergeben wurde.",
        "en": "Your request has been sent to the admin. You will be notified once a new password has been set.",
    },
    "flash.reset_request_username_unknown": {
        "de": "Falls dieser Benutzername existiert, wurde eine Anfrage an den Admin gesendet.",
        "en": "If this username exists, a request has been sent to the admin.",
    },
    "flash.reset_request_resolved": {"de": "Passwort wurde gesetzt und Anfrage geschlossen.", "en": "Password has been set and request closed."},
    "flash.reset_request_not_found": {"de": "Anfrage nicht gefunden.", "en": "Request not found."},
    "flash.bulk_pay_done": {
        "de": "{count} Eintrag/Eintr\u00e4ge f\u00fcr {username} ({ym}) als bezahlt markiert.",
        "en": "{count} entry/entries for {username} ({ym}) marked as paid.",
    },
    "flash.bulk_pay_user_not_found": {
        "de": "User nicht gefunden oder keine Eintr\u00e4ge f\u00fcr diesen Monat.",
        "en": "User not found or no entries for this month.",
    },
    "page.login.title": {"de": "Login", "en": "Login"},
    "page.register.title": {"de": "Registrieren", "en": "Register"},
    "page.about.title": {"de": "\u00dcber uns", "en": "About us"},
    "page.dashboard.title": {"de": "Eintragen", "en": "Add entries"},
    "page.summary.title": {"de": "Monats\u00fcbersicht", "en": "Monthly summary"},
    "page.admin.title": {"de": "Admin-\u00dcbersicht", "en": "Admin overview"},
    "page.admin_edit_user.title": {"de": "User bearbeiten", "en": "Edit user"},
    "page.admin_edit_entry.title": {"de": "Eintrag bearbeiten", "en": "Edit entry"},
    "page.admin_balances.title": {"de": "Offene Betr\u00e4ge", "en": "Open balances"},
    "page.profile.title": {"de": "Mein Profil", "en": "My profile"},
    "page.forgot_password.title": {"de": "Passwort vergessen", "en": "Forgot password"},
    "about.heading": {"de": "\u00dcber uns", "en": "About us"},
    "about.text": {
        "de": "Wir sind einige der wenigen Entwickler, die ihr Bier OHNE KI trinken. DSGVO-konform, Hosting und Bier trinken in Deutschland. Kontakt: vfbah@arbeitermili.eu",
        "en": "We are among the few developers who drink their beer WITHOUT AI. GDPR-compliant, hosting and beer drinking in Germany. Contact: vfbah@arbeitermili.eu",
    },
    "login.heading": {"de": "Login", "en": "Login"},
    "login.submit": {"de": "Einloggen", "en": "Sign in"},
    "login.no_account": {"de": "Noch kein Konto?", "en": "No account yet?"},
    "login.register_link": {"de": "Jetzt registrieren", "en": "Register now"},
    "login.forgot_password_link": {"de": "Passwort vergessen?", "en": "Forgot password?"},
    "login.monthly_status": {"de": "Monatsstand {month} (nur lesen)", "en": "Monthly status {month} (read-only)"},
    "register.heading": {"de": "Registrieren", "en": "Register"},
    "register.submit": {"de": "Konto anlegen", "en": "Create account"},
    "register.has_account": {"de": "Schon ein Konto?", "en": "Already have an account?"},
    "register.login_link": {"de": "Zum Login", "en": "Go to login"},
    "register.hint": {
        "de": "Du brauchst keine E-Mail-Adresse. Bitte w\u00e4hle am besten deinen Klarnamen oder einen passenden Spitznamen als Benutzernamen sowie ein freies Passwort. Der Benutzername kann sp\u00e4ter nur vom Admin ge\u00e4ndert werden.",
        "en": "You don't need an email address. Please choose your real name or a suitable nickname as your username, plus a password of your choice. The username can only be changed by an admin later on.",
    },
    "dashboard.heading": {"de": "Biere eintragen", "en": "Add drinks"},
    "dashboard.info": {
        "de": "Mittwochs nach dem Training hier die Anzahl der getrunkenen Biere eintragen. Ein Bier = {price} \u20ac.",
        "en": "After training on Wednesdays, enter the number of drinks here. One drink = {price} \u20ac.",
    },
    "dashboard.save_entry": {"de": "Eintrag speichern", "en": "Save entry"},
    "dashboard.recent_entries": {"de": "Letzte Eintr\u00e4ge von {username}", "en": "Latest entries from {username}"},
    "summary.heading": {"de": "Monats\u00fcbersicht", "en": "Monthly summary"},
    "summary.info": {
        "de": "Auswertung f\u00fcr {month}.{year} \u2013 ein Bier = {price} \u20ac.",
        "en": "Overview for {month}.{year} \u2013 one drink = {price} \u20ac.",
    },
    "summary.no_entries": {"de": "F\u00fcr diesen Monat liegen noch keine Eintr\u00e4ge vor.", "en": "No entries exist for this month yet."},
    "admin.heading": {"de": "Admin-\u00dcbersicht", "en": "Admin overview"},
    "admin.subtitle": {"de": "Nutzer, Eintr\u00e4ge und Zahlungen im Blick.", "en": "Keep users, entries, and payments in view."},
    "admin.balance_report": {"de": "Offene Betr\u00e4ge / Monatsreport", "en": "Open balances / monthly report"},
    "admin.stats.users": {"de": "Nutzer", "en": "Users"},
    "admin.stats.admins": {"de": "Admins", "en": "Admins"},
    "admin.stats.drinks_total": {"de": "Getr\u00e4nke gesamt", "en": "Total drinks"},
    "admin.stats.latest_entries": {"de": "Letzte Eintr\u00e4ge", "en": "Latest entries"},
    "admin.user_management": {"de": "Nutzerverwaltung", "en": "User management"},
    "admin.export": {"de": "Export", "en": "Export"},
    "admin.export_csv": {"de": "CSV exportieren", "en": "Export CSV"},
    "admin.export_help": {
        "de": "Exportiert alle Eintr\u00e4ge des gew\u00e4hlten Monats als CSV (Spieler, Datum, Anzahl, Getr\u00e4nk, Preis).",
        "en": "Exports all entries of the selected month as CSV (player, date, amount, drink, price).",
    },
    "admin.backup": {"de": "Backups", "en": "Backups"},
    "admin.backup.create": {"de": "Jetzt sichern", "en": "Back up now"},
    "admin.backup.download": {"de": "Download", "en": "Download"},
    "admin.backup.empty": {"de": "Noch keine Backups vorhanden.", "en": "No backups yet."},
    "admin.backup.help": {
        "de": "Automatische Sicherung alle {hours} Stunden, es werden die letzten {keep} Backups behalten.",
        "en": "Automatic backup every {hours} hours, keeping the latest {keep} backups.",
    },
    "admin.backup.created": {"de": "Backup erfolgreich erstellt.", "en": "Backup created successfully."},
    "admin.backup.not_found": {"de": "Backup nicht gefunden.", "en": "Backup not found."},
    "admin.backup.table_date": {"de": "Datum", "en": "Date"},
    "admin.backup.table_size": {"de": "Gr\u00f6\u00dfe", "en": "Size"},
    "admin.backup.table_actions": {"de": "Aktionen", "en": "Actions"},
    "admin.status_settings": {"de": "Telegram Statusmeldungen", "en": "Telegram status messages"},
    "admin.status_settings.daily_time": {"de": "Zeit der Tages-/Monatsmeldung", "en": "Daily/monthly message time"},
    "admin.status_settings.time_hint": {"de": "Format HH:MM, z.B. 23:00", "en": "Format HH:MM, e.g. 23:00"},
    "admin.status_settings.poll_seconds": {"de": "Prüf-Intervall (Sekunden)", "en": "Poll interval (seconds)"},
    "admin.status_settings.poll_hint": {"de": "Min. 5. Wirkung nach Bot-Neustart.", "en": "Min 5. Takes effect after bot restart."},
    "admin.status_settings.save": {"de": "Speichern", "en": "Save"},
    "admin.status_settings.saved": {"de": "Status-Einstellungen gespeichert.", "en": "Status settings saved."},
    "admin.status_settings.invalid": {
        "de": "Ungültige Werte: Zeit als HH:MM, Intervall mindestens 5 s.",
        "en": "Invalid values: time as HH:MM, interval at least 5 s.",
    },
    "admin.latest_entries_global": {"de": "Letzte Eintr\u00e4ge (global)", "en": "Latest entries (global)"},
    "admin.reset_requests": {"de": "Passwort-Anfragen", "en": "Password requests"},
    "admin.reset_requests_empty": {"de": "Keine offenen Passwort-Anfragen.", "en": "No open password requests."},
    "admin.reset_requests_help": {
        "de": "Diese Nutzer haben 'Passwort vergessen?' ausgel\u00f6st. Vergib unten ein neues Passwort.",
        "en": "These users triggered 'Forgot password?'. Set a new password below.",
    },
    "admin.bulk_pay_btn": {"de": "Als bezahlt markieren", "en": "Mark as paid"},
    "admin.bulk_pay_confirm": {
        "de": "Alle offenen Eintr\u00e4ge von {username} im Monat {ym} als bezahlt markieren?",
        "en": "Mark all open entries of {username} in month {ym} as paid?",
    },
    "admin_edit_user.heading": {"de": "User bearbeiten", "en": "Edit user"},
    "admin.back_overview": {"de": "\u2190 Zur\u00fcck zur \u00dcbersicht", "en": "\u2190 Back to overview"},
    "admin_edit_user.password_hint": {"de": "Leer lassen, um Passwort nicht zu \u00e4ndern", "en": "Leave blank to keep password unchanged"},
    "admin_edit_entry.heading": {"de": "Eintrag bearbeiten", "en": "Edit entry"},
    "balances.heading": {"de": "Offene Betr\u00e4ge pro Spieler", "en": "Open balances per player"},
    "balances.subtitle": {
        "de": "\u00dcbersicht aller Monate mit den jeweiligen Biermengen und Euro-Betr\u00e4gen pro Spieler (theoretische Kassensumme).",
        "en": "Overview of all months with drink quantities and euro totals per player (theoretical cash total).",
    },
    "balances.price_hint": {"de": "Ein Bier = {price} \u20ac", "en": "One drink = {price} \u20ac"},
    "balances.month_header": {
        "de": "Monat {ym} \u2014 Gesamt: {total_beers} Bier(e) / {total_euros} \u20ac",
        "en": "Month {ym} \u2014 Total: {total_beers} drink(s) / {total_euros} \u20ac",
    },
    "form.username": {"de": "Benutzername", "en": "Username"},
    "form.password": {"de": "Passwort", "en": "Password"},
    "form.date": {"de": "Datum", "en": "Date"},
    "form.beer_count": {"de": "Anzahl Biere", "en": "Number of drinks"},
    "form.month": {"de": "Monat", "en": "Month"},
    "form.year": {"de": "Jahr", "en": "Year"},
    "form.telegram_id": {"de": "Telegram-ID", "en": "Telegram ID"},
    "form.optional": {"de": "optional", "en": "optional"},
    "form.new_password": {"de": "Neues Passwort", "en": "New password"},
    "form.admin_rights": {"de": "Admin-Rechte", "en": "Admin rights"},
    "form.current_password": {"de": "Aktuelles Passwort", "en": "Current password"},
    "form.new_password_repeat": {"de": "Neues Passwort wiederholen", "en": "Repeat new password"},
    "form.phone": {"de": "Telefonnummer", "en": "Phone number"},
    "form.email": {"de": "E-Mail-Adresse", "en": "Email address"},
    "form.birthday": {"de": "Geburtstag", "en": "Birthday"},
    "action.save": {"de": "Speichern", "en": "Save"},
    "action.cancel": {"de": "Abbrechen", "en": "Cancel"},
    "action.update": {"de": "Aktualisieren", "en": "Update"},
    "action.edit": {"de": "Bearbeiten", "en": "Edit"},
    "action.delete": {"de": "L\u00f6schen", "en": "Delete"},
    "action.change": {"de": "\u00c4ndern", "en": "Change"},
    "action.send_request": {"de": "Anfrage senden", "en": "Send request"},
    "action.set_new_password": {"de": "Neues Passwort setzen", "en": "Set new password"},
    "table.player": {"de": "Spieler", "en": "Player"},
    "table.beers": {"de": "Biere", "en": "Drinks"},
    "table.total": {"de": "Gesamt", "en": "Total"},
    "table.total_row": {"de": "Gesamt", "en": "Total"},
    "table.open": {"de": "Offen", "en": "Open"},
    "table.paid": {"de": "Bezahlt", "en": "Paid"},
    "table.date": {"de": "Datum", "en": "Date"},
    "table.recorded_at": {"de": "Erfasst am", "en": "Recorded at"},
    "table.payment_method": {"de": "Zahlart", "en": "Payment method"},
    "table.no_entries": {"de": "Noch keine Eintr\u00e4ge vorhanden.", "en": "No entries yet."},
    "table.no_entries_yet": {"de": "Es sind noch keine Eintr\u00e4ge vorhanden.", "en": "No entries are available yet."},
    "table.drinks": {"de": "Getr\u00e4nke", "en": "Drinks"},
    "table.total_euro": {"de": "Summe (\u20ac)", "en": "Total (\u20ac)"},
    "table.last_date": {"de": "Letztes Datum", "en": "Last date"},
    "table.role": {"de": "Rolle", "en": "Role"},
    "table.actions": {"de": "Aktionen", "en": "Actions"},
    "table.drink": {"de": "Getr\u00e4nk", "en": "Drink"},
    "table.amount": {"de": "Anzahl", "en": "Amount"},
    "table.payment": {"de": "Zahlung", "en": "Payment"},
    "table.amount_euro": {"de": "Betrag (\u20ac)", "en": "Amount (\u20ac)"},
    "table.requested_at": {"de": "Angefragt am", "en": "Requested at"},
    "role.admin": {"de": "Admin", "en": "Admin"},
    "role.user": {"de": "User", "en": "User"},
    "payment.paid": {"de": "bezahlt", "en": "paid"},
    "payment.open": {"de": "offen", "en": "open"},
    "payment.bar": {"de": "Bar", "en": "Cash"},
    "confirm.delete_user": {"de": "User '{username}' wirklich l\u00f6schen?", "en": "Really delete user '{username}'?"},
    "confirm.delete_entry": {"de": "Eintrag wirklich l\u00f6schen?", "en": "Really delete entry?"},
    "profile.heading": {"de": "Mein Profil", "en": "My profile"},
    "profile.subtitle": {"de": "Benutzername: {username} (nur vom Admin \u00e4nderbar)", "en": "Username: {username} (only changeable by admin)"},
    "profile.optional_data": {"de": "Optionale Kontaktdaten", "en": "Optional contact data"},
    "profile.change_password": {"de": "Passwort \u00e4ndern", "en": "Change password"},
    "forgot_password.heading": {"de": "Passwort vergessen", "en": "Forgot password"},
    "forgot_password.info": {
        "de": "Gib deinen Benutzernamen ein. Der Admin erh\u00e4lt eine interne Anfrage und vergibt dir manuell ein neues Passwort.",
        "en": "Enter your username. The admin will receive an internal request and manually set a new password for you.",
    },
    "forgot_password.back_login": {"de": "\u2190 Zur\u00fcck zum Login", "en": "\u2190 Back to login"},
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.path.join(app.instance_path, "bierkaessle.sqlite3"),
        BEER_PRICE=float(os.environ.get("BEER_PRICE", "1.50")),
        WTF_CSRF_ENABLED=True,
    )
    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    csrf = CSRFProtect(app)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(
                app.config["DATABASE"],
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript(
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
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username_at_request TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by_user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(resolved_by_user_id) REFERENCES users(id)
            );
            """
        )
        try:
            db.execute("ALTER TABLE beers ADD COLUMN drink_type TEXT NOT NULL DEFAULT 'bier'")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE beers ADD COLUMN price_per_unit REAL NOT NULL DEFAULT 1.50")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN birthday DATE")
        except Exception:
            pass
        db.commit()

    with app.app_context():
        init_db()

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

    def is_admin_user(user):
        if user is None:
            return False
        if user["is_admin"]:
            return True
        admin_names = os.environ.get("ADMIN_USERNAMES", "").split(",")
        admin_names = [n.strip() for n in admin_names if n.strip()]
        return user["username"] in admin_names

    def get_language():
        lang = session.get("lang", DEFAULT_LANGUAGE)
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        session["lang"] = lang
        return lang

    def get_theme():
        theme = session.get("theme", DEFAULT_THEME)
        if theme not in SUPPORTED_THEMES:
            theme = DEFAULT_THEME
        session["theme"] = theme
        return theme

    def translate(key, **kwargs):
        lang = get_language()
        text_map = TRANSLATIONS.get(key, {})
        text = text_map.get(lang) or text_map.get(DEFAULT_LANGUAGE) or key
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    def flash_i18n(key, category="info", **kwargs):
        flash({"key": key, "kwargs": kwargs}, category)

    def resolve_next_endpoint(candidate):
        if candidate not in ALLOWED_REDIRECT_ENDPOINTS:
            return url_for("index")
        return url_for(candidate)

    def translate_flash_message(message):
        if isinstance(message, dict) and message.get("key"):
            kwargs = message.get("kwargs") if isinstance(message.get("kwargs"), dict) else {}
            return translate(message["key"], **kwargs)
        return str(message)

    def open_reset_request_count():
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) AS c FROM password_reset_requests WHERE status = 'open'"
        ).fetchone()
        return row["c"] if row else 0

    # ──────────────────────────── Telegram Status-Einstellungen ────────────────────────────
    STATUS_CONFIG_FILE = os.path.join(app.instance_path, "status_config.json")

    def _valid_poll_seconds(value: object) -> float:
        """Liefert poll_seconds als endlicher Wert >= 5, sonst 30."""
        try:
            poll = float(value)
            if poll >= 5 and math.isfinite(poll):
                return poll
        except (ValueError, TypeError):
            pass
        print("[Status] Ungültiges STATUS_POLL_SECONDS, verwende 30s", file=sys.stderr)
        return 30.0

    def load_status_config() -> dict:
        try:
            with open(STATUS_CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data["poll_seconds"] = _valid_poll_seconds(data.get("poll_seconds", 30))
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # Fallback: Env-Vars, sonst Defaults
        return {
            "daily_time": os.environ.get("STATUS_DAILY_TIME", "23:00"),
            "poll_seconds": _valid_poll_seconds(os.environ.get("STATUS_POLL_SECONDS", "30")),
        }

    def save_status_config(daily_time: str, poll_seconds: str) -> bool:
        hh, mm = None, None
        try:
            hh, mm = (int(p) for p in daily_time.split(":"))
            valid_time = 0 <= hh <= 23 and 0 <= mm <= 59
        except (ValueError, TypeError):
            valid_time = False
        try:
            poll = float(poll_seconds)
            valid_poll = poll >= 5 and math.isfinite(poll)
        except (ValueError, TypeError):
            valid_poll = False
        if not (valid_time and valid_poll):
            return False
        os.makedirs(app.instance_path, exist_ok=True)
        tmp = STATUS_CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"daily_time": f"{hh:02d}:{mm:02d}", "poll_seconds": poll}, fh)
        os.replace(tmp, STATUS_CONFIG_FILE)
        return True

    # ──────────────────────────── Backups ────────────────────────────
    BACKUP_DIR = os.path.join(app.instance_path, "backups")
    BACKUP_INTERVAL_SECONDS = float(os.environ.get("BACKUP_INTERVAL_HOURS", "24")) * 3600
    BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "10"))

    def _backup_dir_ready():
        os.makedirs(BACKUP_DIR, exist_ok=True)
        return BACKUP_DIR

    def create_backup():
        """Erstellt eine konsistente SQLite-Kopie mit aktuellem WAL-Bestand."""
        _backup_dir_ready()
        src = app.config["DATABASE"]
        if not os.path.exists(src):
            return None
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"bierkaessle-{ts}.sqlite3")
        try:
            sconn = sqlite3.connect(src)
            dconn = sqlite3.connect(dest)
            try:
                sconn.backup(dconn)
            finally:
                dconn.close()
                sconn.close()
        except Exception:
            if os.path.exists(dest):
                os.remove(dest)
            return None
        return dest

    def list_backups():
        """Liefert (filename, size_bytes, mtime) absteigend nach Zeit."""
        _backup_dir_ready()
        entries = []
        for fn in os.listdir(BACKUP_DIR):
            if not fn.startswith("bierkaessle-") or not fn.endswith(".sqlite3"):
                continue
            fp = os.path.join(BACKUP_DIR, fn)
            try:
                st = os.stat(fp)
                entries.append((fn, st.st_size, st.st_mtime))
            except OSError:
                continue
        entries.sort(key=lambda e: e[2], reverse=True)
        return entries

    def cleanup_old_backups():
        """Entfernt Backups, die über BACKUP_KEEP hinausgehen."""
        backups = list_backups()
        for fn, _, _ in backups[BACKUP_KEEP:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, fn))
            except OSError:
                pass

    def _start_backup_worker():
        # Nicht im Test-Modus starten, damit Tests deterministisch bleiben
        if app.config.get("TESTING"):
            return

        def _run():
            while not app.config.get("BACKUP_STOP"):
                time.sleep(BACKUP_INTERVAL_SECONDS)
                try:
                    with app.app_context():
                        created = create_backup()
                        if created:
                            cleanup_old_backups()
                except Exception as exc:
                    print(f"[Backup] Fehler: {exc}", file=sys.stderr)

        thread = threading.Thread(target=_run, daemon=True, name="backup-worker")
        thread.start()
        app.config["BACKUP_THREAD"] = thread

    _start_backup_worker()
    cleanup_old_backups()

    @app.context_processor
    def inject_globals():
        user = current_user()
        admin_flag = is_admin_user(user)
        return {
            "current_user_obj": user,
            "is_admin": admin_flag,
            "is_mobile": detect_mobile(),
            "drink_catalog": DRINK_CATALOG,
            "drink_label": DRINK_LABEL,
            "t": translate,
            "tf": translate_flash_message,
            "current_lang": get_language(),
            "current_theme": get_theme(),
            "session_theme_defined": "theme" in session,
            "supported_languages": sorted(SUPPORTED_LANGUAGES),
            "supported_themes": sorted(SUPPORTED_THEMES),
            "open_reset_requests_count": open_reset_request_count() if admin_flag else 0,
            "backup_dir": BACKUP_DIR,
            "backup_interval_hours": int(BACKUP_INTERVAL_SECONDS // 3600),
            "backup_keep": BACKUP_KEEP,
            "status_settings": load_status_config(),
                        "datetime": datetime,
        }

    def login_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                flash_i18n("flash.login_required", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    def admin_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not is_admin_user(user):
                flash_i18n("flash.admin_required", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    @app.errorhandler(429)
    def ratelimit_handler(e):
        flash_i18n("flash.rate_limit", "danger")
        return redirect(url_for("login")), 429

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or not password:
                flash_i18n("flash.empty_username_password", "danger")
                return render_template("register.html")

            db = get_db()
            is_first_user = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
            is_admin_val = 1 if is_first_user else 0

            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), is_admin_val),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash_i18n("flash.username_taken", "danger")
                return render_template("register.html")

            flash_i18n("flash.register_success", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

            if user is None or not check_password_hash(user["password_hash"], password):
                flash_i18n("flash.login_failed", "danger")
                return render_template("login.html", **_login_context())

            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash_i18n("flash.welcome", "success", username=user["username"])
            return redirect(url_for("dashboard"))
        return render_template("login.html", **_login_context())

    def _login_context():
        db = get_db()
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"
        rows = db.execute(
            """
            SELECT u.username,
                   COALESCE(SUM(b.amount), 0) AS total_drinks,
                   COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros,
                   COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=1 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS paid_euros,
                   COALESCE(SUM(CASE WHEN COALESCE(p.is_paid,0)=0 THEN b.amount * b.price_per_unit ELSE 0 END), 0) AS open_euros
            FROM users u
            LEFT JOIN beers b ON u.id = b.user_id AND strftime('%Y-%m', b.drinking_date) = ?
            LEFT JOIN payments p ON p.beer_id = b.id
            WHERE u.is_admin = 0
            GROUP BY u.id
            HAVING total_drinks > 0
            ORDER BY total_euros DESC
            """,
            (month_str,),
        ).fetchall()

        summary = []
        for r in rows:
            summary.append({
                "username": r["username"],
                "beers": r["total_drinks"],
                "total": round(r["total_euros"], 2),
                "paid": round(r["paid_euros"], 2),
                "open": round(r["open_euros"], 2),
            })

        return {
            "monthly_summary": summary,
            "month_label": today.strftime("%B %Y"),
            "beer_price": app.config["BEER_PRICE"],
        }

    @app.route("/forgot-password", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def forgot_password():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user is not None:
                existing = db.execute(
                    "SELECT id FROM password_reset_requests WHERE user_id = ? AND status = 'open'",
                    (user["id"],),
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO password_reset_requests (user_id, username_at_request, status) VALUES (?, ?, 'open')",
                        (user["id"], user["username"]),
                    )
                    db.commit()
            flash_i18n("flash.reset_request_username_unknown", "info")
            return redirect(url_for("login"))
        return render_template("forgot_password.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash_i18n("flash.logout_success", "info")
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        if current_user() is None:
            return redirect(url_for("login"))
        return redirect(url_for("dashboard"))

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/set-language", methods=["POST"])
    def set_language():
        lang = request.form.get("lang", DEFAULT_LANGUAGE)
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        session["lang"] = lang
        next_endpoint = request.form.get("next_endpoint", "index")
        return redirect(resolve_next_endpoint(next_endpoint))

    @app.route("/set-theme", methods=["POST"])
    def set_theme():
        theme = request.form.get("theme", DEFAULT_THEME)
        if theme not in SUPPORTED_THEMES:
            theme = DEFAULT_THEME
        session["theme"] = theme
        next_endpoint = request.form.get("next_endpoint", "index")
        return redirect(resolve_next_endpoint(next_endpoint))

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_required
    def dashboard():
        db = get_db()
        user = current_user()

        if request.method == "POST":
            amount_raw = request.form.get("amount", "0")
            date_raw = request.form.get("drinking_date") or str(date.today())
            drink_type = request.form.get("drink_type", "bier")
            if drink_type not in DRINK_PRICE:
                drink_type = "bier"
            price = DRINK_PRICE[drink_type]

            try:
                amount = int(amount_raw)
            except ValueError:
                amount = 0

            if amount <= 0:
                flash_i18n("flash.invalid_amount", "danger")
            else:
                db.execute(
                    "INSERT INTO beers (user_id, drinking_date, amount, drink_type, price_per_unit) VALUES (?, ?, ?, ?, ?)",
                    (user["id"], date_raw, amount, drink_type, price),
                )
                db.commit()
                flash_i18n("flash.entry_saved", "success")
            return redirect(url_for("dashboard"))

        entries = db.execute(
            """
            SELECT b.id, b.drinking_date, b.amount, b.drink_type, b.price_per_unit, b.created_at,
                   COALESCE(p.is_paid, 0) AS is_paid, p.method AS payment_method
            FROM beers b
            LEFT JOIN payments p ON p.beer_id = b.id
            WHERE b.user_id = ?
            ORDER BY b.drinking_date DESC, b.created_at DESC
            LIMIT 20
            """,
            (user["id"],),
        ).fetchall()

        return render_template(
            "dashboard.html",
            user=user,
            entries=entries,
            today=date.today(),
            beer_price=app.config["BEER_PRICE"],
            drink_catalog=DRINK_CATALOG,
            drink_label=DRINK_LABEL,
        )

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        db = get_db()
        user = current_user()

        if request.method == "POST":
            form_type = request.form.get("form_type", "")

            if form_type == "contact_data":
                phone = request.form.get("phone", "").strip() or None
                email = request.form.get("email", "").strip() or None
                birthday_raw = request.form.get("birthday", "").strip()
                birthday = None

                if email:
                    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                        flash_i18n("flash.invalid_email", "danger")
                        return redirect(url_for("profile"))

                if birthday_raw:
                    try:
                        datetime.strptime(birthday_raw, "%Y-%m-%d")
                        birthday = birthday_raw
                    except ValueError:
                        flash_i18n("flash.invalid_birthday", "danger")
                        return redirect(url_for("profile"))

                db.execute(
                    "UPDATE users SET phone = ?, email = ?, birthday = ? WHERE id = ?",
                    (phone, email, birthday, user["id"]),
                )
                db.commit()
                flash_i18n("flash.profile_updated", "success")
                return redirect(url_for("profile"))

            if form_type == "change_password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                new_password_repeat = request.form.get("new_password_repeat", "")

                if not check_password_hash(user["password_hash"], current_password):
                    flash_i18n("flash.password_current_wrong", "danger")
                    return redirect(url_for("profile"))

                if not new_password:
                    flash_i18n("flash.password_empty", "danger")
                    return redirect(url_for("profile"))

                if new_password != new_password_repeat:
                    flash_i18n("flash.password_mismatch", "danger")
                    return redirect(url_for("profile"))

                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), user["id"]),
                )
                db.commit()
                flash_i18n("flash.password_changed", "success")
                return redirect(url_for("profile"))

            return redirect(url_for("profile"))

        user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return render_template("profile.html", user=user)

    @app.route("/summary")
    @login_required
    def summary():
        db = get_db()
        user = current_user()
        year = request.args.get("year")
        month = request.args.get("month")
        today = date.today()

        try:
            year = int(year) if year else today.year
            month = int(month) if month else today.month
        except ValueError:
            year, month = today.year, today.month

        month_str = f"{year:04d}-{month:02d}"
        admin_filter = "" if is_admin_user(user) else "WHERE u.is_admin = 0"
        rows = db.execute(
            f"""
            SELECT u.username,
                   COALESCE(SUM(b.amount), 0) AS total_drinks,
                   COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros
            FROM users u
            LEFT JOIN beers b ON u.id = b.user_id AND strftime('%Y-%m', b.drinking_date) = ?
            {admin_filter}
            GROUP BY u.id
            ORDER BY u.username
            """,
            (month_str,),
        ).fetchall()

        summary_data = []
        total_drinks = 0
        total_euros = 0.0
        for row in rows:
            drinks = row["total_drinks"] or 0
            euros = row["total_euros"] or 0.0
            total_drinks += drinks
            total_euros += euros
            summary_data.append({"username": row["username"], "beers": drinks, "euros": round(euros, 2)})

        return render_template(
            "summary.html",
            summary_data=summary_data,
            beer_price=app.config["BEER_PRICE"],
            total_beers=total_drinks,
            total_euros=round(total_euros, 2),
            year=year,
            month=month,
        )

    @app.route("/admin")
    @login_required
    @admin_required
    def admin_dashboard():
        db = get_db()
        beer_price = app.config["BEER_PRICE"]

        users_stats = db.execute(
            """
            SELECT u.id, u.username, u.telegram_id, u.is_admin, u.phone, u.email, u.birthday,
                   COALESCE(SUM(b.amount), 0) AS beers, MAX(b.drinking_date) AS last_date
            FROM users u
            LEFT JOIN beers b ON u.id = b.user_id
            GROUP BY u.id
            ORDER BY u.username
            """
        ).fetchall()

        recent_entries = db.execute(
            """
            SELECT b.id, b.drinking_date, b.amount, b.drink_type, b.price_per_unit, b.created_at,
                   u.username, COALESCE(p.is_paid, 0) AS is_paid, p.method AS payment_method
            FROM beers b
            JOIN users u ON u.id = b.user_id
            LEFT JOIN payments p ON p.beer_id = b.id
            ORDER BY b.drinking_date DESC, b.created_at DESC
            LIMIT 50
            """
        ).fetchall()

        reset_requests = db.execute(
            """
            SELECT r.id, r.username_at_request, r.requested_at, u.id AS user_id
            FROM password_reset_requests r
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'open'
            ORDER BY r.requested_at ASC
            """
        ).fetchall()

        return render_template(
            "admin_dashboard.html",
            users_stats=users_stats,
            recent_entries=recent_entries,
            beer_price=beer_price,
            drink_label=DRINK_LABEL,
            reset_requests=reset_requests,
            backups=list_backups(),
        )

    @app.route("/admin/backup/create", methods=["POST"])
    @login_required
    @admin_required
    def admin_backup_create():
        created = create_backup()
        if created:
            cleanup_old_backups()
            flash_i18n("admin.backup.created", "success")
        else:
            flash_i18n("admin.backup.not_found", "danger")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/backup/download/<path:filename>")
    @login_required
    @admin_required
    def admin_backup_download(filename):
        # Nur Dateinamen aus dem Backup-Verzeichnis zulassen (kein Pfad-Traversal)
        backup_names = {fn for fn, _, _ in list_backups()}
        if filename not in backup_names:
            flash_i18n("admin.backup.not_found", "danger")
            return redirect(url_for("admin_dashboard"))
        return send_file(
            os.path.join(BACKUP_DIR, filename),
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/admin/status-settings", methods=["POST"])
    @login_required
    @admin_required
    def admin_status_settings():
        if save_status_config(
            request.form.get("daily_time", ""),
            request.form.get("poll_seconds", ""),
        ):
            flash_i18n("admin.status_settings.saved", "success")
        else:
            flash_i18n("admin.status_settings.invalid", "danger")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/reset-request/<int:request_id>/resolve", methods=["POST"])
    @login_required
    @admin_required
    def admin_resolve_reset_request(request_id):
        db = get_db()
        admin_user = current_user()
        req = db.execute(
            "SELECT * FROM password_reset_requests WHERE id = ? AND status = 'open'",
            (request_id,),
        ).fetchone()

        if req is None:
            flash_i18n("flash.reset_request_not_found", "warning")
            return redirect(url_for("admin_dashboard"))

        new_password = request.form.get("new_password", "")
        if not new_password:
            flash_i18n("flash.password_empty", "danger")
            return redirect(url_for("admin_dashboard"))

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), req["user_id"]),
        )
        db.execute(
            "UPDATE password_reset_requests SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = ? WHERE id = ?",
            (admin_user["id"], request_id),
        )
        db.commit()
        flash_i18n("flash.reset_request_resolved", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/user/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_edit_user(user_id):
        db = get_db()
        admin_user = current_user()
        user = db.execute(
            "SELECT id, username, telegram_id, is_admin, phone, email, birthday, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if user is None:
            flash_i18n("flash.user_not_found", "warning")
            return redirect(url_for("admin_dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            telegram_id_raw = request.form.get("telegram_id", "").strip()
            new_password = request.form.get("new_password", "")
            is_admin_checked = 1 if request.form.get("is_admin") == "on" else 0
            phone = request.form.get("phone", "").strip() or None
            email = request.form.get("email", "").strip() or None
            birthday = request.form.get("birthday", "").strip() or None

            if not username:
                flash_i18n("flash.username_empty", "danger")
                return render_template("admin_edit_user.html", edit_user=user)

            telegram_id = None
            if telegram_id_raw:
                try:
                    telegram_id = int(telegram_id_raw)
                except ValueError:
                    flash_i18n("flash.telegram_id_number", "danger")
                    return render_template("admin_edit_user.html", edit_user=user)

            if user["id"] == admin_user["id"] and is_admin_checked == 0:
                flash_i18n("flash.self_remove_admin", "danger")
                return render_template("admin_edit_user.html", edit_user=user)

            duplicate = db.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id)
            ).fetchone()
            if duplicate:
                flash_i18n("flash.username_taken", "danger")
                return render_template("admin_edit_user.html", edit_user=user)

            if telegram_id is not None:
                duplicate_tg = db.execute(
                    "SELECT id FROM users WHERE telegram_id = ? AND id != ?", (telegram_id, user_id)
                ).fetchone()
                if duplicate_tg:
                    flash_i18n("flash.telegram_id_taken", "danger")
                    return render_template("admin_edit_user.html", edit_user=user)

            db.execute(
                "UPDATE users SET username = ?, telegram_id = ?, is_admin = ?, phone = ?, email = ?, birthday = ? WHERE id = ?",
                (username, telegram_id, is_admin_checked, phone, email, birthday, user_id),
            )

            if new_password:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), user_id),
                )

            db.commit()
            flash_i18n("flash.user_updated", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_edit_user.html", edit_user=user)

    @app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_user(user_id):
        db = get_db()
        admin_user = current_user()
        user = db.execute("SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()

        if user is None:
            flash_i18n("flash.user_not_found", "warning")
            return redirect(url_for("admin_dashboard"))

        if user["is_admin"]:
            flash_i18n("flash.delete_admin_forbidden", "danger")
            return redirect(url_for("admin_dashboard"))

        if user["id"] == admin_user["id"]:
            flash_i18n("flash.delete_self_forbidden", "danger")
            return redirect(url_for("admin_dashboard"))

        db.execute(
            "DELETE FROM payments WHERE beer_id IN (SELECT id FROM beers WHERE user_id = ?)", (user_id,)
        )
        db.execute("DELETE FROM beers WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM password_reset_requests WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        flash_i18n("flash.user_deleted", "info", username=user["username"])
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/entry/<int:entry_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_edit_entry(entry_id):
        db = get_db()
        entry = db.execute(
            """
            SELECT b.id, b.drinking_date, b.amount, b.drink_type, b.price_per_unit, u.username
            FROM beers b JOIN users u ON u.id = b.user_id
            WHERE b.id = ?
            """,
            (entry_id,),
        ).fetchone()

        if entry is None:
            flash_i18n("flash.entry_not_found", "warning")
            return redirect(url_for("admin_dashboard"))

        if request.method == "POST":
            amount_raw = request.form.get("amount", "0")
            date_raw = request.form.get("drinking_date") or str(date.today())
            drink_type = request.form.get("drink_type", "bier")
            if drink_type not in DRINK_PRICE:
                drink_type = "bier"
            price = DRINK_PRICE[drink_type]

            try:
                amount = int(amount_raw)
            except ValueError:
                amount = 0

            if amount <= 0:
                flash_i18n("flash.invalid_amount", "danger")
            else:
                db.execute(
                    "UPDATE beers SET amount = ?, drinking_date = ?, drink_type = ?, price_per_unit = ? WHERE id = ?",
                    (amount, date_raw, drink_type, price, entry_id),
                )
                db.commit()
                flash_i18n("flash.entry_updated", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_edit_entry.html", entry=entry, drink_catalog=DRINK_CATALOG)

    @app.route("/admin/entry/<int:entry_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_entry(entry_id):
        db = get_db()
        db.execute("DELETE FROM beers WHERE id = ?", (entry_id,))
        db.commit()
        flash_i18n("flash.entry_deleted", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/export/month")
    @login_required
    @admin_required
    def admin_export_month():
        db = get_db()
        today = date.today()
        year = request.args.get("year") or today.year
        month = request.args.get("month") or today.month

        try:
            year = int(year)
            month = int(month)
        except ValueError:
            year, month = today.year, today.month

        month_str = f"{year:04d}-{month:02d}"
        rows = db.execute(
            """
            SELECT u.username, b.drinking_date, b.amount, b.drink_type, b.price_per_unit
            FROM beers b JOIN users u ON u.id = b.user_id
            WHERE strftime('%Y-%m', b.drinking_date) = ?
            ORDER BY u.username, b.drinking_date
            """,
            (month_str,),
        ).fetchall()

        output = [["username", "date", "amount", "drink_type", "price_per_unit", "total"]]
        for r in rows:
            output.append([
                r["username"], r["drinking_date"], r["amount"], r["drink_type"], r["price_per_unit"],
                round(r["amount"] * r["price_per_unit"], 2)
            ])

        csv_lines = [",".join(str(col) for col in row) for row in output]
        csv_data = "\n".join(csv_lines)

        response = make_response(csv_data)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename=bierkaessle_{year}_{month:02d}.csv"
        return response

    @app.route("/admin/report/balances")
    @login_required
    @admin_required
    def admin_report_balances():
        db = get_db()
        rows = db.execute(
            """
            SELECT u.username AS username, strftime('%Y-%m', b.drinking_date) AS ym,
                   COALESCE(SUM(b.amount), 0) AS total_drinks,
                   COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros
            FROM users u JOIN beers b ON u.id = b.user_id
            GROUP BY u.username, ym
            ORDER BY ym DESC, u.username
            """
        ).fetchall()

        data_drinks, data_euros, months = {}, {}, []
        for r in rows:
            ym = r["ym"]
            if ym not in data_drinks:
                data_drinks[ym] = {}
                data_euros[ym] = {}
                months.append(ym)
            data_drinks[ym][r["username"]] = r["total_drinks"]
            data_euros[ym][r["username"]] = r["total_euros"]

        users = [r["username"] for r in db.execute("SELECT username FROM users ORDER BY username").fetchall()]

        month_rows = []
        for ym in months:
            entries = []
            total_drinks = 0
            total_euros = 0.0
            for username in users:
                drinks = data_drinks.get(ym, {}).get(username, 0)
                euros = data_euros.get(ym, {}).get(username, 0.0)
                total_drinks += drinks
                total_euros += euros
                entries.append({"username": username, "beers": drinks, "euros": round(euros, 2)})
            month_rows.append({
                "ym": ym, "entries": entries,
                "total_beers": total_drinks, "total_euros": round(total_euros, 2),
            })

        return render_template(
            "admin_report_balances.html",
            month_rows=month_rows, users=users, beer_price=app.config["BEER_PRICE"],
        )

    @app.route("/admin/bulk-pay", methods=["POST"])
    @login_required
    @admin_required
    def admin_bulk_pay():
        db = get_db()
        admin_user = current_user()
        username = request.form.get("username", "").strip()
        ym = request.form.get("ym", "").strip()
        method = request.form.get("method", "").strip()

        if method not in ("BAR", "PAYPAL"):
            flash_i18n("flash.payment_method_required", "danger")
            return redirect(url_for("admin_report_balances"))

        target_user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if target_user is None:
            flash_i18n("flash.bulk_pay_user_not_found", "warning")
            return redirect(url_for("admin_report_balances"))

        beer_ids = db.execute(
            """
            SELECT b.id FROM beers b
            LEFT JOIN payments p ON p.beer_id = b.id
            WHERE b.user_id = ?
              AND strftime('%Y-%m', b.drinking_date) = ?
              AND COALESCE(p.is_paid, 0) = 0
            """,
            (target_user["id"], ym),
        ).fetchall()

        if not beer_ids:
            flash_i18n("flash.bulk_pay_user_not_found", "warning")
            return redirect(url_for("admin_report_balances"))

        for row in beer_ids:
            db.execute(
                """
                INSERT INTO payments (beer_id, is_paid, method, marked_by_user_id)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(beer_id) DO UPDATE SET
                    is_paid = 1,
                    method = excluded.method,
                    marked_by_user_id = excluded.marked_by_user_id,
                    marked_at = CURRENT_TIMESTAMP
                """,
                (row["id"], method, admin_user["id"]),
            )
        db.commit()

        flash_i18n("flash.bulk_pay_done", "success", count=len(beer_ids), username=username, ym=ym)
        return redirect(url_for("admin_report_balances"))

    @app.route("/entry/<int:entry_id>/payment", methods=["POST"])
    @login_required
    def update_payment(entry_id):
        db = get_db()
        user = current_user()
        entry = db.execute("SELECT b.id, b.user_id FROM beers b WHERE b.id = ?", (entry_id,)).fetchone()

        if entry is None:
            flash_i18n("flash.entry_not_found", "warning")
            return redirect(url_for("dashboard"))

        if (entry["user_id"] != user["id"]) and (not is_admin_user(user)):
            flash_i18n("flash.entry_permission_denied", "danger")
            return redirect(url_for("dashboard"))

        is_paid = 1 if request.form.get("is_paid") == "on" else 0
        method = request.form.get("method") or None

        if is_paid and method not in ("BAR", "PAYPAL"):
            flash_i18n("flash.payment_method_required", "danger")
            return redirect(request.referrer or url_for("dashboard"))

        db.execute(
            """
            INSERT INTO payments (beer_id, is_paid, method, marked_by_user_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(beer_id) DO UPDATE SET
                is_paid = excluded.is_paid,
                method = excluded.method,
                marked_by_user_id = excluded.marked_by_user_id,
                marked_at = CURRENT_TIMESTAMP
            """,
            (entry_id, is_paid, method, user["id"]),
        )
        db.commit()
        flash_i18n("flash.payment_updated", "success")
        return redirect(request.referrer or url_for("dashboard"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "1904")), debug=False)
