from flask import Flask, redirect, render_template, request, url_for, session, flash
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from flask_login import login_user, logout_user, login_required, current_user

from db import db_read, db_write, init_app, get_db
from auth import login_manager, authenticate, register_user
from bank_service import get_balance, deposit, withdraw, transfer

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

load_dotenv()
W_SECRET = os.getenv("W_SECRET")

app = Flask(__name__)
app.config["DEBUG"] = True
app.secret_key = "supersecret"

login_manager.init_app(app)
login_manager.login_view = "login"


def is_valid_signature(x_hub_signature, data, private_key):
    """GitHub Webhook Signature Check."""
    hash_algorithm, github_signature = x_hub_signature.split("=", 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, "latin-1")
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)


@app.post("/update_server")
def webhook():
    x_hub_signature = request.headers.get("X-Hub-Signature")
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo("./mysite")
        origin = repo.remotes.origin
        origin.pull()
        return "Updated PythonAnywhere successfully", 200
    return "Unauthorized", 401

# ---------------------------
# AUTHENTIFICATION ROUTES
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = authenticate(request.form["email"], request.form["password"])
        if user:
            login_user(user)
            return redirect(url_for("index"))
        error = "E-Mail oder Passwort ist falsch."
    return render_template(
        "auth.html",
        title="In dein Konto einloggen",
        action=url_for("login"),
        button_label="Einloggen",
        error=error,
        footer_text="Noch kein Konto?",
        footer_link_url=url_for("register"),
        footer_link_label="Registrieren",
        mode="login",
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        vorname = request.form["vorname"]
        nachname = request.form["nachname"]
        email = request.form["email"]
        password = request.form["password"]
        ok, msg = register_user(vorname, nachname, email, password)
        if ok:
            return redirect(url_for("login"))
        error = msg or "Registrierung fehlgeschlagen."
    return render_template(
        "auth.html",
        title="Neues Konto erstellen",
        action=url_for("register"),
        button_label="Registrieren",
        error=error,
        footer_text="Du hast bereits ein Konto?",
        footer_link_url=url_for("login"),
        footer_link_label="Einloggen",
        mode="register",
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ---------------------------
# USERS ROUTE
# ---------------------------
@app.route("/users", methods=["GET"])
@login_required
def users():
    rows = db_read(
        "SELECT konto_id, vorname, nachname, email "
        "FROM kunden_konto ORDER BY nachname, vorname"
    )
    return render_template("users.html", users=rows)

# ---------------------------
# MAIN PAGE
# ---------------------------
@app.route("/")
@login_required
def index():
    return render_template("main_page.html")

# ---------------------------
# BANK DASHBOARD
# ---------------------------
@app.route("/bank")
@login_required
def bank():
    saldo, waehrung = get_balance(current_user.id)
    # Letzte 20 Transaktionen des primären Kontos abrufen
    tx = db_read(
        """
        SELECT typ, betrag, waehrung, gebuehr, beschreibung, ausgefuehrt_am
        FROM transaktion
        WHERE gesamt_konto_id = (
            SELECT gesamt_konto_id
            FROM gesamt_konto
            WHERE kunden_konto_id = %s
            ORDER BY gesamt_konto_id
            LIMIT 1
        )
        ORDER BY ausgefuehrt_am DESC
        LIMIT 20
        """,
        (current_user.id,),
    )
    return render_template("bank.html", saldo=saldo, waehrung=waehrung, tx=tx)

def _parse_amount(form_value: str) -> Decimal:
    """Wandelt einen eingegebenen Betrag in Decimal um (unterstützt Komma)."""
    if form_value is None:
        raise ValueError("Betrag fehlt.")
    raw = form_value.strip().replace(",", ".")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("Ungültiger Betrag.")
    if amount <= 0:
        raise ValueError("Betrag muss > 0 sein.")
    return amount

@app.post("/bank/deposit")
@login_required
def bank_deposit():
    try:
        amount = _parse_amount(request.form.get("amount"))
        deposit(current_user.id, amount, "CHF", "Manuelle Einzahlung")
        return redirect(url_for("bank"))
    except Exception as e:
        return render_template("bank_error.html", error=str(e)), 400

@app.post("/bank/withdraw")
@login_required
def bank_withdraw():
    try:
        amount = _parse_amount(request.form.get("amount"))
        withdraw(current_user.id, amount, "CHF", "Manuelle Auszahlung")
        return redirect(url_for("bank"))
    except Exception as e:
        return render_template("bank_error.html", error=str(e)), 400

@app.post("/bank/transfer")
@login_required
def bank_transfer():
    try:
        to_email = (request.form.get("to_email") or "").strip()
        if not to_email:
            raise ValueError("Empfänger E-Mail fehlt.")
        amount = _parse_amount(request.form.get("amount"))
        transfer(current_user.id, to_email, amount, "CHF")
        return redirect(url_for("bank"))
    except Exception as e:
        return render_template("bank_error.html", error=str(e)), 400

# ---------------------------
# AKTIENÜBERSICHT, KAUF UND VERKAUF
# ---------------------------
@app.route("/stocks")
@login_required
def stocks_page():
    """Übersichtsseite: verfügbare Aktien und Portfolio des aktuellen Nutzers anzeigen."""
    user_id = current_user.id
    db = get_db()
    cur = db.cursor()
    # Alle verfügbaren Aktien auslesen
    stocks = cur.execute("SELECT stock_id, name, price FROM available_stocks").fetchall()
    # Aktienbestand des Nutzers (Join mit Aktien für Namen und Preis)
    portfolio = cur.execute(
        """
        SELECT s.stock_id, s.name, s.price, u.quantity 
        FROM user_stocks u
        JOIN available_stocks s ON u.stock_id = s.stock_id
        WHERE u.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return render_template("stocks.html", stocks=stocks, portfolio=portfolio)

@app.route("/buy_stock", methods=["POST"])
@login_required
def buy_stock():
    """Aktie kaufen: verarbeitet das Kauf-Formular."""
    user_id = current_user.id
    stock_id = request.form.get("stock_id")
    qty_str = request.form.get("quantity", "0")
    try:
        quantity = int(qty_str)
    except ValueError:
        quantity = 0
    if quantity <= 0:
        flash("Ungültige Anzahl", "error")
        return redirect("/stocks")

    db = get_db()
    cur = db.cursor()
    # Preis der Aktie abrufen
    cur.execute("SELECT price FROM available_stocks WHERE stock_id = ?", (stock_id,))
    row = cur.fetchone()
    if row is None:
        flash("Aktie existiert nicht", "error")
        return redirect("/stocks")
    price = row[0]
    cost = price * quantity
    # Kontostand (saldo) des Nutzers prüfen
    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
    konto_row = cur.fetchone()
    if konto_row is None:
        flash("Kein Hauptkonto gefunden", "error")
        return redirect("/stocks")
    saldo_current = konto_row[0]
    if cost > saldo_current:
        flash("Nicht genügend Guthaben für diesen Kauf", "error")
        return redirect("/stocks")
    # Saldo verringern
    new_saldo = saldo_current - cost
    cur.execute("UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?", (new_saldo, user_id))
    # Aktienbestand erhöhen oder anlegen
    cur.execute(
        "SELECT quantity FROM user_stocks WHERE user_id = ? AND stock_id = ?",
        (user_id, stock_id),
    )
    result = cur.fetchone()
    if result:
        new_qty = result[0] + quantity
        cur.execute(
            "UPDATE user_stocks SET quantity = ? WHERE user_id = ? AND stock_id = ?",
            (new_qty, user_id, stock_id),
        )
    else:
        cur.execute(
            "INSERT INTO user_stocks (user_id, stock_id, quantity) VALUES (?, ?, ?)",
            (user_id, stock_id, quantity),
        )
    db.commit()
    flash("Aktienkauf erfolgreich durchgeführt", "success")
    return redirect("/stocks")

@app.route("/sell_stock", methods=["POST"])
@login_required
def sell_stock():
    """Aktie verkaufen: verarbeitet das Verkaufs-Formular."""
    user_id = current_user.id
    stock_id = request.form.get("stock_id")
    qty_str = request.form.get("quantity", "0")
    try:
        quantity = int(qty_str)
    except ValueError:
        quantity = 0
    if quantity <= 0:
        flash("Ungültige Anzahl", "error")
        return redirect("/stocks")
    db = get_db()
    cur = db.cursor()
    # Prüfen, ob der Nutzer die Aktie besitzt
    cur.execute(
        "SELECT quantity FROM user_stocks WHERE user_id = ? AND stock_id = ?",
        (user_id, stock_id),
    )
    result = cur.fetchone()
    if result is None or result[0] < quantity:
        flash("Nicht genügend Aktien zum Verkaufen vorhanden", "error")
        return redirect("/stocks")
    # Aktienpreis holen
    cur.execute("SELECT price FROM available_stocks WHERE stock_id = ?", (stock_id,))
    price = cur.fetchone()[0]
    revenue = price * quantity
    # Aktienbestand verringern
    new_qty = result[0] - quantity
    if new_qty > 0:
        cur.execute(
            "UPDATE user_stocks SET quantity = ? WHERE user_id = ? AND stock_id = ?",
            (new_qty, user_id, stock_id),
        )
    else:
        cur.execute(
            "DELETE FROM user_stocks WHERE user_id = ? AND stock_id = ?",
            (user_id, stock_id),
        )
    # Verkaufserlös dem Hauptkonto gutschreiben
    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
    konto_row = cur.fetchone()
    current_saldo = konto_row[0]
    new_saldo = current_saldo + revenue
    cur.execute("UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?", (new_saldo, user_id))
    db.commit()
    flash("Aktienverkauf erfolgreich durchgeführt", "success")
    return redirect("/stocks")

# ---------------------------
# SPARKONTO LOGIK UND ROUTEN
# ---------------------------
def apply_monthly_interest(user_id):
    """Prüft, ob monatliche Zinsen gutzuschreiben sind und aktualisiert das Sparkonto."""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT balance, last_interest_date FROM savings_accounts WHERE user_id = ?", 
        (user_id,)
    )
    result = cur.fetchone()
    if result is None:
        return
    balance, last_date_str = result
    last_date = datetime.fromisoformat(last_date_str)
    today = datetime.today()
    months_passed = (today.year - last_date.year) * 12 + (today.month - last_date.month)
    if months_passed >= 1:
        for _ in range(months_passed):
            interest = balance * Decimal("0.01")
            balance += interest
        cur.execute(
            "UPDATE savings_accounts SET balance = ?, last_interest_date = ? WHERE user_id = ?",
            (balance, today.strftime("%Y-%m-%d"), user_id),
        )
        db.commit()

@app.route("/savings")
@login_required
def savings_page():
    """Anzeige des Sparkontos: aktueller Stand und Formulare für Ein-/Auszahlung."""
    user_id = current_user.id
    apply_monthly_interest(user_id)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT balance, last_interest_date FROM savings_accounts WHERE user_id = ?", (user_id,))
    savings = cur.fetchone()
    savings_balance = savings[0] if savings else Decimal("0.00")
    last_date = savings[1] if savings else None
    return render_template("savings.html", savings_balance=savings_balance, last_date=last_date)

@app.route("/savings/deposit", methods=["POST"])
@login_required
def savings_deposit():
    """Einzahlung auf das Sparkonto (vom Hauptkonto abziehen)."""
    user_id = current_user.id
    amount_str = request.form.get("amount", "0")
    try:
        amount = Decimal(amount_str)
    except:
        amount = Decimal("0")
    if amount <= 0:
        flash("Bitte einen gültigen Betrag eingeben.", "error")
        return redirect("/savings")

    db = get_db()
    cur = db.cursor()
    # Hauptkonto-Saldo abrufen
    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
    saldo_row = cur.fetchone()
    main_saldo = saldo_row[0]
    if amount > main_saldo:
        flash("Nicht genügend Guthaben auf dem Hauptkonto.", "error")
        return redirect("/savings")
    # Hauptkonto belasten
    new_main_saldo = main_saldo - amount
    cur.execute("UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?", (new_main_saldo, user_id))
    # Sparkonto gutschreiben
    cur.execute("SELECT balance FROM savings_accounts WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    if result:
        new_savings_balance = result[0] + amount
        cur.execute("UPDATE savings_accounts SET balance = ? WHERE user_id = ?", (new_savings_balance, user_id))
    else:
        today_str = datetime.today().strftime("%Y-%m-%d")
        cur.execute(
            "INSERT INTO savings_accounts (user_id, balance, last_interest_date) VALUES (?, ?, ?)",
            (user_id, amount, today_str),
        )
    db.commit()
    flash("Einzahlung erfolgreich.", "success")
    return redirect("/savings")

@app.route("/savings/withdraw", methods=["POST"])
@login_required
def savings_withdraw():
    """Abheben vom Sparkonto (aufs Hauptkonto buchen)."""
    user_id = current_user.id
    amount_str = request.form.get("amount", "0")
    try:
        amount = Decimal(amount_str)
    except:
        amount = Decimal("0")
    if amount <= 0:
        flash("Bitte einen gültigen Betrag eingeben.", "error")
        return redirect("/savings")
    db = get_db()
    cur = db.cursor()
    # Sparkonto-Saldo abrufen
    cur.execute("SELECT balance FROM savings_accounts WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    savings_balance = result[0] if result else Decimal("0")
    if amount > savings_balance:
        flash("Nicht genügend Guthaben auf dem Sparkonto.", "error")
        return redirect("/savings")
    # Sparkonto belasten und Hauptkonto gutschreiben
    new_savings_balance = savings_balance - amount
    cur.execute("UPDATE savings_accounts SET balance = ? WHERE user_id = ?", (new_savings_balance, user_id))
    # Hauptkonto erhöhen
    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
    saldo_row = cur.fetchone()
    main_saldo = saldo_row[0]
    new_main_saldo = main_saldo + amount
    cur.execute("UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?", (new_main_saldo, user_id))
    db.commit()
    flash("Abhebung erfolgreich.", "success")
    return redirect("/savings")

# ---------------------------
# WÄHRUNGSUMTAUSCH
# ---------------------------
@app.route("/exchange", methods=["GET", "POST"])
@login_required
def exchange():
    user_id = current_user.id
    db = get_db()
    cur = db.cursor()
    message = None

    if request.method == "POST":
        from_cur = request.form.get("from_currency")
        to_cur = request.form.get("to_currency")
        amount_str = request.form.get("amount", "0")
        try:
            amount = Decimal(amount_str)
        except:
            amount = Decimal("0")
        if amount <= 0 or not from_cur or not to_cur or from_cur == to_cur:
            message = "Ungültige Eingabe für Währungsumtausch."
        else:
            cur.execute(
                "SELECT rate FROM exchange_rates WHERE from_currency = ? AND to_currency = ?",
                (from_cur, to_cur),
            )
            rate_row = cur.fetchone()
            if rate_row is None:
                message = f"Kein Wechselkurs für {from_cur}->{to_cur} vorhanden."
            else:
                rate = rate_row[0]
                converted_amount = (amount * rate).quantize(Decimal("0.01"))
                # Guthaben in Quellwährung ermitteln
                if from_cur == "CHF":
                    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
                    source_row = cur.fetchone()
                    source_balance = source_row[0] if source_row else Decimal("0")
                else:
                    cur.execute(
                        "SELECT balance FROM user_balances WHERE user_id = ? AND currency = ?",
                        (user_id, from_cur),
                    )
                    result = cur.fetchone()
                    source_balance = result[0] if result else Decimal("0")
                if amount > source_balance:
                    message = f"Nicht genügend Guthaben in {from_cur}."
                else:
                    # Abziehen vom Quellkonto
                    if from_cur == "CHF":
                        new_source_balance = source_balance - amount
                        cur.execute(
                            "UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?",
                            (new_source_balance, user_id),
                        )
                    else:
                        new_source_balance = source_balance - amount
                        cur.execute(
                            "UPDATE user_balances SET balance = ? WHERE user_id = ? AND currency = ?",
                            (new_source_balance, user_id, from_cur),
                        )
                    # Gutschrift auf Zielkonto
                    if to_cur == "CHF":
                        cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
                        target_row = cur.fetchone()
                        current_saldo = target_row[0]
                        new_balance = current_saldo + converted_amount
                        cur.execute(
                            "UPDATE gesamt_konto SET saldo = ? WHERE kunden_konto_id = ?",
                            (new_balance, user_id),
                        )
                    else:
                        cur.execute(
                            "SELECT balance FROM user_balances WHERE user_id = ? AND currency = ?",
                            (user_id, to_cur),
                        )
                        result = cur.fetchone()
                        if result:
                            new_target_balance = result[0] + converted_amount
                            cur.execute(
                                "UPDATE user_balances SET balance = ? WHERE user_id = ? AND currency = ?",
                                (new_target_balance, user_id, to_cur),
                            )
                        else:
                            cur.execute(
                                "INSERT INTO user_balances (user_id, currency, balance) VALUES (?, ?, ?)",
                                (user_id, to_cur, converted_amount),
                            )
                    db.commit()
                    message = f"Erfolgreich {amount:.2f} {from_cur} in {converted_amount:.2f} {to_cur} umgetauscht."

    # Aktuelle Guthaben abrufen
    cur.execute("SELECT saldo FROM gesamt_konto WHERE kunden_konto_id = ?", (user_id,))
    chf_balance_row = cur.fetchone()
    chf_balance = chf_balance_row[0] if chf_balance_row else Decimal("0.00")
    cur.execute("SELECT currency, balance FROM user_balances WHERE user_id = ?", (user_id,))
    foreign_balances = cur.fetchall()
    return render_template("exchange.html", chf_balance=chf_balance, foreign_balances=foreign_balances, message=message)

# Datenbank initialisieren (MySQL)
init_app(app)

if __name__ == "__main__":
    app.run()
