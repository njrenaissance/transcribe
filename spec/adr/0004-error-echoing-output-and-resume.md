# ADR-0004: Write an error-echoing output file for every per-file failure; use it to resume runs

## Status
accepted

## Context
Issue #18 was found during live-fire testing against `data/manifest.csv`
(~400 real files): when a fast-transcription result has no usable transcript,
`transform.transform_result` raises `EmptyTranscriptionResultError`, and
`main.py`'s per-file loop catches it, prints to stderr, and writes **no**
output file — matching the behavior `spec.md`'s original done criterion 10
and issue #10's acceptance criteria explicitly specified. In a batch of
hundreds of files, a failure's only trace is a line printed to stderr during
the run; there is no way to later scan the output folder and tell which
inputs failed transcription versus which were never run at all, unless
stderr was captured and kept.

The issue explicitly left open whether the fix should cover only the
empty-transcript case that was observed, or every per-file failure mode
(missing file, unsupported extension, transcription request failure,
timeout). Separately, running the tool over a large manifest is expected to
be interrupted and re-run; re-transcribing (and re-paying Azure for) files
that already succeeded on a prior run is wasteful, but doing that safely
requires the output itself to distinguish "succeeded" from "failed, needs
retry."

## Decision
Every input file now gets exactly one `FILE.json`, regardless of outcome:

- Success → the existing schema (`source_file`, `language`,
  `duration_seconds`, `segments`).
- A per-file failure → `{"source_file": ..., "error": "<message>"}`.

This applies uniformly to **every** per-file failure raised inside the
validate/transcribe/transform sequence — `MissingFileError`,
`UnsupportedFileTypeError`, `TranscriptionError`,
`TranscriptionTimeoutError`, and `EmptyTranscriptionResultError` — not just
the empty-transcript case that was observed live. A partial fix covering
only one failure mode would leave the same silent-failure gap for every
other one, and the auditability rationale applies equally to all of them.
`ManifestError` and `CredentialError` are unaffected: both abort the whole
run before the per-file loop starts, so there is no single file to attach an
error to.

A resume mechanism rides on this same schema distinction: before processing
a file, if its output already exists and parses as a successful transcript
(no `error` key), the run skips it — no Azure call. An error-echoing output,
or one that's missing/unreadable/corrupt, does **not** count as done, so a
retried run naturally retries prior failures without a separate "retry"
flag. A new `--clobber` CLI flag forces reprocessing of every file
regardless of any existing output, for the case where a full re-run is
wanted on purpose (e.g. after a code or credential fix).

## Consequences
- The output schema is now effectively a union (success vs. error); any
  downstream consumer of `FILE.json` must check for an `error` key rather
  than assuming the success shape.
- `spec.md`'s done criteria 3, 4, 5, 8, 9, and 10 change from "does not
  create `FILE.json`" to "creates `FILE.json` with an `error` field"; a new
  criterion 11 documents the skip/resume and `--clobber` behavior.
- `MissingFileError`/`UnsupportedFileTypeError` can still leave no output if
  the destination's parent directory doesn't exist or isn't writable — that
  surfaces as `OutputWriteError` instead, the same as any output-write
  failure, and is not specific to this change.
- Resuming a large manifest run (the original motivation for the live-fire
  testing that surfaced issue #18) no longer re-calls Azure for files that
  already succeeded, while still retrying files that previously failed.
