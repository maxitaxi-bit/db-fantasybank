from decimal import Decimal
from db import db_tx, db_read

def _get_primary_gesamt_konto_id_for_user(kunden_konto_id: int) -> int:
    row = db_read(
        "SELECT gesamt_konto_id FROM gesamt_konto WHERE kunden_konto_id=%s ORDER BY gesamt_konto_id LIMIT 1",
        (kunden_konto_id,),
        single=True,
    )
    if not row:
        raise RuntimeError("Kein gesamt_konto für User gefunden.")
    return int(row["gesamt_konto_id"])

def get_balance(kunden_konto_id: int) -> tuple[Decimal, str]:
    gid = _get_primary_gesamt_konto_id_for_user(kunden_konto_id)
    row = db_read("SELECT saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s", (gid,), single=True)
    return Decimal(row["saldo"]), row["waehrung"]

def deposit(kunden_konto_id: int, amount: Decimal, waehrung: str = "CHF", beschreibung: str = "Deposit"):
    if amount <= 0:
        raise ValueError("Betrag muss > 0 sein")

    gid = _get_primary_gesamt_konto_id_for_user(kunden_konto_id)

    with db_tx() as (conn, curd, cur):
        # lock row
        curd.execute("SELECT saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s FOR UPDATE", (gid,))
        row = curd.fetchone()
        if not row:
            raise RuntimeError("gesamt_konto nicht gefunden")

        if row["waehrung"] != waehrung:
            raise ValueError("Währung passt nicht zum Konto")

        cur.execute("UPDATE gesamt_konto SET saldo = saldo + %s WHERE gesamt_konto_id=%s", (amount, gid))

        cur.execute(
            """INSERT INTO transaktion (gesamt_konto_id, typ, betrag, waehrung, gebuehr, gegenkonto_ref, beschreibung)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (gid, "DEPOSIT", amount, waehrung, 0, None, beschreibung),
        )

def withdraw(kunden_konto_id: int, amount: Decimal, waehrung: str = "CHF", beschreibung: str = "Withdrawal"):
    if amount <= 0:
        raise ValueError("Betrag muss > 0 sein")

    gid = _get_primary_gesamt_konto_id_for_user(kunden_konto_id)

    with db_tx() as (conn, curd, cur):
        curd.execute("SELECT saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s FOR UPDATE", (gid,))
        row = curd.fetchone()
        if not row:
            raise RuntimeError("gesamt_konto nicht gefunden")

        if row["waehrung"] != waehrung:
            raise ValueError("Währung passt nicht zum Konto")

        saldo = Decimal(row["saldo"])
        if saldo < amount:
            raise ValueError("Nicht genügend Guthaben")

        cur.execute("UPDATE gesamt_konto SET saldo = saldo - %s WHERE gesamt_konto_id=%s", (amount, gid))
        cur.execute(
            """INSERT INTO transaktion (gesamt_konto_id, typ, betrag, waehrung, gebuehr, gegenkonto_ref, beschreibung)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (gid, "WITHDRAWAL", amount, waehrung, 0, None, beschreibung),
        )

def transfer(kunden_konto_id_from: int, to_email: str, amount: Decimal, waehrung: str = "CHF", fee: Decimal = Decimal("0.00")):
    if amount <= 0:
        raise ValueError("Betrag muss > 0 sein")

   to_row = db_read(
        "SELECT konto_id FROM kunden_konto WHERE LOWER(email)=LOWER(%s)",
        (to_email.strip(),),
        single=True
    )

    if not to_row:
        raise ValueError("Empfänger existiert nicht")

    kid_to = int(to_row["konto_id"])
    gid_from = _get_primary_gesamt_konto_id_for_user(kunden_konto_id_from)
    gid_to = _get_primary_gesamt_konto_id_for_user(kid_to)

    total = amount + fee

    with db_tx() as (conn, curd, cur):
        # lock both accounts in a stable order (avoid deadlocks)
        first, second = sorted([gid_from, gid_to])

        curd.execute("SELECT gesamt_konto_id, saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s FOR UPDATE", (first,))
        _ = curd.fetchone()
        curd.execute("SELECT gesamt_konto_id, saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s FOR UPDATE", (second,))
        _ = curd.fetchone()

        curd.execute("SELECT saldo, waehrung FROM gesamt_konto WHERE gesamt_konto_id=%s", (gid_from,))
        from_row = curd.fetchone()
        if from_row["waehrung"] != waehrung:
            raise ValueError("Währung passt nicht zum Senderkonto")

        if Decimal(from_row["saldo"]) < total:
            raise ValueError("Nicht genügend Guthaben")

        # debit sender
        cur.execute("UPDATE gesamt_konto SET saldo = saldo - %s WHERE gesamt_konto_id=%s", (total, gid_from))
        # credit receiver
        cur.execute("UPDATE gesamt_konto SET saldo = saldo + %s WHERE gesamt_konto_id=%s", (amount, gid_to))

        # log transactions
        cur.execute(
            """INSERT INTO transaktion (gesamt_konto_id, typ, betrag, waehrung, gebuehr, gegenkonto_ref, beschreibung)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (gid_from, "TRANSFER", amount, waehrung, fee, f"to:{to_email}", "Transfer out"),
        )
        cur.execute(
            """INSERT INTO transaktion (gesamt_konto_id, typ, betrag, waehrung, gebuehr, gegenkonto_ref, beschreibung)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (gid_to, "TRANSFER", amount, waehrung, 0, f"from:{kunden_konto_id_from}", "Transfer in"),
        )
