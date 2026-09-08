"""transcribe CLI entrypoint."""

import sys

from cli import parse_args, validate_files
from errors import AppError


def main(argv: list[str] | None = None) -> int:
    """Parse and validate CLI input; return the process exit code."""
    try:
        paths = parse_args(sys.argv[1:] if argv is None else argv)
        validate_files(paths)
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
