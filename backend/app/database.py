import os
import sqlite3
from contextlib import contextmanager

DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite")  # "sqlite" | "postgres"

if DB_BACKEND == "postgres":
    import psycopg2
    import psycopg2.extras
    DATABASE_URL = os.environ["DATABASE_URL"]
    PH = "%s"  # psycopg2 placeholder
else:
    SQLITE_PATH = os.environ.get("SQLITE_PATH", "./data/chronostock.db")
    PH = "?"   # sqlite3 placeholder


def get_conn():
    if DB_BACKEND == "postgres":
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
    else:
        os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cursor(conn):
    """Unified cursor context manager for both sqlite3 and psycopg2."""
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def init_db() -> None:
    conn = get_conn()
    try:
        with cursor(conn) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, ticker)
                )
            """)
        conn.commit()
    finally:
        conn.close()
