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

    @app.context_processor
    def inject_roles():
        user = current_user()
        return {
            "current_user_obj": user,
            "is_admin": is_admin_user(user),
            "drink_catalog": DRINK_CATALOG,
            "drink_label": DRINK_LABEL,
        }

    def login_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                flash("Bitte zuerst einloggen.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    def admin_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not is_admin_user(user):
                flash("Admin-Rechte erforderlich.", "danger")
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
                flash("Benutzername und Passwort duerfen nicht leer sein.", "danger")
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
                flash("Benutzername ist bereits vergeben.", "danger")
                return render_template("register.html")

            flash("Registrierung erfolgreich. Bitte einloggen.", "success")
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
                flash("Benutzername oder Passwort falsch.", "danger")
                return render_template("login.html", **_login_context())

            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Willkommen, {user['username']}!", "success")
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
        flash("Erfolgreich ausgeloggt.", "info")
        return redirect(url_for("login"))

    # ---------------------- Kernfunktionen ----------------------
    @app.route("/")
    def index():
        if current_user() is None:
            return redirect(url_for("login"))
        return redirect(url_for("dashboard"))

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
                flash("Bitte eine gueltige Anzahl eintragen.", "danger")
            else:
                db.execute(
                    "INSERT INTO beers (user_id, drinking_date, amount, drink_type, price_per_unit) VALUES (?, ?, ?, ?, ?)",
                    (user["id"], date_raw, amount, drink_type, price),
                )
                db.commit()
                flash("Eintrag gespeichert.", "success")

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
            SELECT u.id, u.username, u.is_admin,
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
            flash("Eintrag nicht gefunden.", "warning")
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
                flash("Bitte eine gueltige Anzahl eintragen.", "danger")
            else:
                db.execute(
                    "UPDATE beers SET amount = ?, drinking_date = ?, drink_type = ?, price_per_unit = ? WHERE id = ?",
                    (amount, date_raw, drink_type, price, entry_id),
                )
                db.commit()
                flash("Eintrag aktualisiert.", "success")
                return redirect(url_for("admin_dashboard"))

        return render_template("admin_edit_entry.html", entry=entry, drink_catalog=DRINK_CATALOG)

    @app.route("/admin/entry/<int:entry_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_entry(entry_id):
        db = get_db()
        db.execute("DELETE FROM beers WHERE id = ?", (entry_id,))
        db.commit()
        flash("Eintrag gelöscht.", "info")
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
            flash("Eintrag nicht gefunden.", "warning")
            return redirect(url_for("dashboard"))

        if (entry["user_id"] != user["id"]) and (not is_admin_user(user)):
            flash("Keine Berechtigung für diesen Eintrag.", "danger")
            return redirect(url_for("dashboard"))

        is_paid = 1 if request.form.get("is_paid") == "on" else 0
        method = request.form.get("method") or None

        if is_paid and method not in ("BAR", "PAYPAL"):
            flash("Bitte eine gültige Zahlart wählen.", "danger")
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

        flash("Zahlstatus aktualisiert.", "success")
        return redirect(request.referrer or url_for("dashboard"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "1904")), debug=False)
