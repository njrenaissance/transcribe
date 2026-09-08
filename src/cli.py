"""CLI argument parsing and input-file validation.

Run before any Azure calls are made: rejects a missing file-path argument
list, a nonexistent file, or an unsupported file extension.
"""

import argparse
from pathlib import Path

from errors import MissingFileError, UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = {".mp3", ".wav"}


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the `transcribe` CLI's argument parser."""
    parser = argparse.ArgumentParser(prog="transcribe")
    parser.add_argument("files", nargs="+", help="audio file(s) to transcribe")
    return parser


def parse_args(argv: list[str]) -> list[Path]:
    """Parse CLI arguments into a list of input file paths.

    Exits with code 2 and a usage message on stderr (via argparse) when no
    file arguments are given.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return [Path(file) for file in args.files]


def validate_file(path: Path) -> None:
    """Validate a single input file exists and has a supported extension."""
    if not path.exists():
        raise MissingFileError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(path)


def validate_files(paths: list[Path]) -> None:
    """Validate each input file in turn."""
    for path in paths:
        validate_file(path)
