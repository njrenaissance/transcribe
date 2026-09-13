"""Transform Azure fast-transcription results + a call record into TEXT-with-frontmatter output."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import yaml

from .call_lookup import CallRecord
from .errors import AppError, EmptyTranscriptionResultError, OutputWriteError

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
Frontmatter = dict[str, str | None]


class Segment(TypedDict):
    """One timestamped transcript segment used to render the body."""

    start: float
    end: float
    text: str


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


def _render_body(segments: list[Segment]) -> str:
    """Render timestamped segments as a human-readable plain-text transcript body."""
    return "\n".join(f"[{segment['start']:.1f}-{segment['end']:.1f}] {segment['text']}" for segment in segments)


def transform_result(result: dict[str, Any], source_path: Path, call_record: CallRecord) -> TranscriptOutput:
    """Transform a fast-transcription result and its call record into this project's output schema.

    Args:
        result: the parsed fast-transcription result JSON.
        source_path: the input audio file the result belongs to.
        call_record: the matching call record, used to populate the frontmatter.

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
    return TranscriptOutput(frontmatter=_base_frontmatter(source_path, call_record), body=_render_body(segments))


def build_error_output(source_path: Path, error: AppError, call_record: CallRecord | None = None) -> ErrorOutput:
    """Build the error-echoing output written for `source_path` when processing it fails.

    Carries any call-record fields already found before the failure (e.g. a
    transcription error after a successful lookup), or all-`None` fields when
    the lookup itself is what failed.
    """
    frontmatter = _base_frontmatter(source_path, call_record)
    frontmatter["error"] = str(error)
    return ErrorOutput(frontmatter=frontmatter)


def output_path(source_path: Path) -> Path:
    """The sibling `FILE-transcript.txt` path that `source_path`'s output is written to."""
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


def has_existing_transcript(source_path: Path) -> bool:
    """Whether `source_path` already has a successful transcript on disk.

    Used to resume a run without re-transcribing files that already
    succeeded. An error-echoing output (or a missing/unreadable/corrupt/malformed
    file) does not count as done, so a prior failure is retried on the next run.
    """
    destination = output_path(source_path)
    if not destination.exists():
        return False
    try:
        frontmatter = _read_frontmatter(destination)
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


def write_transcript_txt(output: TranscriptOutput | ErrorOutput, source_path: Path) -> Path:
    """Atomically write `output` to `FILE-transcript.txt`, a sibling of `source_path`.

    Writes to a temp file in the same directory and renames it into place with
    `os.replace`, so a mid-write failure never leaves a partial/corrupt destination file.

    Raises:
        OutputWriteError: if the write or the atomic rename fails.
    """
    destination = output_path(source_path)
    text = _render_output(output)
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
        os.replace(tmp_path, destination)
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise OutputWriteError(destination, str(err)) from err
    return destination
