"""Shared pytest configuration."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pytest

_CALLS_SCHEMA = """
CREATE TABLE calls (
    id INTEGER PRIMARY KEY,
    ref TEXT,
    target TEXT,
    associate TEXT,
    direction TEXT,
    call_start TEXT,
    duration TEXT,
    end_time TEXT,
    classification TEXT,
    call_progress TEXT,
    language TEXT,
    monitor TEXT,
    text_message TEXT
)
"""
_CALLS_INSERT = (
    "INSERT INTO calls (ref, target, associate, direction, call_start, duration, end_time, "
    "classification, call_progress, language, monitor, text_message) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def pytest_configure(config):
    """Show live log output at INFO under `pytest -v`, unless a log-cli level was set explicitly."""
    if config.option.verbose > 0 and config.option.log_cli_level is None:
        config.option.log_cli_level = "INFO"


@pytest.fixture
def make_call_db(tmp_path):
    """Factory fixture: build a SQLite file with a `calls` table holding the given rows.

    Each row is a 12-tuple in `calls` column order: `ref, target, associate,
    direction, call_start, duration, end_time, classification, call_progress,
    language, monitor, text_message`.
    """

    def _make(rows: Iterable[tuple[object, ...]] = (), name: str = "calls.db") -> Path:
        db_path = tmp_path / name
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(_CALLS_SCHEMA)
            conn.executemany(_CALLS_INSERT, rows)
            conn.commit()
        finally:
            conn.close()
        return db_path

    return _make
