"""CLI argument parsing and input-file validation.

Run before any Azure calls are made: rejects an invalid input-mode
combination, a nonexistent call-record database, a nonexistent file, or an
unsupported file extension.
"""

import argparse
import csv
import os
from pathlib import Path
from typing import NamedTuple

from .errors import ManifestError, MissingFileError, UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = {".mp3", ".wav"}
_MANIFEST_COLUMNS = ("ref", "target", "audio_path")
_CALL_DB_ENV_VAR = "CALL_DB_PATH"


class ManifestEntry(NamedTuple):
    """One input file plus the `ref`/`target` key its call record is looked up by.

    Field names match the manifest CSV's own columns (`ref`, `target`,
    `audio_path`). `audio_path` is a local file path or a URL; only the
    local-filesystem case is handled today (see `spec/adr/0006-yaml-frontmatter-txt-output.md`).
    The CLI's single-file flag for the same value is spelled `--audiopath`.
    """

    ref: str
    target: str
    audio_path: str


class ParsedArgs(NamedTuple):
    """Resolved input entries and run options parsed from the CLI arguments."""

    entries: list[ManifestEntry]
    clobber: bool
    call_db: Path


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the `transcribe` CLI's argument parser."""
    parser = argparse.ArgumentParser(prog="transcribe")
    parser.add_argument(
        "--manifest",
        type=Path,
        help=f"CSV file with '{'/'.join(_MANIFEST_COLUMNS)}' columns (batch mode)",
    )
    parser.add_argument("--audiopath", help="a single audio file path or URL (use with --ref and --target)")
    parser.add_argument("--ref", help="the call's reference number, for --audiopath")
    parser.add_argument("--target", help="the call's target phone number, for --audiopath")
    parser.add_argument(
        "--call-db",
        type=Path,
        default=_default_call_db(),
        help=f"path to call-inventory's SQLite index (default: ${_CALL_DB_ENV_VAR})",
    )
    parser.add_argument(
        "--clobber",
        action="store_true",
        help="reprocess files that already have a FILE-transcript.txt transcript instead of skipping them",
    )
    return parser


def _default_call_db() -> Path | None:
    value = os.environ.get(_CALL_DB_ENV_VAR)
    return Path(value) if value else None


def parse_args(argv: list[str]) -> ParsedArgs:
    """Parse CLI arguments into resolved manifest entries and run options.

    Exactly one of `--manifest` or the `--audiopath`/`--ref`/`--target` triple
    must be given; the triple must be given together or not at all. Exits
    with code 2 and a usage message on stderr (via argparse) for any other
    combination, or when `--call-db` is missing.

    Raises:
        ManifestError: if `--manifest` is given but can't be read or is malformed.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    single_entry_flags = (args.audiopath, args.ref, args.target)
    if args.manifest is not None and any(single_entry_flags):
        parser.error("--manifest cannot be combined with --audiopath/--ref/--target")
    if any(single_entry_flags) and not all(single_entry_flags):
        parser.error("--audiopath, --ref, and --target must all be given together")
    if args.manifest is None and not all(single_entry_flags):
        parser.error("no input given: pass --manifest or --audiopath/--ref/--target")
    if args.call_db is None:
        parser.error(f"--call-db is required (or set {_CALL_DB_ENV_VAR})")

    entries = (
        read_manifest(args.manifest)
        if args.manifest is not None
        else [ManifestEntry(ref=args.ref, target=args.target, audio_path=args.audiopath)]
    )
    return ParsedArgs(entries=entries, clobber=args.clobber, call_db=args.call_db)


def read_manifest(path: Path) -> list[ManifestEntry]:
    """Read a CSV manifest's `ref`, `target`, and `audio_path` columns into typed entries.

    Raises:
        ManifestError: if the file doesn't exist, is missing a required
            column, or a row has an empty value in any required column.
    """
    try:
        with path.open(newline="", encoding="utf-8-sig") as manifest_file:
            reader = csv.DictReader(manifest_file)
            fieldnames = reader.fieldnames or []
            missing = [column for column in _MANIFEST_COLUMNS if column not in fieldnames]
            if missing:
                raise ManifestError(path, f"missing column(s): {', '.join(missing)}")
            rows = list(reader)
    except OSError as err:
        raise ManifestError(path, str(err)) from err

    return [_manifest_entry(path, row) for row in rows]


def _manifest_entry(path: Path, row: dict[str, str]) -> ManifestEntry:
    """Build one `ManifestEntry` from a CSV row, or raise `ManifestError` if empty."""
    values = {column: row[column] for column in _MANIFEST_COLUMNS}
    empty = [column for column, value in values.items() if not value]
    if empty:
        raise ManifestError(path, f"a row has an empty '{'/'.join(empty)}' value")
    return ManifestEntry(ref=values["ref"], target=values["target"], audio_path=values["audio_path"])


def validate_file(path: Path) -> None:
    """Validate a single input file exists and has a supported extension."""
    if not path.exists():
        raise MissingFileError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(path)
