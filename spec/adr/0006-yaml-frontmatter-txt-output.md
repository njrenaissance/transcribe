# ADR-0006: Write `FILE-transcript.txt` with YAML frontmatter, replacing `FILE.json`

## Status
accepted

## Context
Issue #20: SharePoint, the intended ingestion target for these transcripts,
cannot ingest a `.wav` file or the current `FILE.json` sibling output; a
plain JSON blob saved with a `.txt` extension doesn't render usefully there
either. A transcript also needs to carry its call metadata (see ADR-0005) so
an ingested file is self-describing without a separate lookup.

`spec/adr/0004-error-echoing-output-and-resume.md`'s per-file contract must
survive the format change: every input file gets exactly one output file,
success or failure, so a batch run's output folder is a complete audit trail
even without captured stderr.

Two frontmatter encodings were considered: YAML (conventional
`---`-delimited frontmatter, as used by Jekyll/Hugo/many static-site and
note-taking tools) and JSON (no new dependency, since `json` is already used
throughout `transform.py`). YAML was chosen for its conventional
readability as a plain-text-file header; the cost is a new runtime dependency.

## Decision
Write `FILE-transcript.txt` — `source_path.stem + "-transcript.txt"` — instead
of the sibling-suffixed `FILE.json`. The file has a `---`-delimited YAML
frontmatter block, followed by the transcript body:

- Frontmatter fields (fixed order): `source_file` (kept from the prior
  schema, for audit-trail continuity), then the call record's `ref`,
  `target`, `associate`, `direction`, `call_start`, `duration`, `end_time`,
  `classification`, `call_progress`, `language`, `monitor`, `text_message`.
  Any field with no known value (e.g. lookup never ran or found nothing)
  renders as YAML `null`.
- On success, the body is the transcript, one line per segment:
  `[start-end] text`.
- On a per-file failure (ADR-0004), the frontmatter gains an `error` field
  and there is no body — the same union-of-success-or-error contract as
  before, just YAML instead of JSON.
- `has_existing_transcript`'s resume check now parses the YAML frontmatter
  block instead of JSON, with the same "no `error` key" success criterion.

Adds `pyyaml` as a new runtime dependency (`types-pyyaml` for `mypy`, since
PyYAML ships no inline type stubs).

## Consequences
- Drops the prior transcription-derived `language` and `duration_seconds`
  fields from the output, in favor of the call record's own `language` and
  `duration` (a call-length string, not a transcription-audio-length
  number) — any downstream consumer built against the old JSON shape
  breaks.
- This is `transcribe`'s first third-party runtime dependency beyond
  `httpx`/`python-dotenv`.
- A file with no matching call record (see ADR-0005) still gets a
  `FILE-transcript.txt` with `source_file` + `error`, consistent with every
  other per-file failure mode.
