"""transcribe CLI entrypoint."""

import sqlite3
import sys
from pathlib import Path

import dotenv

from .call_lookup import CallRecord, find_call_record, open_call_db
from .cli import ManifestEntry, parse_args, validate_file
from .credentials import AzureCredentials, load_azure_credentials
from .errors import AppError
from .transcription import transcribe_file
from .transform import (
    ErrorOutput,
    TranscriptOutput,
    build_error_output,
    has_existing_transcript,
    transform_result,
    write_transcript_txt,
)


def _process_entry(
    entry: ManifestEntry,
    credentials: AzureCredentials,
    call_db: sqlite3.Connection,
    *,
    clobber: bool,
) -> bool:
    """Validate, look up the call record, transcribe, transform, and write output for one entry.

    Looks up the call record before calling Azure, so a `ref`/`target` that
    matches no record fails fast without spending an Azure call. A failure at
    any stage still writes an error-echoing `FILE-transcript.txt` (carrying
    any call-record fields already found) before the exception propagates.

    Returns:
        True if the file was skipped because it already had a transcript.

    Raises:
        AppError: if validation, lookup, transcription, or transformation fails.
    """
    path = Path(entry.audio_path)
    if not clobber and has_existing_transcript(path):
        return True

    call_record: CallRecord | None = None
    try:
        validate_file(path)
        call_record = find_call_record(call_db, entry.ref, entry.target)
        result = transcribe_file(path, credentials)
        output: TranscriptOutput | ErrorOutput = transform_result(result, path, call_record)
    except AppError as err:
        write_transcript_txt(build_error_output(path, err, call_record), path)
        raise
    write_transcript_txt(output, path)
    return False


def main(argv: list[str] | None = None) -> int:
    """Parse args, load credentials and the call-record DB once, then process each entry.

    Returns 0 if every entry succeeded or was skipped as already-transcribed;
    1 if any entry failed. Each entry's failure is isolated and reported
    without stopping the rest.
    """
    dotenv.load_dotenv()
    try:
        parsed_args = parse_args(sys.argv[1:] if argv is None else argv)
        credentials = load_azure_credentials()
        call_db = open_call_db(parsed_args.call_db)
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    had_failure = False
    try:
        for entry in parsed_args.entries:
            try:
                _process_entry(entry, credentials, call_db, clobber=parsed_args.clobber)
            except AppError as err:
                print(f"Error: {err}", file=sys.stderr)
                had_failure = True
    finally:
        call_db.close()

    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main())
