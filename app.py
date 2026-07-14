
import os
import sqlite3
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash


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
        db.commit()

    @app.before_first_request
    def ensure_db():
        init_db()

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

    def login_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                flash("Bitte zuerst einloggen.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Benutzername und Passwort duerfen nicht leer sein.", "danger")
                return render_template("register.html")

            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
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
                return render_template("login.html")

            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Willkommen, {user['username']}!", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Erfolgreich ausgeloggt.", "info")
        return redirect(url_for("login"))

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

            try:
                amount = int(amount_raw)
            except ValueError:
                amount = 0

            if amount <= 0:
                flash("Bitte eine gueltige Bier-Anzahl eintragen.", "danger")
            else:
                db.execute(
                    "INSERT INTO beers (user_id, drinking_date, amount) VALUES (?, ?, ?)",
                    (user["id"], date_raw, amount),
                )
                db.commit()
                flash("Eintrag gespeichert.", "success")

            return redirect(url_for("dashboard"))

        entries = db.execute(
            """
            SELECT drinking_date, amount, created_at
            FROM beers
            WHERE user_id = ?
            ORDER BY drinking_date DESC, created_at DESC
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
            SELECT u.username, COALESCE(SUM(b.amount), 0) AS beers
            FROM users u
            LEFT JOIN beers b
              ON u.id = b.user_id
             AND strftime('%Y-%m', b.drinking_date) = ?
            GROUP BY u.id
            ORDER BY u.username
            """,
            (month_str,),
        ).fetchall()

        beer_price = app.config["BEER_PRICE"]
        summary_data = []
        total_beers = 0
        total_euros = 0.0

        for row in rows:
            beers = row["beers"] or 0
            euros = beers * beer_price
            total_beers += beers
            total_euros += euros
            summary_data.append(
                {
                    "username": row["username"],
                    "beers": beers,
                    "euros": euros,
                }
            )

        return render_template(
            "summary.html",
            summary_data=summary_data,
            beer_price=beer_price,
            total_beers=total_beers,
            total_euros=total_euros,
            year=year,
            month=month,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "1904")), debug=False)
