"""transcribe CLI entrypoint."""

import sys
from pathlib import Path

import dotenv

from .cli import parse_args, validate_file
from .credentials import AzureCredentials, load_azure_credentials
from .errors import AppError
from .transcription import transcribe_file
from .transform import (
    ErrorOutput,
    TranscriptOutput,
    build_error_output,
    has_existing_transcript,
    transform_result,
    write_transcript_json,
)


def _process_file(path: Path, credentials: AzureCredentials, *, clobber: bool) -> bool:
    """Validate, transcribe, transform, and write output for one input file.

    Skips files that already have a successful transcript unless `clobber`
    is set, so a manifest-driven run can be resumed without re-transcribing
    (and re-paying for) files already done. A failure at any stage still
    writes an error-echoing `FILE.json` before the exception propagates, so
    every input file ends up with exactly one output file — a prior failure
    is therefore not treated as done, and is retried on the next run.

    Returns:
        True if the file was skipped because it already had a transcript.

    Raises:
        AppError: if validation, transcription, or transformation fails for `path`.
    """
    if not clobber and has_existing_transcript(path):
        return True

    try:
        validate_file(path)
        result = transcribe_file(path, credentials)
        output: TranscriptOutput | ErrorOutput = transform_result(result, path)
    except AppError as err:
        write_transcript_json(build_error_output(path, err), path)
        raise
    write_transcript_json(output, path)
    return False


def main(argv: list[str] | None = None) -> int:
    """Parse args, load credentials once, then process each file independently.

    Returns 0 if every file succeeded or was skipped as already-transcribed;
    1 if any file failed. Each file's failure is isolated and reported
    without stopping the rest.
    """
    dotenv.load_dotenv()
    try:
        parsed_args = parse_args(sys.argv[1:] if argv is None else argv)
        credentials = load_azure_credentials()
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    had_failure = False
    for path in parsed_args.paths:
        try:
            _process_file(path, credentials, clobber=parsed_args.clobber)
        except AppError as err:
            print(f"Error: {err}", file=sys.stderr)
            had_failure = True

    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main())
