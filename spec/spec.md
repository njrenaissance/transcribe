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
- Input: one or more local audio file paths as CLI arguments, e.g.
  `transcribe audio.mp3 interview.wav`.
- Input (credentials): Azure Speech endpoint and key read from environment
  variables `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` (plain `os.environ`
  reads — this project has app config, i.e. `pydantic-settings`, disabled per
  `CLAUDE.md`). The local/fast mode needs only these; the deferred blob mode
  adds storage credentials (Phase 2).
- Process (local/fast mode): for each input `FILE`:
  1. Validate CLI arguments and the file (it exists and has a supported
     extension) — before any Azure call.
  2. Load and validate the Speech credentials.
  3. `POST` the file to the fast transcription endpoint
     (`.../speechtotext/transcriptions:transcribe?api-version=2025-10-15`) as
     `multipart/form-data` with an `audio` part (the file bytes) and a
     `definition` part (JSON: `locales`, etc.), authenticated with the
     `Ocp-Apim-Subscription-Key` header. The response body **is** the
     transcription result JSON — there is no job URL, polling, or separate
     download.
  4. Transform the result JSON into this spec's output schema (below) and write
     it to `FILE.json`.
- Output: for each input `FILE`, a sibling JSON file `FILE.json`:
  ```json
  {
    "source_file": "audio.mp3",
    "language": "en",
    "duration_seconds": 12.34,
    "segments": [
      {"start": 0.0, "end": 2.5, "text": "Hello world"}
    ]
  }
  ```

## Result → output-schema mapping (fast transcription)
Azure's fast-transcription response carries `durationMilliseconds` and a
`phrases` array of `{offsetMilliseconds, durationMilliseconds, text, locale}`.
Map it as:
- `source_file` ← the input file's name.
- `language` ← the phrases' `locale` (or the requested locale).
- `duration_seconds` ← `durationMilliseconds / 1000`.
- `segments` ← one object per phrase: `{start: offsetMilliseconds/1000,
  end: (offsetMilliseconds + durationMilliseconds)/1000, text}`, ordered by
  non-decreasing `start`.

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
1. `transcribe audio.mp3` (a valid, supported audio file) creates
   `audio.mp3.json` with keys `source_file`, `language`, `duration_seconds`, and
   `segments`; `segments` is a non-empty list of objects
   `{start: number >= 0, end: number > start, text: non-empty string}`, ordered
   by non-decreasing `start`. Exit code 0.
2. `transcribe a.mp3 b.mp3` creates both `a.mp3.json` and `b.mp3.json`, each
   independently satisfying criterion 1. Exit code 0.
3. `transcribe missing.mp3`, where `missing.mp3` does not exist, exits with code
   1, prints an error to stderr naming `missing.mp3`, and does not create
   `missing.mp3.json`.
4. `transcribe notes.txt`, where `notes.txt` exists but has an unsupported
   extension, exits with code 1, prints an error to stderr mentioning
   "unsupported" and the file extension, and does not create any output file.
5. `transcribe a.mp3 missing.mp3` (one valid, one missing) creates `a.mp3.json`
   per criterion 1, prints the missing-file error for `missing.mp3` to stderr,
   and exits with code 1 overall.
6. `transcribe` with no arguments exits with code 2 and prints a usage message
   to stderr.
7. `transcribe audio.mp3` with `AZURE_SPEECH_ENDPOINT` or `AZURE_SPEECH_KEY`
   unset or empty exits with code 1, prints an error to stderr naming the
   missing variable(s), makes no call to Azure, and creates no output file.
8. `transcribe audio.mp3` where the fast-transcription call fails (raises or
   returns an authentication or network error, or any non-2xx response) exits
   with code 1, prints an error to stderr describing the failure, and does not
   create `audio.mp3.json` — no partial or corrupt output file is ever written.
9. `transcribe audio.mp3` where the fast-transcription HTTP call exceeds a
   configured request timeout exits with code 1, prints a timeout error to
   stderr naming the file, and does not create `audio.mp3.json`.
10. `transcribe audio.mp3` where the call succeeds but returns no usable
    transcript (e.g. an empty `phrases` list) exits with code 1, prints an error
    to stderr describing the failure, and does not create `audio.mp3.json`.

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
  `Transcription`-kind file → exit 1. Each leaves no `FILE.json` behind.
