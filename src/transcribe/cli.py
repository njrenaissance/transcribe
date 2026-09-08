"""CLI argument parsing and input-file validation.

Run before any Azure calls are made: rejects a missing file-path argument
list, a nonexistent file, or an unsupported file extension.
"""

import argparse
import csv
from pathlib import Path
from typing import NamedTuple

from .errors import ManifestError, MissingFileError, UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = {".mp3", ".wav"}
_MANIFEST_URL_COLUMN = "url"


class ParsedArgs(NamedTuple):
    """Resolved input file paths and run options parsed from the CLI arguments."""

    paths: list[Path]
    clobber: bool


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the `transcribe` CLI's argument parser."""
    parser = argparse.ArgumentParser(prog="transcribe")
    parser.add_argument("files", nargs="*", help="audio file(s) to transcribe")
    parser.add_argument(
        "--manifest",
        type=Path,
        help=f"CSV file with a '{_MANIFEST_URL_COLUMN}' column of audio file paths",
    )
    parser.add_argument(
        "--clobber",
        action="store_true",
        help="reprocess files that already have a FILE.json transcript instead of skipping them",
    )
    return parser


def parse_args(argv: list[str]) -> ParsedArgs:
    """Parse CLI arguments into resolved input file paths and run options.

    Exits with code 2 and a usage message on stderr (via argparse) when
    neither file arguments nor `--manifest` are given.

    Raises:
        ManifestError: if `--manifest` is given but can't be read or is malformed.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.files and args.manifest is None:
        parser.error("no files given: pass FILE arguments and/or --manifest")

    paths = [Path(file) for file in args.files]
    if args.manifest is not None:
        paths.extend(read_manifest(args.manifest))
    return ParsedArgs(paths=paths, clobber=args.clobber)


def read_manifest(path: Path) -> list[Path]:
    """Read a CSV manifest's `url` column into a list of file paths.

    Raises:
        ManifestError: if the file doesn't exist, has no `url` column, or a
            row's `url` value is empty.
    """
    try:
        with path.open(newline="", encoding="utf-8-sig") as manifest_file:
            reader = csv.DictReader(manifest_file)
            if reader.fieldnames is None or _MANIFEST_URL_COLUMN not in reader.fieldnames:
                raise ManifestError(path, f"missing '{_MANIFEST_URL_COLUMN}' column")
            urls = [row[_MANIFEST_URL_COLUMN] for row in reader]
    except OSError as err:
        raise ManifestError(path, str(err)) from err

    if any(not url for url in urls):
        raise ManifestError(path, f"a row has an empty '{_MANIFEST_URL_COLUMN}' value")
    return [Path(url) for url in urls]


def validate_file(path: Path) -> None:
    """Validate a single input file exists and has a supported extension."""
    if not path.exists():
        raise MissingFileError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(path)
