"""transcribe CLI entrypoint."""

import sys
from pathlib import Path

import dotenv

from .cli import parse_args, validate_file
from .credentials import AzureCredentials, load_azure_credentials
from .errors import AppError
from .transcription import transcribe_file
from .transform import transform_result, write_transcript_json


def _process_file(path: Path, credentials: AzureCredentials) -> None:
    """Validate, transcribe, transform, and write output for one input file.

    Raises:
        AppError: if validation, transcription, or transformation fails for `path`.
    """
    validate_file(path)
    result = transcribe_file(path, credentials)
    output = transform_result(result, path)
    write_transcript_json(output, path)


def main(argv: list[str] | None = None) -> int:
    """Parse args, load credentials once, then process each file independently.

    Returns 0 if every file succeeded; 1 if any file failed. Each file's
    failure is isolated and reported without stopping the rest.
    """
    dotenv.load_dotenv()
    try:
        paths = parse_args(sys.argv[1:] if argv is None else argv)
        credentials = load_azure_credentials()
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    had_failure = False
    for path in paths:
        try:
            _process_file(path, credentials)
        except AppError as err:
            print(f"Error: {err}", file=sys.stderr)
            had_failure = True

    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main())
