# spec.md

**Status:** approved

## Purpose
Transcribe local audio files into timestamped text via a CLI, using Azure AI
Speech. Two input modes are supported, built in priority order:

1. **Local files — fast transcription (primary, current).** Files already on
   disk are sent directly to Azure's **fast (synchronous)** transcription
   endpoint; the transcript is returned inline in the same HTTP response. No
   intermediate storage, no polling. This is the path optimized for quickly
   transcribing many small local files.
2. **Blob-staged batch (deferred, Phase 2).** Larger or bulk audio staged in
   Azure Blob Storage and transcribed via the asynchronous **batch** endpoint.
   Described under "Phase 2" below; not yet built.

The method split (fast for local, batch for blob) is recorded in
`spec/adr/0003-fast-transcription-for-local-files.md`; both sit within the Azure
provider decision in ADR-0001.

## Inputs / Outputs
- Input: either a CSV manifest (`--manifest FILE`, batch mode) with `ref`,
  `target`, and `audio_path` columns — one row per call to transcribe — or a
  single explicit request via `--audiopath PATH --ref REF --target TARGET`.
  `audio_path`/`--audiopath` may be a local file path or a URL; only the
  local-filesystem case is currently supported (see
  `spec/adr/0006-yaml-frontmatter-txt-output.md`).
- Input (call-record database): `--call-db PATH` (or the `CALL_DB_PATH`
  environment variable) — call-inventory's SQLite index, queried by
  `ref`+`target` for the output's frontmatter. See
  `spec/adr/0005-direct-sqlite-read-of-call-inventory-index.md`.
- Input (credentials): Azure Speech endpoint and key read from environment
  variables `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` (plain `os.environ`
  reads — this project has app config, i.e. `pydantic-settings`, disabled per
  `CLAUDE.md`). The local/fast mode needs only these; the deferred blob mode
  adds storage credentials (Phase 2).
- Process (local/fast mode): for each entry:
  1. Validate the file (it exists and has a supported extension) — before
     any Azure call.
  2. Load and validate the Speech credentials, and open the call-record
     database — both once per run, before the per-entry loop.
  3. Look up the entry's call record by `ref`+`target` in the call-record
     database.
  4. `POST` the file to the fast transcription endpoint
     (`.../speechtotext/transcriptions:transcribe?api-version=2025-10-15`) as
     `multipart/form-data` with an `audio` part (the file bytes) and a
     `definition` part (JSON: `locales`, etc.), authenticated with the
     `Ocp-Apim-Subscription-Key` header. `locales` carries every candidate in
     `transcription.CANDIDATE_LOCALES` (currently `en-US`, `es-US`), so Azure
     performs per-phrase language identification among them in this same
     request rather than assuming a single fixed locale (see
     `spec/adr/0007-multi-locale-language-identification.md`). The response
     body **is** the transcription result JSON — there is no job URL,
     polling, or separate download.
  5. Transform the result and call record into this spec's output schema
     (below) and write it to `FILE-transcript.txt`.
- Output: for each input file, exactly one sibling text file
  `FILE-transcript.txt` (`source_path.stem + "-transcript.txt"`) — written on
  success *and* on a per-file failure, so the output folder alone is a
  complete, auditable record of every input file's outcome (see ADR-0004).
  The file is a `---`-delimited YAML frontmatter block followed by the
  transcript body. On success:
  ```
  ---
  source_file: audio.mp3
  ref: '123'
  target: '5551234567'
  associate: '5559876543'
  direction: incoming
  call_start: '2026-08-29 23:05:17'
  duration: '00:00:35'
  end_time: '2026-08-29 23:05:52'
  classification: pertinent
  call_progress: complete
  language: English
  monitor: null
  text_message: null
  detected_locales:
  - en-US
  ---
  [0.0-2.5] Hello world
  ```
  `detected_locales` is the distinct, sorted set of locales Azure's language
  identification reported across the file's phrases (empty if none reported
  one) — separate from the call record's own `language` field. See
  ADR-0007.
  On a per-file failure (missing file, unsupported extension, no matching
  call record, transcription request failure or timeout, or no usable
  transcript): the same frontmatter fields (`None` for any not yet known)
  plus an `error` field, and no body:
  ```
  ---
  source_file: audio.mp3
  ref: null
  ...
  error: 'no usable transcript for audio.mp3: transcription result contained no phrases'
  ---
  ```
- Resuming a run: before processing an entry, if its output already exists
  and holds a successful transcript (no `error` key in the frontmatter), the
  entry is skipped — no Azure call is made. An error-echoing output from a
  prior run does **not** count as done, so it's retried automatically. Pass
  `--clobber` to reprocess every entry regardless of any existing output. See
  ADR-0004.

## Result → output-schema mapping (fast transcription)
Azure's fast-transcription response carries a `phrases` array of
`{offsetMilliseconds, durationMilliseconds, text, locale}` (`locale` is the
per-phrase language-identification result among `CANDIDATE_LOCALES`, and may
be absent — see ADR-0007). Map it as:
- `source_file` ← the input file's name.
- The frontmatter's `ref`, `target`, `associate`, `direction`, `call_start`,
  `duration`, `end_time`, `classification`, `call_progress`, `language`,
  `monitor`, `text_message` ← the matching call record (see ADR-0005),
  `None` for any not yet known.
- The frontmatter's `detected_locales` ← the distinct, sorted `locale` values
  present across `phrases` (`[]` if none report one).
- The body ← one line per phrase, `[start-end] text`, where
  `start = offsetMilliseconds/1000`, `end = (offsetMilliseconds +
  durationMilliseconds)/1000`, ordered by non-decreasing `start`.

## What we produce
CLI

## Where we persist
file

## Method
Azure AI Speech — **fast (synchronous) transcription** for local files
(primary, current); **batch (asynchronous) transcription** for blob-staged audio
(Phase 2, deferred). A hosted, pretrained speech-to-text model (the LLM bucket
among this template's rules / classical-ML / LLM method buckets), not a
locally-run model. Both endpoints fall under ADR-0001's Azure provider decision;
the fast-vs-batch split and its rationale are in ADR-0003.

## Done criteria (local/fast mode — current)
1. `transcribe --audiopath audio.mp3 --ref 123 --target 5551234567 --call-db calls.db`
   (a valid, supported audio file; `ref`+`target` matching a row in
   `calls.db`) creates `audio-transcript.txt`: a `---`-delimited YAML
   frontmatter block with `source_file` plus the matching call record's
   fields (see ADR-0005/ADR-0006), followed by a non-empty body of one line
   per segment, `[start-end] text` with `start >= 0` and `end > start`. Exit
   code 0.
2. A `--manifest manifest.csv` run with two valid rows (`a.mp3`, `b.wav`,
   each with a matching call record) creates both `a-transcript.txt` and
   `b-transcript.txt`, each independently satisfying criterion 1. Exit code 0.
3. An entry whose `audio_path` does not exist exits with code 1, prints an
   error to stderr naming the missing file, and creates its
   `FILE-transcript.txt` with `source_file` + an `error` field (see
   ADR-0004) — no partial or corrupt output file is ever written.
4. An entry whose `audio_path` exists but has an unsupported extension exits
   with code 1, prints an error to stderr mentioning "unsupported" and the
   file extension, and creates its output with an `error` field mentioning
   "unsupported".
5. A `--manifest` run with one valid entry and one missing-file entry
   creates the valid entry's output per criterion 1, prints the missing-file
   error to stderr, creates the failing entry's output per criterion 3, and
   exits with code 1 overall.
6. `transcribe` with no arguments, or with `--manifest` combined with
   `--audiopath`/`--ref`/`--target`, or with only some of
   `--audiopath`/`--ref`/`--target` given, exits with code 2 and prints a
   usage message to stderr.
7. A run with `AZURE_SPEECH_ENDPOINT` or `AZURE_SPEECH_KEY` unset or empty,
   or with `--call-db` missing/unresolvable (no flag and no `CALL_DB_PATH`),
   exits with code 1, prints an error to stderr naming the problem, makes no
   call to Azure, and creates no output file — both failures abort the whole
   run before the per-entry loop starts, so there is no single entry to
   attach an error output to.
8. An entry whose `ref`+`target` matches no row in the call database exits
   with code 1, prints an error to stderr naming the ref/target, and creates
   its output with `source_file` + an `error` field and every call-record
   field `null` — no Azure call is made for that entry.
9. An entry whose fast-transcription call fails (raises or returns an
   authentication or network error, or any non-2xx response) exits with code
   1, prints an error to stderr describing the failure, and creates its
   output with an `error` field describing the failure (carrying the
   call-record fields already found by that point).
10. An entry whose fast-transcription HTTP call exceeds a configured request
    timeout exits with code 1, prints a timeout error to stderr naming the
    file, and creates its output with an `error` field.
11. An entry whose call succeeds but returns no usable transcript (e.g. an
    empty `phrases` list) exits with code 1, prints an error to stderr
    describing the failure, and creates its output with an `error` field
    describing the failure.
12. Rerunning an entry whose output already holds a successful transcript
    from criterion 1 makes no call to Azure and exits with code 0
    (resumed/skipped). If the output instead holds an error from criterion
    8, 9, 10, or 11, the second run retries it — calls Azure again (or
    retries the lookup) and overwrites the output. Adding `--clobber`
    always reprocesses and overwrites, regardless of any existing output.
13. An entry whose audio is in a non-English `CANDIDATE_LOCALES` candidate
    (e.g. Spanish) is transcribed correctly — its output's body contains the
    correctly-recognized (not garbled or empty) text, and its frontmatter's
    `detected_locales` includes that locale (e.g. `es-US`), not just
    `en-US`. See ADR-0007.
14. An entry whose fast-transcription result has usable phrases but none of
    them report a `locale` still succeeds per criterion 1 — its
    `detected_locales` is `[]`, and this is not treated as a failure (see
    ADR-0007).

## Phase 2 (deferred): blob-staged batch mode
Not yet built; kept here so the second mode isn't lost. When built:
- Stage each local audio file in Azure Blob Storage (**Cold** access tier —
  online and directly readable by the batch service, retained long-term as
  evidence; never Archive, which is offline), and mint a short-lived read SAS
  URL for it.
- Submit a batch job (`POST .../speechtotext/transcriptions:submit`) with
  `contentUrls` set to the SAS URL(s); poll the job URL until `Succeeded`,
  `Failed`, or a configured timeout; on `Succeeded`, list the job's files, and
  download the file of kind `Transcription` from its `contentUrl`; transform it
  into the same output schema above.
- Adds storage credentials to the credential contract and an
  `azurerm_storage_account` to `/infra` (extending ADR-0002).
- Batch-specific done criteria then apply: job reaching `Failed` status →
  exit 1 with Azure's failure reason; job stuck past the poll timeout → exit 1
  with a timeout error; result listing/download failing or returning no
  `Transcription`-kind file → exit 1. Each leaves no `FILE-transcript.txt`
  behind.
