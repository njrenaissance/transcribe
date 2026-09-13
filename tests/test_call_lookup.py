import sqlite3

import pytest

from transcribe.call_lookup import CallRecord, find_call_record, open_call_db
from transcribe.errors import CallDbError, CallRecordNotFoundError


@pytest.fixture
def connect():
    """Open sqlite3 connections that get closed automatically at teardown."""
    connections: list[sqlite3.Connection] = []

    def _connect(db_path):
        conn = sqlite3.connect(db_path)
        connections.append(conn)
        return conn

    yield _connect
    for conn in connections:
        conn.close()


_CALL_ROW = (
    "123",
    "5551234567",
    "5559876543",
    "incoming",
    "2026-08-29 23:05:17",
    "00:00:35",
    "2026-08-29 23:05:52",
    "pertinent",
    "complete",
    "English",
    None,
    None,
)


@pytest.mark.unit
def test_open_call_db_raises_when_file_missing(tmp_path):
    missing = tmp_path / "missing.db"

    with pytest.raises(CallDbError, match="missing.db"):
        open_call_db(missing)


@pytest.mark.unit
def test_open_call_db_raises_when_not_a_sqlite_file(tmp_path):
    not_sqlite = tmp_path / "not_sqlite.db"
    not_sqlite.write_text("not a sqlite file", encoding="utf-8")

    with pytest.raises(CallDbError):
        open_call_db(not_sqlite)


@pytest.mark.unit
def test_open_call_db_raises_when_calls_table_missing(tmp_path):
    db_path = tmp_path / "no_calls_table.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE other (id INTEGER)")
    conn.commit()
    conn.close()

    with pytest.raises(CallDbError):
        open_call_db(db_path)


@pytest.mark.unit
def test_find_call_record_returns_matching_row_with_correct_field_mapping(make_call_db, connect):
    conn = connect(make_call_db([_CALL_ROW]))

    record = find_call_record(conn, ref="123", target="5551234567")

    assert record == CallRecord(
        ref="123",
        target="5551234567",
        associate="5559876543",
        direction="incoming",
        call_start="2026-08-29 23:05:17",
        duration="00:00:35",
        end_time="2026-08-29 23:05:52",
        classification="pertinent",
        call_progress="complete",
        language="English",
        monitor=None,
        text_message=None,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "target",
    [
        pytest.param("5551234567", id="bare_digits"),
        pytest.param("555-123-4567", id="dashed"),
        pytest.param("(555) 123-4567", id="parens_and_spaces"),
    ],
)
def test_find_call_record_matches_target_regardless_of_format(make_call_db, connect, target):
    conn = connect(make_call_db([_CALL_ROW]))

    record = find_call_record(conn, ref="123", target=target)

    assert record.ref == "123"


@pytest.mark.unit
def test_find_call_record_raises_when_no_row_matches(make_call_db, connect):
    conn = connect(make_call_db([_CALL_ROW]))

    with pytest.raises(CallRecordNotFoundError, match="999"):
        find_call_record(conn, ref="999", target="5551234567")


@pytest.mark.unit
def test_find_call_record_takes_first_row_on_ambiguous_match(make_call_db, connect):
    first_row = _CALL_ROW
    second_row = (*_CALL_ROW[:2], "different-associate", *_CALL_ROW[3:])
    conn = connect(make_call_db([first_row, second_row]))

    record = find_call_record(conn, ref="123", target="5551234567")

    assert record.associate == "5559876543"
