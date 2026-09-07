# spec.md

**Status:** draft

## Purpose
Transcribe local audio files into timestamped text via a CLI, using Azure AI Speech's Batch Transcription API.

## Inputs / Outputs
- Input: one or more local audio file paths as CLI arguments, e.g. `transcribe audio.mp3 interview.wav`.
- Input (credentials): Azure Speech endpoint and key read from environment variables `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` (plain `os.environ` reads — this project has app config, i.e. `pydantic-settings`, disabled per `CLAUDE.md`).
- Process: each file is submitted as a Batch Transcription job (Azure's asynchronous API — upload, then poll job status until it reaches a terminal state), not the synchronous/fast transcription endpoint. The CLI polls until the job is `Succeeded` or `Failed` before writing output or reporting an error.
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

## What we produce
CLI

## Where we persist
file

## Method
LLM (Azure AI Speech Batch Transcription API — hosted, asynchronous transcription; not a locally-run model, and not Azure's synchronous/fast transcription endpoint. This is the closest fit among this template's three method buckets — rules / classical ML / LLM — for a hosted, pretrained speech-to-text model. Flagged for explicit human confirmation before this spec moves to `approved`.)

## Done criteria
1. `transcribe audio.mp3` (a valid, supported audio file) creates `audio.mp3.json` with keys `source_file`, `language`, `duration_seconds`, and `segments`; `segments` is a non-empty list of objects `{start: number >= 0, end: number > start, text: non-empty string}`, ordered by non-decreasing `start`. Exit code 0.
2. `transcribe a.mp3 b.mp3` creates both `a.mp3.json` and `b.mp3.json`, each independently satisfying criterion 1. Exit code 0.
3. `transcribe missing.mp3`, where `missing.mp3` does not exist, exits with code 1, prints an error to stderr naming `missing.mp3`, and does not create `missing.mp3.json`.
4. `transcribe notes.txt`, where `notes.txt` exists but has an unsupported extension, exits with code 1, prints an error to stderr mentioning "unsupported" and the file extension, and does not create any output file.
5. `transcribe a.mp3 missing.mp3` (one valid file, one missing) creates `a.mp3.json` per criterion 1, prints the missing-file error for `missing.mp3` to stderr, and exits with code 1 overall.
6. `transcribe` with no arguments exits with code 2 and prints a usage message to stderr.
7. `transcribe audio.mp3` with `AZURE_SPEECH_ENDPOINT` or `AZURE_SPEECH_KEY` unset or empty exits with code 1, prints an error to stderr naming the missing variable(s), makes no call to Azure, and creates no output file.
8. `transcribe audio.mp3` where submitting the batch job to Azure fails (e.g. raises an authentication or network error) exits with code 1, prints an error to stderr describing the failure, and does not create `audio.mp3.json` — no partial or corrupt output file is ever written.
9. `transcribe audio.mp3` where the batch job is accepted but reaches Azure's `Failed` terminal status (job-level failure, not a transport/auth error) exits with code 1, prints an error to stderr that includes Azure's reported failure reason, and does not create `audio.mp3.json`.
10. `transcribe audio.mp3` where the batch job stays in a non-terminal status (e.g. `Running`) past a configured timeout exits with code 1, prints a timeout error to stderr naming the file, and does not create `audio.mp3.json`.
