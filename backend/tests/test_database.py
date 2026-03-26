import importlib
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from app import database as database_module


def _reload_database(sqlite_path: Path):
    os.environ["DB_BACKEND"] = "sqlite"
    os.environ["SQLITE_PATH"] = str(sqlite_path)
    return importlib.reload(database_module)


def test_get_conn_uses_sqlite_with_row_factory(tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "chronostock.db"
    db = _reload_database(db_file)

    conn = db.get_conn()
    try:
        assert db.PH == "?"
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_cursor_context_closes_cursor(tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "chronostock.db"
    db = _reload_database(db_file)
    conn = db.get_conn()

    with db.cursor(conn) as cur:
        cur.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        cur.execute("SELECT 1")
    conn.close()


def test_init_db_creates_expected_tables_and_indexes(tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "chronostock.db"
    db = _reload_database(db_file)

    db.init_db()

    conn = sqlite3.connect(db_file)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"users", "watchlist", "password_reset_tokens", "stock_events", "pipeline_runs"}.issubset(tables)

        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_stock_events_ticker_event_date" in indexes
        assert "idx_stock_events_pipeline_run_at" in indexes
        assert "idx_pipeline_runs_name_started_at" in indexes
    finally:
        conn.close()


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_file = tmp_path / "data" / "chronostock.db"
    db = _reload_database(db_file)

    db.init_db()
    db.init_db()

    conn = sqlite3.connect(db_file)
    try:
        # If init_db was not idempotent, this can fail due to schema conflicts.
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        assert row is not None
    finally:
        conn.close()


def test_reload_database_postgres_sets_placeholder_and_uses_connect(monkeypatch) -> None:
    calls = {}

    class FakeConn:
        def __init__(self):
            self.cursor_factory = None

    fake_conn = FakeConn()
    fake_psycopg2 = SimpleNamespace(connect=lambda url: calls.update({"url": url}) or fake_conn)
    fake_extras = SimpleNamespace(RealDictCursor=object())
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)
    monkeypatch.setenv("DB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    db = importlib.reload(database_module)
    monkeypatch.setattr(db, "psycopg2", fake_psycopg2)
    monkeypatch.setattr(db, "DATABASE_URL", "postgres://example")
    monkeypatch.setattr(db, "DB_BACKEND", "postgres")
    monkeypatch.setattr(db.psycopg2, "extras", fake_extras, raising=False)

    conn = db.get_conn()

    assert db.PH == "%s"
    assert conn is fake_conn
    assert calls["url"] == "postgres://example"
    assert conn.cursor_factory is fake_extras.RealDictCursor


def test_cursor_closes_custom_cursor_object() -> None:
    state = {"closed": False}

    class FakeCursor:
        def close(self):
            state["closed"] = True

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    with database_module.cursor(FakeConn()) as cur:
        assert isinstance(cur, FakeCursor)

    assert state["closed"] is True
