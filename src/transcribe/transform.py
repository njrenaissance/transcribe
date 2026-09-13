"""Transform Azure fast-transcription results + a call record into TEXT-with-frontmatter output."""

import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import yaml

from .call_lookup import CallRecord
from .errors import AppError, EmptyTranscriptionResultError, OutputWriteError

# A `time.strftime` format string (https://docs.python.org/3/library/time.html#time.strftime),
# configurable via --timestamp-format. Each segment's start/end is rendered with
# `time.strftime(timestamp_format, time.gmtime(seconds))` -- `seconds` is elapsed
# time from the start of the call, not a wall-clock time, so this reads as
# hours/minutes/seconds *since the call began*.
DEFAULT_TIMESTAMP_FORMAT = "%H:%M:%S"

# The directives `time.strftime` documents support, per
# https://docs.python.org/3/library/time.html#time.strftime -- used to validate
# --timestamp-format portably (see `validate_timestamp_format`).
_VALID_STRFTIME_DIRECTIVES = frozenset("aAbBcdHIjmMpSUwWxXyYzZ%")

_CALL_RECORD_FIELDS = (
    "ref",
    "target",
    "associate",
    "direction",
    "call_start",
    "duration",
    "end_time",
    "classification",
    "call_progress",
    "language",
    "monitor",
    "text_message",
)
Frontmatter = dict[str, str | int | float | bool | list[str] | None]

# Thresholds for `needs_review`, validated against a 16-call sample with real
# human-transcribed references (issue: quality scoring). Every call that a
# human transcript confirmed was well-captured had coverage_ratio >= 0.42 and
# word_density >= 1.81; every silently-near-empty "success" had at least one
# of these below the cutoffs. Not complete: a transcript with normal coverage
# and density but wrong/repetitive content (e.g. one phrase mis-recognized as
# a repeated stock phrase) can still slip through — this catches sparse or
# gappy output, not plausible-but-incorrect output.
_MIN_COVERAGE_RATIO = 0.30
_MIN_WORD_DENSITY = 1.0


class Segment(TypedDict):
    """One timestamped transcript segment used to render the body."""

    start: float
    end: float
    text: str
    speaker: int | None


@dataclass(frozen=True)
class TranscriptOutput:
    """What gets written to `FILE-transcript.txt` on success: YAML frontmatter + a plain-text body."""

    frontmatter: Frontmatter
    body: str


@dataclass(frozen=True)
class ErrorOutput:
    """What gets written to `FILE-transcript.txt` on a per-file failure (ADR-0004): frontmatter only."""

    frontmatter: Frontmatter  # always includes "error"


def _base_frontmatter(source_path: Path, call_record: CallRecord | None) -> Frontmatter:
    """The call-record-derived frontmatter fields, in a fixed key order.

    `source_file` always comes from `source_path` (kept for audit-trail
    continuity with the prior JSON schema). Every other field comes from
    `call_record` when a lookup succeeded, else `None` — e.g. a
    `CallRecordNotFoundError` has no record to draw from.
    """
    values = call_record._asdict() if call_record is not None else {}
    frontmatter: Frontmatter = {"source_file": source_path.name}
    frontmatter.update({field_name: values.get(field_name) for field_name in _CALL_RECORD_FIELDS})
    return frontmatter


def validate_timestamp_format(timestamp_format: str) -> None:
    """Validate that `timestamp_format` uses only documented `time.strftime` directives.

    Checked against the directive set documented at
    https://docs.python.org/3/library/time.html#time.strftime rather than by calling
    `time.strftime` itself: that delegates to the platform C library, and glibc (Linux)
    silently passes an unrecognized directive like "%Q" straight through instead of
    raising, while Windows' CRT rejects it -- so calling it can't be relied on to catch
    an invalid format the same way on every platform this runs on.

    Raises:
        ValueError: if `timestamp_format` contains a directive outside that set, or a
            trailing `%` with no directive character after it.
    """
    for match in re.finditer(r"%(.?)", timestamp_format):
        directive = match.group(1)
        if directive not in _VALID_STRFTIME_DIRECTIVES:
            raise ValueError(f"Invalid timestamp format directive: '%{directive}'")


def _format_timestamp(seconds: float, timestamp_format: str) -> str:
    """Render a segment timestamp using `timestamp_format`, relative to the start of the call."""
    return time.strftime(timestamp_format, time.gmtime(seconds))


def _render_segment(segment: Segment, timestamp_format: str) -> str:
    """Render one segment as `<start> - <end> Speaker N: text`, or without a speaker label if unknown."""
    start = _format_timestamp(segment["start"], timestamp_format)
    end = _format_timestamp(segment["end"], timestamp_format)
    timing = f"{start} - {end}"
    if segment["speaker"] is None:
        return f"{timing} {segment['text']}"
    return f"{timing} Speaker {segment['speaker']}: {segment['text']}"


def _render_body(segments: list[Segment], timestamp_format: str) -> str:
    """Render timestamped, speaker-labeled segments as a human-readable plain-text transcript body."""
    return "\n".join(_render_segment(segment, timestamp_format) for segment in segments)


def _quality_signals(phrases: list[dict[str, Any]], segments: list[Segment], audio_duration_ms: int) -> Frontmatter:
    """Cheap, reference-free signals for flagging a transcript as worth a human's second look.

    `coverage_ratio` is the fraction of the audio actually spanned by a
    phrase (low → Azure recognized speech in only part of the call);
    `word_density` is words per covered second (low → sparse, likely
    truncated recognition even where a phrase exists); `average_confidence`
    is Azure's own mean per-phrase confidence, informational only pending
    threshold calibration against more real data. `needs_review` is set
    when either validated threshold is crossed (see `_MIN_COVERAGE_RATIO`/
    `_MIN_WORD_DENSITY`) — a` False` value is not a quality guarantee, just
    the absence of this particular warning sign.
    """
    audio_duration_s = audio_duration_ms / 1000
    covered_s = sum(segment["end"] - segment["start"] for segment in segments)
    word_count = sum(len(segment["text"].split()) for segment in segments)
    coverage_ratio = covered_s / audio_duration_s if audio_duration_s else 0.0
    word_density = word_count / covered_s if covered_s else 0.0
    confidences = [confidence for phrase in phrases if (confidence := phrase.get("confidence")) is not None]
    average_confidence = sum(confidences) / len(confidences) if confidences else None
    needs_review = coverage_ratio < _MIN_COVERAGE_RATIO or word_density < _MIN_WORD_DENSITY
    return {
        "average_confidence": round(average_confidence, 3) if average_confidence is not None else None,
        "coverage_ratio": round(coverage_ratio, 3),
        "word_density": round(word_density, 3),
        "needs_review": needs_review,
    }


def _detected_locales(phrases: list[dict[str, Any]]) -> list[str]:
    """Distinct locales Azure's language identification reported across phrases, sorted.

    Azure's language ID (see `transcription.CANDIDATE_LOCALES`, issue #21) is
    forced-choice among the candidate locales sent — it never emits an
    explicit "unidentified" state. A phrase with no `locale` just contributes
    nothing here rather than failing the whole transcript.
    """
    return sorted({locale for phrase in phrases if (locale := phrase.get("locale"))})


def transform_result(
    result: dict[str, Any],
    source_path: Path,
    call_record: CallRecord,
    timestamp_format: str = DEFAULT_TIMESTAMP_FORMAT,
) -> TranscriptOutput:
    """Transform a fast-transcription result and its call record into this project's output schema.

    Args:
        result: the parsed fast-transcription result JSON.
        source_path: the input audio file the result belongs to.
        call_record: the matching call record, used to populate the frontmatter.
        timestamp_format: a `time.strftime` format string for each segment's
            start/end, relative to the start of the call.

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
                speaker=phrase.get("speaker"),
            )
            for phrase in phrases
        ),
        key=lambda segment: segment["start"],
    )
    audio_duration_ms = result["durationMilliseconds"]
    frontmatter = _base_frontmatter(source_path, call_record)
    frontmatter["audio_duration"] = audio_duration_ms
    frontmatter["detected_locales"] = _detected_locales(phrases)
    frontmatter.update(_quality_signals(phrases, segments, audio_duration_ms))
    return TranscriptOutput(frontmatter=frontmatter, body=_render_body(segments, timestamp_format))


def build_error_output(source_path: Path, error: AppError, call_record: CallRecord | None = None) -> ErrorOutput:
    """Build the error-echoing output written for `source_path` when processing it fails.

    Carries any call-record fields already found before the failure (e.g. a
    transcription error after a successful lookup), or all-`None` fields when
    the lookup itself is what failed.
    """
    frontmatter = _base_frontmatter(source_path, call_record)
    frontmatter["error"] = str(error)
    return ErrorOutput(frontmatter=frontmatter)


def output_path(source_path: Path, ref: str, target: str, destination: Path | None = None) -> Path:
    """The transcript output path for `source_path`.

    Co-located next to `source_path` by default: `FILE-transcript.txt`
    (`source_path.stem + "-transcript.txt"`). When `destination` is given,
    every transcript is written there instead, named
    `<ref>-<target>-<stem>-transcript.txt` so files sharing a stem from
    different calls don't collide in one shared directory.
    """
    if destination is not None:
        return destination / f"{ref}-{target}-{source_path.stem}-transcript.txt"
    return source_path.with_name(f"{source_path.stem}-transcript.txt")


_FRONTMATTER_DELIMITER = "---\n"


def _read_frontmatter(path: Path) -> Frontmatter:
    """Parse the YAML frontmatter block from an existing `FILE-transcript.txt`.

    Raises:
        ValueError: if the file has no frontmatter block.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_FRONTMATTER_DELIMITER):
        raise ValueError(f"{path} has no frontmatter block")
    _, _, rest = text.partition(_FRONTMATTER_DELIMITER)
    block, _, _ = rest.partition(f"\n{_FRONTMATTER_DELIMITER}")
    loaded = yaml.safe_load(block)
    return loaded if isinstance(loaded, dict) else {}


def has_existing_transcript(source_path: Path, ref: str, target: str, destination: Path | None = None) -> bool:
    """Whether `source_path` already has a successful transcript on disk.

    Used to resume a run without re-transcribing files that already
    succeeded. An error-echoing output (or a missing/unreadable/corrupt/malformed
    file) does not count as done, so a prior failure is retried on the next run.
    """
    output_file = output_path(source_path, ref, target, destination)
    if not output_file.exists():
        return False
    try:
        frontmatter = _read_frontmatter(output_file)
    except (OSError, ValueError, yaml.YAMLError):
        return False
    return "error" not in frontmatter


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    """Force multi-line string values (e.g. `text_message`) into block-literal style."""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)


yaml.add_representer(str, _str_representer, Dumper=yaml.SafeDumper)


def _render_output(output: TranscriptOutput | ErrorOutput) -> str:
    """Render `output` as `---`-delimited YAML frontmatter, plus the body for a success."""
    frontmatter_yaml = yaml.safe_dump(output.frontmatter, sort_keys=False, allow_unicode=True)
    body = output.body if isinstance(output, TranscriptOutput) else ""
    return f"{_FRONTMATTER_DELIMITER}{frontmatter_yaml}{_FRONTMATTER_DELIMITER}{body}"


def write_transcript_txt(
    output: TranscriptOutput | ErrorOutput,
    source_path: Path,
    ref: str,
    target: str,
    destination: Path | None = None,
) -> Path:
    """Atomically write `output` to its transcript path (see `output_path`).

    Creates `destination` first if it doesn't exist yet. Writes to a temp
    file in the same directory and renames it into place with `os.replace`,
    so a mid-write failure never leaves a partial/corrupt destination file.

    Raises:
        OutputWriteError: if the write or the atomic rename fails.
    """
    output_file = output_path(source_path, ref, target, destination)
    text = _render_output(output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=output_file.parent, prefix=f".{output_file.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
        os.replace(tmp_path, output_file)
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise OutputWriteError(output_file, str(err)) from err
    return output_file
