from dotenv import load_dotenv
import os
from mysql.connector import pooling

load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE")
}

pool = pooling.MySQLConnectionPool(pool_name="pool", pool_size=5, **DB_CONFIG)

def get_conn():
    return pool.get_connection()

def db_read(sql, params=None, single=False):
    conn = get_conn()
    cur = None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        if single:
            row = cur.fetchone()
            print("db_read(single=True) ->", row)
            return row
        rows = cur.fetchall()
        print("db_read(single=False) ->", rows)
        return rows
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()

def db_write(sql, params=None, return_lastrowid=False):
    conn = get_conn()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        print("db_write OK:", sql, params)
        if return_lastrowid:
            return cur.lastrowid
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()
