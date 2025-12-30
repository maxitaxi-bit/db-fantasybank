import logging
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import db_read, db_write

logger = logging.getLogger(__name__)
login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, konto_id: int, email: str, passwort_hash: str, vorname: str = "", nachname: str = ""):
        self.id = konto_id
        self.email = email
        self.password_hash = passwort_hash
        self.vorname = vorname
        self.nachname = nachname

    @staticmethod
    def get_by_id(konto_id: int):
        try:
            row = db_read(
                """
                SELECT konto_id, email, passwort_hash, vorname, nachname
                FROM kunden_konto
                WHERE konto_id = %s
                """,
                (konto_id,),
                single=True
            )
        except Exception:
            logger.exception("Fehler bei User.get_by_id(%s)", konto_id)
            return None

        if not row:
            return None

        return User(
            row["konto_id"],
            row["email"],
            row["passwort_hash"],
            row.get("vorname", ""),
            row.get("nachname", "")
        )

    @staticmethod
    def get_by_email(email: str):
        try:
            row = db_read(
                """
                SELECT konto_id, email, passwort_hash, vorname, nachname
                FROM kunden_konto
                WHERE email = %s
                """,
                (email,),
                single=True
            )
        except Exception:
            logger.exception("Fehler bei User.get_by_email(%s)", email)
            return None

        if not row:
            return None

        return User(
            row["konto_id"],
            row["email"],
            row["passwort_hash"],
            row.get("vorname", ""),
            row.get("nachname", "")
        )


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.get_by_id(int(user_id))
    except Exception:
        logger.exception("load_user(): invalid user_id=%r", user_id)
        return None


def register_user(vorname: str, nachname: str, email: str, password: str, create_default_account: bool = True) -> bool:
    if User.get_by_email(email):
        return False

    pw_hash = generate_password_hash(password)

    try:
        # 1) create kunden_konto
        db_write(
            """
            INSERT INTO kunden_konto (vorname, nachname, email, passwort_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (vorname, nachname, email, pw_hash)
        )

        if create_default_account:
            # 2) fetch inserted id safely
            row = db_read("SELECT LAST_INSERT_ID() AS konto_id", single=True)
            konto_id = row["konto_id"]

            # 3) create default gesamt_konto
            db_write(
                """
                INSERT INTO gesamt_konto (kunden_konto_id, konto_typ, waehrung, saldo)
                VALUES (%s, %s, %s, %s)
                """,
                (konto_id, "Savings", "CHF", 0)
            )

        return True
    except Exception:
        logger.exception("register_user(): Fehler beim Anlegen")
        return False


def authenticate(email: str, password: str):
    user = User.get_by_email(email)
    if not user:
        return None

    if check_password_hash(user.password_hash, password):
        try:
            db_write("UPDATE kunden_konto SET last_login_at = NOW() WHERE konto_id=%s", (user.id,))
        except Exception:
            logger.exception("Konnte last_login_at nicht setzen (nicht kritisch).")
        return user

    return None

