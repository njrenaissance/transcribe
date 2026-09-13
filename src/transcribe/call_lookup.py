"""Look up a call record from call-inventory's SQLite `calls` table.

Queries `calls` directly via stdlib `sqlite3` rather than depending on the
`wireline` package — see `spec/adr/0005-direct-sqlite-read-of-call-inventory-index.md`.
The table's schema (documented in call-inventory's own
`docs/adr/0005-CDR-FIRST-CALL-RECORD-INDEX.md`) is the data contract between
the two projects; this module hand-writes minimal SQL against it.
"""

import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

from .errors import CallDbError, CallRecordNotFoundError

# The subset of a `calls` row this project's frontmatter needs (see
# spec/adr/0006-yaml-frontmatter-txt-output.md); excludes id/report_path/
# audio_path/audio_stem, which transcribe doesn't use — it already has the
# audio file directly via the manifest/--audiopath entry.
_CALL_COLUMNS = (
    "ref, target, associate, direction, call_start, duration, end_time, "
    "classification, call_progress, language, monitor, text_message"
)


class CallRecord(NamedTuple):
    """One `calls` row's frontmatter-relevant fields, in this project's own shape.

    A local type, not `wireline.CallRecord` — this project never imports
    `wireline`; the two types happen to share field names because both
    describe the same underlying `calls` row.
    """

    ref: str | None
    target: str | None
    associate: str | None
    direction: str | None
    call_start: str | None
    duration: str | None
    end_time: str | None
    classification: str | None
    call_progress: str | None
    language: str | None
    monitor: str | None
    text_message: str | None


def _digits(raw: str) -> str:
    """Reduce a phone number in any format to its bare digits.

    Mirrors call-inventory's own normalization, so a manifest `target` in any
    common format matches the already-normalized value stored in `calls.target`.
    """
    return re.sub(r"\D", "", raw)


def open_call_db(db_path: Path) -> sqlite3.Connection:
    """Open the call-inventory SQLite database read-only, once per run.

    Raises:
        CallDbError: if `db_path` doesn't exist, isn't a readable SQLite file,
            or has no `calls` table.
    """
    if not db_path.exists():
        raise CallDbError(db_path, "file not found")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        conn.execute("SELECT 1 FROM calls LIMIT 1")
    except sqlite3.Error as err:
        conn.close()
        raise CallDbError(db_path, str(err)) from err
    return conn


def find_call_record(conn: sqlite3.Connection, ref: str, target: str) -> CallRecord:
    """Look up the call record matching `ref` (exact) and `target` (digits-normalized, exact).

    On more than one match, the first row (by `id`) wins — `(ref, target)` is
    expected to be unique in practice.

    Raises:
        CallRecordNotFoundError: if no row matches both.
    """
    row = conn.execute(
        f"SELECT {_CALL_COLUMNS} FROM calls WHERE ref = ? AND target = ? ORDER BY id LIMIT 1",
        (ref, _digits(target)),
    ).fetchone()
    if row is None:
        raise CallRecordNotFoundError(ref, target)
    return CallRecord(*row)
