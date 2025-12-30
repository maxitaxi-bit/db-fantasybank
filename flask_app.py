from flask import Flask, redirect, render_template, request, url_for
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
from db import db_read, db_write
from auth import login_manager, authenticate, register_user
from flask_login import login_user, logout_user, login_required, current_user
import logging

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
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)

@app.post('/update_server')
def webhook():
    x_hub_signature = request.headers.get('X-Hub-Signature')
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo('./mysite')
        origin = repo.remotes.origin
        origin.pull()
        return 'Updated PythonAnywhere successfully', 200
    return 'Unathorized', 401

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
        mode="login"
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
        mode="register"
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/users", methods=["GET"])
@login_required
def users():
    rows = db_read("SELECT konto_id, vorname, nachname, email FROM kunden_konto ORDER BY nachname, vorname")
    return render_template("users.html", users=rows)

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "GET":
        todos = db_read("SELECT id, content, due FROM todos WHERE kunden_konto_id=%s ORDER BY due", (current_user.id,))
        return render_template("main_page.html", todos=todos)

    content = request.form["contents"]
    due = request.form["due_at"]
    db_write("INSERT INTO todos (kunden_konto_id, content, due) VALUES (%s, %s, %s)", (current_user.id, content, due))
    return redirect(url_for("index"))

@app.post("/complete")
@login_required
def complete():
    todo_id = request.form.get("id")
    db_write("DELETE FROM todos WHERE kunden_konto_id=%s AND id=%s", (current_user.id, todo_id))
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
