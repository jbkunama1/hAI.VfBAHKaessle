import csv
import os
import sqlite3
from datetime import date

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    g,
    flash,
    make_response,
)
from werkzeug.security import generate_password_hash, check_password_hash

# ──────────────────────────── Getränke-Katalog ────────────────────────────
DRINK_CATALOG = [
    {"key": "bier",   "label": "🍺 Bier",           "price": 1.50},
    {"key": "radler", "label": "🍋 Radler",          "price": 1.50},
    {"key": "cola",   "label": "🥤 Cola/Fanta/Mezzo", "price": 1.50},
    {"key": "wasser", "label": "💧 Wasser",           "price": 1.00},
]
DRINK_PRICE = {d["key"]: d["price"] for d in DRINK_CATALOG}
DRINK_LABEL = {d["key"]: d["label"] for d in DRINK_CATALOG}

SUPPORTED_LANGUAGES = {"de", "en"}
DEFAULT_LANGUAGE = "de"

SUPPORTED_THEMES = {"dark", "light"}
DEFAULT_THEME = "dark"
ALLOWED_REDIRECT_ENDPOINTS = {
    "index",
    "login",
    "register",
    "about",
    "dashboard",
    "summary",
    "admin_dashboard",
    "admin_report_balances",
}

TRANSLATIONS = {
    "app.title": {
        "de": "VfB Grötzingen - AH Bierkässle",
        "en": "VfB Grötzingen - AH Beer Cash Box",
    },
    "nav.about": {"de": "Über uns", "en": "About"},
    "nav.dashboard": {"de": "Eintragen", "en": "Add entries"},
    "nav.summary": {"de": "Monatsübersicht", "en": "Monthly summary"},
    "nav.admin": {"de": "🛠️ Admin", "en": "🛠️ Admin"},
    "nav.logout": {"de": "Logout", "en": "Logout"},
    "nav.login": {"de": "Login", "en": "Login"},
    "nav.register": {"de": "Registrieren", "en": "Register"},
    "switch.language": {"de": "Sprache", "en": "Language"},
    "switch.theme": {"de": "Theme", "en": "Theme"},
    "theme.dark": {"de": "Dunkel", "en": "Dark"},
    "theme.light": {"de": "Hell", "en": "Light"},
    "flash.login_required": {"de": "Bitte zuerst einloggen.", "en": "Please log in first."},
    "flash.admin_required": {"de": "Admin-Rechte erforderlich.", "en": "Admin rights required."},
    "flash.empty_username_password": {
        "de": "Benutzername und Passwort dürfen nicht leer sein.",
        "en": "Username and password must not be empty.",
    },
    "flash.username_taken": {"de": "Benutzername ist bereits vergeben.", "en": "Username is already taken."},
    "flash.register_success": {"de": "Registrierung erfolgreich. Bitte einloggen.", "en": "Registration successful. Please log in."},
    "flash.login_failed": {"de": "Benutzername oder Passwort falsch.", "en": "Wrong username or password."},
    "flash.welcome": {"de": "Willkommen, {username}!", "en": "Welcome, {username}!"},
    "flash.logout_success": {"de": "Erfolgreich ausgeloggt.", "en": "Successfully logged out."},
    "flash.invalid_amount": {"de": "Bitte eine gültige Anzahl eintragen.", "en": "Please enter a valid amount."},
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
    "flash.delete_admin_forbidden": {"de": "Admins dürfen nicht gelöscht werden.", "en": "Admins cannot be deleted."},
    "flash.delete_self_forbidden": {"de": "Du kannst dich nicht selbst löschen.", "en": "You cannot delete yourself."},
    "flash.user_deleted": {"de": "User '{username}' wurde gelöscht.", "en": "User '{username}' was deleted."},
    "flash.entry_not_found": {"de": "Eintrag nicht gefunden.", "en": "Entry not found."},
    "flash.entry_updated": {"de": "Eintrag aktualisiert.", "en": "Entry updated."},
    "flash.entry_deleted": {"de": "Eintrag gelöscht.", "en": "Entry deleted."},
    "flash.entry_permission_denied": {"de": "Keine Berechtigung für diesen Eintrag.", "en": "No permission for this entry."},
    "flash.payment_method_required": {"de": "Bitte eine gültige Zahlart wählen.", "en": "Please choose a valid payment method."},
    "flash.payment_updated": {"de": "Zahlstatus aktualisiert.", "en": "Payment status updated."},
    "page.login.title": {"de": "Login", "en": "Login"},
    "page.register.title": {"de": "Registrieren", "en": "Register"},
    "page.about.title": {"de": "Über uns", "en": "About us"},
    "page.dashboard.title": {"de": "Eintragen", "en": "Add entries"},
    "page.summary.title": {"de": "Monatsübersicht", "en": "Monthly summary"},
    "page.admin.title": {"de": "Admin-Übersicht", "en": "Admin overview"},
    "page.admin_edit_user.title": {"de": "User bearbeiten", "en": "Edit user"},
    "page.admin_edit_entry.title": {"de": "Eintrag bearbeiten", "en": "Edit entry"},
    "page.admin_balances.title": {"de": "Offene Beträge", "en": "Open balances"},
    "about.heading": {"de": "Über uns", "en": "About us"},
    "about.text": {
        "de": "Wir sind einige der wenigen Entwickler, die ihr Bier OHNE KI trinken. DSGVO-konform, Hosting und Bier trinken in Deutschland. Kontakt: vfbah@arbeitermili.eu",
        "en": "We are among the few developers who drink their beer WITHOUT AI. GDPR-compliant, hosting and beer drinking in Germany. Contact: vfbah@arbeitermili.eu",
    },
    "login.heading": {"de": "Login", "en": "Login"},
    "login.submit": {"de": "Einloggen", "en": "Sign in"},
    "login.no_account": {"de": "Noch kein Konto?", "en": "No account yet?"},
    "login.register_link": {"de": "Jetzt registrieren", "en": "Register now"},
    "login.monthly_status": {"de": "Monatsstand {month} (nur lesen)", "en": "Monthly status {month} (read-only)"},
    "register.heading": {"de": "Registrieren", "en": "Register"},
    "register.submit": {"de": "Konto anlegen", "en": "Create account"},
    "register.has_account": {"de": "Schon ein Konto?", "en": "Already have an account?"},
    "register.login_link": {"de": "Zum Login", "en": "Go to login"},
    "dashboard.heading": {"de": "Biere eintragen", "en": "Add drinks"},
    "dashboard.info": {
        "de": "Mittwochs nach dem Training hier die Anzahl der getrunkenen Biere eintragen. Ein Bier = {price} €.",
        "en": "After training on Wednesdays, enter the number of drinks here. One drink = {price} €.",
    },
    "dashboard.save_entry": {"de": "Eintrag speichern", "en": "Save entry"},
    "dashboard.recent_entries": {"de": "Letzte Einträge von {username}", "en": "Latest entries from {username}"},
    "summary.heading": {"de": "Monatsübersicht", "en": "Monthly summary"},
    "summary.info": {
        "de": "Auswertung für {month}.{year} – ein Bier = {price} €.",
        "en": "Overview for {month}.{year} – one drink = {price} €.",
    },
    "summary.no_entries": {"de": "Für diesen Monat liegen noch keine Einträge vor.", "en": "No entries exist for this month yet."},
    "admin.heading": {"de": "Admin-Übersicht", "en": "Admin overview"},
    "admin.subtitle": {"de": "Nutzer, Einträge und Zahlungen im Blick.", "en": "Keep users, entries, and payments in view."},
    "admin.balance_report": {"de": "Offene Beträge / Monatsreport", "en": "Open balances / monthly report"},
    "admin.stats.users": {"de": "Nutzer", "en": "Users"},
    "admin.stats.admins": {"de": "Admins", "en": "Admins"},
    "admin.stats.drinks_total": {"de": "Getränke gesamt", "en": "Total drinks"},
    "admin.stats.latest_entries": {"de": "Letzte Einträge", "en": "Latest entries"},
    "admin.user_management": {"de": "Nutzerverwaltung", "en": "User management"},
    "admin.export": {"de": "Export", "en": "Export"},
    "admin.export_csv": {"de": "CSV exportieren", "en": "Export CSV"},
    "admin.export_help": {
        "de": "Exportiert alle Einträge des gewählten Monats als CSV (Spieler, Datum, Anzahl, Getränk, Preis).",
        "en": "Exports all entries of the selected month as CSV (player, date, amount, drink, price).",
    },
    "admin.latest_entries_global": {"de": "Letzte Einträge (global)", "en": "Latest entries (global)"},
    "admin_edit_user.heading": {"de": "User bearbeiten", "en": "Edit user"},
    "admin.back_overview": {"de": "← Zurück zur Übersicht", "en": "← Back to overview"},
    "admin_edit_user.password_hint": {"de": "Leer lassen, um Passwort nicht zu ändern", "en": "Leave blank to keep password unchanged"},
    "admin_edit_entry.heading": {"de": "Eintrag bearbeiten", "en": "Edit entry"},
    "balances.heading": {"de": "Offene Beträge pro Spieler", "en": "Open balances per player"},
    "balances.subtitle": {
        "de": "Übersicht aller Monate mit den jeweiligen Biermengen und Euro-Beträgen pro Spieler (theoretische Kassensumme).",
        "en": "Overview of all months with drink quantities and euro totals per player (theoretical cash total).",
    },
    "balances.price_hint": {"de": "Ein Bier = {price} €", "en": "One drink = {price} €"},
    "balances.month_header": {
        "de": "Monat {ym} — Gesamt: {total_beers} Bier(e) / {total_euros} €",
        "en": "Month {ym} — Total: {total_beers} drink(s) / {total_euros} €",
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
    "action.save": {"de": "Speichern", "en": "Save"},
    "action.cancel": {"de": "Abbrechen", "en": "Cancel"},
    "action.update": {"de": "Aktualisieren", "en": "Update"},
    "action.edit": {"de": "Bearbeiten", "en": "Edit"},
    "action.delete": {"de": "Löschen", "en": "Delete"},
    "action.change": {"de": "Ändern", "en": "Change"},
    "table.player": {"de": "Spieler", "en": "Player"},
    "table.beers": {"de": "Biere", "en": "Drinks"},
    "table.total": {"de": "Gesamt", "en": "Total"},
    "table.total_row": {"de": "Gesamt", "en": "Total"},
    "table.open": {"de": "Offen", "en": "Open"},
    "table.paid": {"de": "Bezahlt", "en": "Paid"},
    "table.date": {"de": "Datum", "en": "Date"},
    "table.recorded_at": {"de": "Erfasst am", "en": "Recorded at"},
    "table.payment_method": {"de": "Zahlart", "en": "Payment method"},
    "table.no_entries": {"de": "Noch keine Einträge vorhanden.", "en": "No entries yet."},
    "table.no_entries_yet": {"de": "Es sind noch keine Einträge vorhanden.", "en": "No entries are available yet."},
    "table.drinks": {"de": "Getränke", "en": "Drinks"},
    "table.total_euro": {"de": "Summe (€)", "en": "Total (€)"},
    "table.last_date": {"de": "Letztes Datum", "en": "Last date"},
    "table.role": {"de": "Rolle", "en": "Role"},
    "table.actions": {"de": "Aktionen", "en": "Actions"},
    "table.drink": {"de": "Getränk", "en": "Drink"},
    "table.amount": {"de": "Anzahl", "en": "Amount"},
    "table.payment": {"de": "Zahlung", "en": "Payment"},
    "table.amount_euro": {"de": "Betrag (€)", "en": "Amount (€)"},
    "role.admin": {"de": "Admin", "en": "Admin"},
    "role.user": {"de": "User", "en": "User"},
    "payment.paid": {"de": "bezahlt", "en": "paid"},
    "payment.open": {"de": "offen", "en": "open"},
    "payment.bar": {"de": "Bar", "en": "Cash"},
    "confirm.delete_user": {"de": "User '{username}' wirklich löschen?", "en": "Really delete user '{username}'?"},
    "confirm.delete_entry": {"de": "Eintrag wirklich löschen?", "en": "Really delete entry?"},
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(app.instance_path, "bierkaessle.sqlite3"),
        BEER_PRICE=float(os.environ.get("BEER_PRICE", "1.50")),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    # ---------------------- Datenbank-Helfer ----------------------
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
            """
        )
        # Migration: Spalten ergaenzen falls noch nicht vorhanden (Bestandsdatenbank)
        try:
            db.execute("ALTER TABLE beers ADD COLUMN drink_type TEXT NOT NULL DEFAULT 'bier'")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE beers ADD COLUMN price_per_unit REAL NOT NULL DEFAULT 1.50")
        except Exception:
            pass
        db.commit()

    with app.app_context():
        init_db()

    # ---------------------- User/Role-Helpers ----------------------
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

    @app.context_processor
    def inject_roles():
        user = current_user()
        return {
            "current_user_obj": user,
            "is_admin": is_admin_user(user),
            "drink_catalog": DRINK_CATALOG,
            "drink_label": DRINK_LABEL,
            "t": translate,
            "tf": translate_flash_message,
            "current_lang": get_language(),
            "current_theme": get_theme(),
            "session_theme_defined": "theme" in session,
            "supported_languages": sorted(SUPPORTED_LANGUAGES),
            "supported_themes": sorted(SUPPORTED_THEMES),
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

    # ---------------------- Auth-Routen ----------------------
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash_i18n("flash.empty_username_password", "danger")
                return render_template("register.html")

            db = get_db()

            is_first_user = db.execute(
                "SELECT COUNT(*) AS c FROM users"
            ).fetchone()["c"] == 0
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
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            db = get_db()
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

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
        """Monatliche Zusammenfassung fuer die Login-Seite (schreibgeschuetzt)."""
        db = get_db()
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"

        rows = db.execute(
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

    @app.route("/logout")
    def logout():
        session.clear()
        flash_i18n("flash.logout_success", "info")
        return redirect(url_for("login"))

    # ---------------------- Kernfunktionen ----------------------
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
            SELECT
                b.id,
                b.drinking_date,
                b.amount,
                b.drink_type,
                b.price_per_unit,
                b.created_at,
                COALESCE(p.is_paid, 0) AS is_paid,
                p.method AS payment_method
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

    @app.route("/summary")
    @login_required
    def summary():
        db = get_db()

        year = request.args.get("year")
        month = request.args.get("month")

        today = date.today()
        try:
            year = int(year) if year else today.year
            month = int(month) if month else today.month
        except ValueError:
            year, month = today.year, today.month

        month_str = f"{year:04d}-{month:02d}"

        rows = db.execute(
            """
            SELECT u.username,
                   COALESCE(SUM(b.amount), 0) AS total_drinks,
                   COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros
            FROM users u
            LEFT JOIN beers b
              ON u.id = b.user_id
             AND strftime('%Y-%m', b.drinking_date) = ?
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
            summary_data.append(
                {
                    "username": row["username"],
                    "beers": drinks,
                    "euros": round(euros, 2),
                }
            )

        return render_template(
            "summary.html",
            summary_data=summary_data,
            beer_price=app.config["BEER_PRICE"],
            total_beers=total_drinks,
            total_euros=round(total_euros, 2),
            year=year,
            month=month,
        )

    # ---------------------- Admin-Bereich ----------------------
    @app.route("/admin")
    @login_required
    @admin_required
    def admin_dashboard():
        db = get_db()
        beer_price = app.config["BEER_PRICE"]

        users_stats = db.execute(
            """
            SELECT u.id, u.username, u.telegram_id, u.is_admin,
                   COALESCE(SUM(b.amount), 0) AS beers,
                   MAX(b.drinking_date) AS last_date
            FROM users u
            LEFT JOIN beers b ON u.id = b.user_id
            GROUP BY u.id
            ORDER BY u.username
            """
        ).fetchall()

        recent_entries = db.execute(
            """
            SELECT
                b.id,
                b.drinking_date,
                b.amount,
                b.drink_type,
                b.price_per_unit,
                b.created_at,
                u.username,
                COALESCE(p.is_paid, 0) AS is_paid,
                p.method AS payment_method
            FROM beers b
            JOIN users u ON u.id = b.user_id
            LEFT JOIN payments p ON p.beer_id = b.id
            ORDER BY b.drinking_date DESC, b.created_at DESC
            LIMIT 50
            """
        ).fetchall()

        return render_template(
            "admin_dashboard.html",
            users_stats=users_stats,
            recent_entries=recent_entries,
            beer_price=beer_price,
            drink_label=DRINK_LABEL,
        )

    @app.route("/admin/user/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def admin_edit_user(user_id):
        db = get_db()
        admin_user = current_user()
        user = db.execute(
            "SELECT id, username, telegram_id, is_admin, created_at FROM users WHERE id = ?",
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
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, user_id),
            ).fetchone()
            if duplicate:
                flash_i18n("flash.username_taken", "danger")
                return render_template("admin_edit_user.html", edit_user=user)

            if telegram_id is not None:
                duplicate_tg = db.execute(
                    "SELECT id FROM users WHERE telegram_id = ? AND id != ?",
                    (telegram_id, user_id),
                ).fetchone()
                if duplicate_tg:
                    flash_i18n("flash.telegram_id_taken", "danger")
                    return render_template("admin_edit_user.html", edit_user=user)

            db.execute(
                "UPDATE users SET username = ?, telegram_id = ?, is_admin = ? WHERE id = ?",
                (username, telegram_id, is_admin_checked, user_id),
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
        user = db.execute(
            "SELECT id, username, is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

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
            "DELETE FROM payments WHERE beer_id IN (SELECT id FROM beers WHERE user_id = ?)",
            (user_id,),
        )
        db.execute("DELETE FROM beers WHERE user_id = ?", (user_id,))
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
            FROM beers b
            JOIN users u ON u.id = b.user_id
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
            FROM beers b
            JOIN users u ON u.id = b.user_id
            WHERE strftime('%Y-%m', b.drinking_date) = ?
            ORDER BY u.username, b.drinking_date
            """,
            (month_str,),
        ).fetchall()

        output = [["username", "date", "amount", "drink_type", "price_per_unit", "total"]]
        for r in rows:
            output.append([
                r["username"], r["drinking_date"], r["amount"],
                r["drink_type"], r["price_per_unit"],
                round(r["amount"] * r["price_per_unit"], 2)
            ])

        csv_lines = [",".join(str(col) for col in row) for row in output]
        csv_data = "\n".join(csv_lines)

        response = make_response(csv_data)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = (
            f"attachment; filename=bierkaessle_{year}_{month:02d}.csv"
        )
        return response

    @app.route("/admin/report/balances")
    @login_required
    @admin_required
    def admin_report_balances():
        db = get_db()

        rows = db.execute(
            """
            SELECT
                u.username AS username,
                strftime('%Y-%m', b.drinking_date) AS ym,
                COALESCE(SUM(b.amount), 0) AS total_drinks,
                COALESCE(SUM(b.amount * b.price_per_unit), 0) AS total_euros
            FROM users u
            JOIN beers b ON u.id = b.user_id
            GROUP BY u.username, ym
            ORDER BY ym DESC, u.username
            """
        ).fetchall()

        data_drinks = {}
        data_euros = {}
        months = []
        for r in rows:
            ym = r["ym"]
            if ym not in data_drinks:
                data_drinks[ym] = {}
                data_euros[ym] = {}
                months.append(ym)
            data_drinks[ym][r["username"]] = r["total_drinks"]
            data_euros[ym][r["username"]] = r["total_euros"]

        users = [
            r["username"]
            for r in db.execute("SELECT username FROM users ORDER BY username").fetchall()
        ]

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
                entries.append(
                    {
                        "username": username,
                        "beers": drinks,
                        "euros": round(euros, 2),
                    }
                )
            month_rows.append(
                {
                    "ym": ym,
                    "entries": entries,
                    "total_beers": total_drinks,
                    "total_euros": round(total_euros, 2),
                }
            )

        return render_template(
            "admin_report_balances.html",
            month_rows=month_rows,
            users=users,
            beer_price=app.config["BEER_PRICE"],
        )

    @app.route("/entry/<int:entry_id>/payment", methods=["POST"])
    @login_required
    def update_payment(entry_id):
        db = get_db()
        user = current_user()

        entry = db.execute(
            """
            SELECT b.id, b.user_id
            FROM beers b
            WHERE b.id = ?
            """,
            (entry_id,),
        ).fetchone()

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
