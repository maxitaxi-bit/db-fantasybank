from flask import Flask, redirect, render_template, request, url_for
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
import logging
from decimal import Decimal, InvalidOperation

from db import db_read, db_write
from auth import login_manager, authenticate, register_user
from flask_login import login_user, logout_user, login_required, current_user
from flask import session, redirect, request, render_template, flash
from datetime import datetime, timedelta
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


# DON'T CHANGE
def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split("=", 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, "latin-1")
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)


# DON'T CHANGE
@app.post("/update_server")
def webhook():
    x_hub_signature = request.headers.get("X-Hub-Signature")
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo("./mysite")
        origin = repo.remotes.origin
        origin.pull()
        return "Updated PythonAnywhere successfully", 200
    return "Unauthorized", 401


# -------------------------
# AUTH
# -------------------------
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


# -------------------------
# USERS
# -------------------------
@app.route("/users", methods=["GET"])
@login_required
def users():
    rows = db_read(
        "SELECT konto_id, vorname, nachname, email FROM kunden_konto ORDER BY nachname, vorname"
    )
    return render_template("users.html", users=rows)



@app.route("/")
@login_required
def index():
    return render_template("main_page.html")



# -------------------------
# BANK (USES bank_service)
# -------------------------
@app.route("/bank")
@login_required
def bank():
    saldo, waehrung = get_balance(current_user.id)

    tx = db_read(
        """
        SELECT typ, betrag, waehrung, gebuehr, beschreibung, ausgefuehrt_am
        FROM transaktion
        WHERE gesamt_konto_id = (
          SELECT gesamt_konto_id
          FROM gesamt_konto
          WHERE kunden_konto_id=%s
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
        deposit(current_user.id, amount, "CHF", "Manual deposit")
        return redirect(url_for("bank"))
    except Exception as e:
        return render_template("bank_error.html", error=str(e)), 400


@app.post("/bank/withdraw")
@login_required
def bank_withdraw():
    try:
        amount = _parse_amount(request.form.get("amount"))
        withdraw(current_user.id, amount, "CHF", "Manual withdrawal")
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


# In app.py: Routen für Aktienübersicht, Kauf und Verkauf



@app.route('/stocks')
def stocks_page():
    """Übersichtsseite: verfügbare Aktien und Portfolio des aktuellen Nutzers anzeigen."""
    user_id = session.get('user_id')        # aktuell eingeloggter Nutzer (aus Session)
    db = get_db()                           # DB-Verbindung (Funktion get_db() vorausgesetzt)
    cur = db.cursor()
    # Alle verfügbaren Aktien auslesen
    stocks = cur.execute("SELECT stock_id, name, price FROM available_stocks").fetchall()
    # Aktienbestand des Nutzers (Join mit Aktien für Namen und Preis)
    portfolio = cur.execute("""
        SELECT s.stock_id, s.name, s.price, u.quantity 
        FROM user_stocks u 
        JOIN available_stocks s ON u.stock_id = s.stock_id 
        WHERE u.user_id = ?;
    """, (user_id,)).fetchall()
    return render_template('stocks.html', stocks=stocks, portfolio=portfolio)

@app.route('/buy_stock', methods=['POST'])
def buy_stock():
    """Aktie kaufen: verarbeitet das Kauf-Formular."""
    user_id = session.get('user_id')
    stock_id = request.form.get('stock_id')
    qty_str = request.form.get('quantity', "0")
    try:
        quantity = int(qty_str)
    except:
        quantity = 0
    if quantity <= 0:
        # Ungültige Eingabe
        flash("Ungültige Anzahl", "error")
        return redirect('/stocks')
    # Aktienpreis abrufen
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT price FROM available_stocks WHERE stock_id = ?", (stock_id,))
    row = cur.fetchone()
    if row is None:
        flash("Aktie existiert nicht", "error")
        return redirect('/stocks')
    price = row[0]
    cost = price * quantity
    # Kontostand des Nutzers prüfen (angenommen: Users-Tabelle hat Feld 'balance')
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    user_balance = cur.fetchone()[0]
    if cost > user_balance:
        # Nicht genug Guthaben für den Kauf
        flash("Nicht genügend Guthaben für diesen Kauf", "error")
        return redirect('/stocks')
    # Kauf durchführen: Geld abziehen und Aktienbestand erhöhen
    new_balance = user_balance - cost
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
    # Prüfen, ob der Nutzer die Aktie schon besitzt
    cur.execute("SELECT quantity FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                (user_id, stock_id))
    result = cur.fetchone()
    if result:
        # Bereits Eintrag vorhanden: Anzahl erhöhen
        current_qty = result[0]
        new_qty = current_qty + quantity
        cur.execute("UPDATE user_stocks SET quantity = ? WHERE user_id = ? AND stock_id = ?", 
                    (new_qty, user_id, stock_id))
    else:
        # Noch kein Eintrag: neuen Datensatz anlegen
        cur.execute("INSERT INTO user_stocks (user_id, stock_id, quantity) VALUES (?, ?, ?)", 
                    (user_id, stock_id, quantity))
    db.commit()
    flash("Aktienkauf erfolgreich durchgeführt", "success")
    return redirect('/stocks')

@app.route('/sell_stock', methods=['POST'])
def sell_stock():
    """Aktie verkaufen: verarbeitet das Verkaufs-Formular."""
    user_id = session.get('user_id')
    stock_id = request.form.get('stock_id')
    qty_str = request.form.get('quantity', "0")
    try:
        quantity = int(qty_str)
    except:
        quantity = 0
    if quantity <= 0:
        flash("Ungültige Anzahl", "error")
        return redirect('/stocks')
    db = get_db()
    cur = db.cursor()
    # Prüfen, ob der Nutzer die Aktie besitzt und wie viele
    cur.execute("SELECT quantity FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                (user_id, stock_id))
    result = cur.fetchone()
    if result is None or result[0] < quantity:
        # Nutzer hat nicht genügend Stücke dieser Aktie
        flash("Nicht genügend Aktien zum Verkaufen vorhanden", "error")
        return redirect('/stocks')
    # Aktienpreis holen für Verkaufswert
    cur.execute("SELECT price FROM available_stocks WHERE stock_id = ?", (stock_id,))
    price = cur.fetchone()[0]
    revenue = price * quantity  # Verkaufserlös
    # Aktienbestand reduzieren
    new_qty = result[0] - quantity
    if new_qty > 0:
        cur.execute("UPDATE user_stocks SET quantity = ? WHERE user_id = ? AND stock_id = ?", 
                    (new_qty, user_id, stock_id))
    else:
        # Wenn alles verkauft, den Datensatz löschen
        cur.execute("DELETE FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                    (user_id, stock_id))
    # Geld dem Nutzer gutschreiben
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    current_balance = cur.fetchone()[0]
    new_balance = current_balance + revenue
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
    db.commit()
    flash("Aktienverkauf erfolgreich durchgeführt", "success")
    return redirect('/stocks')

# In app.py: Logik für Sparkonto-Zinsen und Routen für Ein-/Auszahlung



def apply_monthly_interest(user_id):
    """Prüft, ob für das Sparkonto des Nutzers monatliche Zinsen fällig sind, und aktualisiert den Saldo entsprechend."""
    db = get_db()
    cur = db.cursor()
    # Aktuellen Saldo und Datum der letzten Zinszahlung holen
    cur.execute("SELECT balance, last_interest_date FROM savings_accounts WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    if result is None:
        return  # Kein Sparkonto vorhanden (falls noch nicht angelegt)
    balance, last_date_str = result
    last_date = datetime.fromisoformat(last_date_str)
    today = datetime.today()
    # Prüfen, wie viele Monate seit last_interest_date vergangen sind
    months_passed = (today.year - last_date.year) * 12 + (today.month - last_date.month)
    if months_passed >= 1:
        # Für jeden vollen Monat 1% Zinsen hinzufügen (Zinseszins bei >1 Monaten)
        for _ in range(months_passed):
            interest = balance * 0.01
            balance += interest
        # Datum der letzten Zinsgutschrift auf heute aktualisieren
        cur.execute("UPDATE savings_accounts SET balance = ?, last_interest_date = ? WHERE user_id = ?", 
                    (balance, today.strftime("%Y-%m-%d"), user_id))
        db.commit()

@app.route('/savings')
def savings_page():
    """Anzeige des Sparkontos: aktueller Stand und Formulare für Ein-/Auszahlung."""
    user_id = session.get('user_id')
    # Zinsen ggf. gutschreiben, falls ein Monat vergangen ist
    apply_monthly_interest(user_id)
    db = get_db()
    cur = db.cursor()
    # aktuellen Sparkonto-Stand nach evtl. Zinsgutschrift holen
    cur.execute("SELECT balance, last_interest_date FROM savings_accounts WHERE user_id = ?", (user_id,))
    savings = cur.fetchone()
    savings_balance = savings[0] if savings else 0.0
    last_date = savings[1] if savings else None
    return render_template('savings.html', savings_balance=savings_balance, last_date=last_date)

@app.route('/savings/deposit', methods=['POST'])
def savings_deposit():
    """Einzahlung auf das Sparkonto (vom Hauptkonto abziehen)."""
    user_id = session.get('user_id')
    amount_str = request.form.get('amount', "0")
    try:
        amount = float(amount_str)
    except:
        amount = 0.0
    if amount <= 0:
        flash("Bitte einen gültigen Betrag eingeben.", "error")
        return redirect('/savings')
    db = get_db()
    cur = db.cursor()
    # Hauptkonto-Guthaben prüfen
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    main_balance = cur.fetchone()[0]
    if amount > main_balance:
        flash("Nicht genügend Guthaben auf dem Hauptkonto.", "error")
        return redirect('/savings')
    # Hauptkonto belasten und Sparkonto gutschreiben
    new_main_balance = main_balance - amount
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_main_balance, user_id))
    # Sparkonto aktualisieren (falls noch kein Eintrag, neu anlegen)
    cur.execute("SELECT balance FROM savings_accounts WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    if result:
        new_savings_balance = result[0] + amount
        cur.execute("UPDATE savings_accounts SET balance = ? WHERE user_id = ?", 
                    (new_savings_balance, user_id))
    else:
        # Sparkonto existiert noch nicht: anlegen mit dem Einzahlungsbetrag
        today_str = datetime.today().strftime("%Y-%m-%d")
        cur.execute("INSERT INTO savings_accounts (user_id, balance, last_interest_date) VALUES (?, ?, ?)", 
                    (user_id, amount, today_str))
    db.commit()
    flash("Einzahlung erfolgreich.", "success")
    return redirect('/savings')

@app.route('/savings/withdraw', methods=['POST'])
def savings_withdraw():
    """Abheben vom Sparkonto (aufs Hauptkonto buchen)."""
    user_id = session.get('user_id')
    amount_str = request.form.get('amount', "0")
    try:
        amount = float(amount_str)
    except:
        amount = 0.0
    if amount <= 0:
        flash("Bitte einen gültigen Betrag eingeben.", "error")
        return redirect('/savings')
    db = get_db()
    cur = db.cursor()
    # Sparkonto-Saldo prüfen
    cur.execute("SELECT balance FROM savings_accounts WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    savings_balance = result[0] if result else 0.0
    if amount > savings_balance:
        flash("Nicht genügend Guthaben auf dem Sparkonto.", "error")
        return redirect('/savings')
    # Sparkonto belasten und Hauptkonto gutschreiben
    new_savings_balance = savings_balance - amount
    cur.execute("UPDATE savings_accounts SET balance = ? WHERE user_id = ?", 
                (new_savings_balance, user_id))
    # Hauptkonto erhöhen
    cur.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    main_balance = cur.fetchone()[0]
    new_main_balance = main_balance + amount
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_main_balance, user_id))
    db.commit()
    flash("Abhebung erfolgreich.", "success")
    return redirect('/savings')



if __name__ == "__main__":
    app.run()
