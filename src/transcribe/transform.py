"""Transform Azure fast-transcription results into this project's output schema, and write them to disk."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from .errors import AppError, EmptyTranscriptionResultError, OutputWriteError
from .transcription import DEFAULT_LOCALE


class Segment(TypedDict):
    """One timestamped transcript segment in the output schema."""

    start: float
    end: float
    text: str


class TranscriptOutput(TypedDict):
    """The output schema written to `FILE.json` on success."""

    source_file: str
    language: str
    duration_seconds: float
    segments: list[Segment]


class ErrorOutput(TypedDict):
    """The output schema written to `FILE.json` when processing `source_file` fails.

    Written instead of `TranscriptOutput` so every input file ends up with
    exactly one output file, auditable from the output folder alone even when
    the run's stderr wasn't captured (see issue #18).
    """

    source_file: str
    error: str


def transform_result(
    result: dict[str, Any],
    source_path: Path,
    requested_locale: str = DEFAULT_LOCALE,
) -> TranscriptOutput:
    """Transform a fast-transcription result into this project's output schema.

    Args:
        result: the parsed fast-transcription result JSON.
        source_path: the input audio file the result belongs to.
        requested_locale: the locale used as `language` when a phrase has none.

    Raises:
        EmptyTranscriptionResultError: if the result has no phrases (no usable transcript).
    """
    phrases = result.get("phrases") or []
    if not phrases:
        raise EmptyTranscriptionResultError(source_path)

    segments: list[Segment] = sorted(
        (
            Segment(
                start=phrase["offsetMilliseconds"] / 1000,
                end=(phrase["offsetMilliseconds"] + phrase["durationMilliseconds"]) / 1000,
                text=phrase["text"],
            )
            for phrase in phrases
        ),
        key=lambda segment: segment["start"],
    )

    return TranscriptOutput(
        source_file=source_path.name,
        language=phrases[0].get("locale") or requested_locale,
        duration_seconds=result["durationMilliseconds"] / 1000,
        segments=segments,
    )


def build_error_output(source_path: Path, error: AppError) -> ErrorOutput:
    """Build the error-echoing output written for `source_path` when processing it fails."""
    return ErrorOutput(source_file=source_path.name, error=str(error))


def output_path(source_path: Path) -> Path:
    """The sibling `FILE.json` path that `source_path`'s output is written to."""
    return source_path.with_name(source_path.name + ".json")


def has_existing_transcript(source_path: Path) -> bool:
    """Whether `source_path` already has a successful transcript on disk.

    Used to resume a run without re-transcribing files that already
    succeeded. An error-echoing output (or an unreadable/corrupt file) does
    not count as done, so a prior failure is retried on the next run.
    """
    destination = output_path(source_path)
    if not destination.exists():
        return False
    try:
        with destination.open(encoding="utf-8") as existing_file:
            existing_output = json.load(existing_file)
    except (OSError, json.JSONDecodeError):
        return False
    return "error" not in existing_output


def write_transcript_json(output: TranscriptOutput | ErrorOutput, source_path: Path) -> Path:
    """Atomically write `output` to `FILE.json`, a sibling of `source_path`.

    Writes to a temp file in the same directory and renames it into place with
    `os.replace`, so a mid-write failure never leaves a partial/corrupt destination file.

    Raises:
        OutputWriteError: if the write or the atomic rename fails.
    """
    destination = output_path(source_path)
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(output, tmp_file, indent=2)
        os.replace(tmp_path, destination)
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise OutputWriteError(destination, str(err)) from err
    return destination
