# Specification & Requirements

For authoritative functional requirements, input/output schemas, and done criteria, see [spec.md](../spec/spec.md).

This page summarizes the key requirements and links to design decisions.

## Current phase: Local files via fast transcription with call metadata

**Status:** Complete (issues #6–8, #10–11, #18, #20 done)

**Scope:** Transcribe local audio files using Azure AI Speech's synchronous (fast) endpoint. Enrich transcripts with call metadata from a call-inventory SQLite database. Output SharePoint-ready text files with YAML frontmatter. Support resume via `--clobber` for partial re-runs and error auditing.

## Input/Output contract

### Input

**Command line — single-file mode:**
```bash
transcribe --ref CALL-001 --target 5551234567 --audiopath audio.mp3 --call-db calls.db
```

- `--ref`: Call reference number (string, required)
- `--target`: Target phone number (string, required)
- `--audiopath`: Path to audio file (local path or URL; only local files supported today)
- `--call-db`: Path to call-inventory SQLite database (required)
- `--clobber`: Force reprocess even if output exists (optional, see resume behavior below)

**Command line — batch mode:**
```bash
transcribe --manifest manifest.csv --call-db calls.db [--clobber]
```

- `--manifest`: Path to CSV file with columns `ref`, `target`, `audio_path` (required)
- `--call-db`: Path to call-inventory SQLite database (required)
- `--clobber`: Force reprocess all files (optional)

**Environment:**
```bash
export AZURE_SPEECH_ENDPOINT=https://your-region.cognitiveservices.azure.com/
export AZURE_SPEECH_KEY=your-api-key
export CALL_DB_PATH=/path/to/calls.db  # Optional; --call-db takes precedence
```

- Required: `AZURE_SPEECH_ENDPOINT` (non-empty)
- Required: `AZURE_SPEECH_KEY` (non-empty)
- Optional: `CALL_DB_PATH` (used if `--call-db` not provided)

### Output

**Exit codes:**
- `0`: All files successfully transcribed
- `1`: Validation error, credential error, or transcription error
- `2`: CLI usage error (no arguments, unrecognized flags)

**Files written:**
```bash
$ transcribe --ref C001 --target 5551234567 --audiopath audio.mp3 --call-db calls.db
$ ls -la audio*
-rw-r--r--  audio.mp3
-rw-r--r--  audio-transcript.txt
```

**Output schema — success** (`{stem}-transcript.txt` with YAML frontmatter + body):
```
---
source_file: audio.mp3
ref: CALL-001
target: 5551234567
associate: 5559876543
direction: Inbound
call_start: "2024-01-15T14:30:00"
duration: "00:02:15"
end_time: "2024-01-15T14:32:15"
classification: Business
call_progress: Completed
language: en
monitor: "Agent 1"
text_message: null
---

[0.0-2.5] Hello, this is the call center.
[2.5-5.0] How can I assist you today?
[5.0-7.5] I'm looking for information about...
```

**Frontmatter fields:**
- `source_file` (string): Input file's basename (audit trail continuity)
- `ref` (string | null): Call reference number from manifest/--ref
- `target` (string | null): Target phone number from manifest/--target
- `associate`, `direction`, `call_start`, `duration`, `end_time`, `classification`, `call_progress`, `language`, `monitor`, `text_message` (all strings or null): Call record fields from the SQLite lookup

**Body format:**
- One line per segment: `[start-end] text`
- Times in seconds, 0.1 precision
- Empty if the file had no phrases or if the call record was not found (but frontmatter always populated with source_file + null fields)

**Output schema — failure** (`{stem}-transcript.txt` with YAML frontmatter only, no body):
```
---
source_file: audio.mp3
ref: CALL-001
target: 5551234567
error: "Transcription failed: Azure timeout after 30s"
---
```

- `error` field describes the failure: file not found, unsupported extension, transcription failure, call lookup failure, output write failure, etc.
- **Every input file gets exactly one output file**, success or failure. This is the "error-echoing output" contract (ADR-0004).

**Resume behavior:**
- Before processing each file, the tool checks if `{stem}-transcript.txt` already exists
- If it parses as YAML with no `error` key, the file is skipped (already succeeded)
- If it has an `error` key or is missing/unreadable/corrupt, the file is retried
- `--clobber` forces reprocessing all files regardless of existing output
- This design enables resuming partial batch runs without re-calling Azure for already-successful files

**stderr output:**
```bash
$ transcribe --ref C001 --target 5551234567 --audiopath missing.mp3 --call-db calls.db
Error: file not found: missing.mp3
```

- One error message per failure
- All failures reported to stderr before exit
- Exit code is still 1 (failure), but the `{stem}-transcript.txt` file also has an `error` key for audit trailing

## Input validation requirements

**Supported audio file types:**
- `.mp3` (MPEG-3 audio)
- `.wav` (Waveform Audio)
- Extensions are case-insensitive: `.MP3`, `.WAV`, `.mp3`, `.wav` all accepted

**Argument validation:**
1. Exactly one of `--manifest` or the `--audiopath`/`--ref`/`--target` triple must be provided
2. If manifest mode: CSV file must exist and be readable, columns must be `ref`, `target`, `audio_path`
3. If single-file mode: all three of `--audiopath`, `--ref`, `--target` must be non-empty
4. Call database (`--call-db` or `CALL_DB_PATH`) must exist and be readable

**File validation (per-file, during processing):**
1. Audio file must exist on disk (local files only; URLs not supported today)
2. Audio file extension must be `.mp3` or `.wav`

**Validation order:**
1. Parse and validate CLI arguments (fail fast, exit code 2 if invalid)
2. Load credentials
3. Load and parse manifest (if batch mode)
4. For each file: validate file exists and has supported extension
5. Run transcription, lookup, and output for each file

**Failures:** Argument or credential validation errors abort the whole run (exit code 1) before the per-file loop. Per-file failures (missing file, unsupported type, transcription error, lookup error, write error) are caught inside the loop, an error-echoing output file is written for that file, and the run continues with the next file.

## Credential validation requirements

**Environment variables:**
- `AZURE_SPEECH_ENDPOINT`: URL of Azure Cognitive Services endpoint (e.g., `https://eastus.cognitiveservices.azure.com/`)
- `AZURE_SPEECH_KEY`: API key (string, any non-empty value)

**Validation:**
- Both must be set (not unset via `os.environ`)
- Both must be non-empty (empty string `""` is treated as missing)
- If either is missing, raise `CredentialError` naming every missing variable

**Error messages must name missing variables:**
- If `AZURE_SPEECH_KEY` is unset but `AZURE_SPEECH_ENDPOINT` is set:
  ```
  Error: Missing required environment variable(s): AZURE_SPEECH_KEY
  ```
- If both are missing:
  ```
  Error: Missing required environment variable(s): AZURE_SPEECH_ENDPOINT, AZURE_SPEECH_KEY
  ```

**Credentials are validated before transcription.** If validation fails, report error to stderr and exit 1 without calling Azure.

## Call metadata lookup requirements (issue #20)

**Data source:** SQLite database produced by `call-inventory` project (see `/spec/adr/0005-direct-sqlite-read-of-call-inventory-index.md`).

**Lookup:**
- Query the `calls` table by `(ref, target)` key
- `target` is digits-normalized before lookup (any non-digits stripped)
- Return the first matching row by ID (or null if no match)

**Fields used in output:**
- `ref`: Call reference number
- `target`: Target phone number
- `associate`: Associated number
- `direction`: Call direction (inbound/outbound)
- `call_start`: Call start timestamp
- `duration`: Call duration string
- `end_time`: Call end timestamp
- `classification`: Call classification
- `call_progress`: Call progress/outcome
- `language`: Language of the call
- `monitor`: Monitoring/recording agent
- `text_message`: Associated text message body (if any)

**Error handling:**
- If database cannot be opened: `CallDbError`, caught at startup, run aborts
- If lookup returns no matching row: `CallRecordNotFoundError`, caught per-file, error-echoing output written with all call fields set to null
- If database query fails: `CallDbError`, caught per-file, error-echoing output written

## Transcription requirements (issue #8)

**Azure endpoint:**
```
POST /cognitiveservices/v1/speechtotext/transcriptions:transcribe?api-version=2025-10-15
```

**Request format:**
- Content-Type: `multipart/form-data`
- Header: `Ocp-Apim-Subscription-Key: {AZURE_SPEECH_KEY}`
- Body:
  - `audio` (binary part): File bytes
  - `definition` (JSON part): `{"locales": ["en-US"]}` or similar

**Response format (success, 2xx):**
```json
{
  "durationMilliseconds": 12340,
  "phrases": [
    {
      "offsetMilliseconds": 0,
      "durationMilliseconds": 2500,
      "text": "Hello world",
      "locale": "en-US"
    },
    {
      "offsetMilliseconds": 2500,
      "durationMilliseconds": 2500,
      "text": "How are you?",
      "locale": "en-US"
    }
  ]
}
```

**Error handling:**
- Non-2xx response: `TranscriptionError`, caught per-file, error-echoing output written
- Network timeout (default 30s): `TranscriptionTimeoutError`, caught per-file, error-echoing output written
- Empty phrases list: `EmptyTranscriptionResultError`, caught per-file, error-echoing output written
- Auth failure (401, 403): `TranscriptionError`, caught per-file, error-echoing output written

## Output transformation requirements (issue #10 + issue #20)

**YAML frontmatter:** Built from call record fields (all required fields present, even if null):
- `source_file`: Input file's basename
- `ref`, `target`, `associate`, `direction`, `call_start`, `duration`, `end_time`, `classification`, `call_progress`, `language`, `monitor`, `text_message`: From call record (or null if lookup failed)
- On error: add `error` field with failure message; omit body

**Transcript body:** Rendered from Azure phrases
- One line per segment: `[start-end] text`
- Times in seconds, 0.1 precision
- If no phrases (empty transcript): only frontmatter, no error (output file still created for audit trailing; call frontmatter still populated)

**Atomic write:**
- Write to temp file in same directory as output, then rename into place
- Ensures partial/corrupt writes never leave broken output
- Failure to write raises `OutputWriteError`, caught per-file, error-echoing output attempted (but may fail if directory is unwritable)

## Done criteria

**Exit code 0 (all files succeeded):**
1. ✓ Single file: `transcribe --audiopath audio.mp3 --ref C001 --target 5551234567 --call-db calls.db` creates `audio-transcript.txt` with YAML + body
2. ✓ Batch manifest: `transcribe --manifest manifest.csv --call-db calls.db` creates `{stem}-transcript.txt` for each row
3. ✓ Resume/skip: Re-running the same manifest skips files with successful `{stem}-transcript.txt` (no `error` key)
4. ✓ Clobber: `--clobber` flag forces reprocessing all files regardless of existing output

**Exit code 1 (some or all files failed):**
5. ✓ Missing file: `transcribe --audiopath missing.mp3 ... --call-db calls.db` → error to stderr, `missing-transcript.txt` with error field written
6. ✓ Unsupported type: `transcribe --audiopath notes.txt ... --call-db calls.db` → error to stderr, `notes-transcript.txt` with error field written
7. ✓ Mixed valid/invalid: Batch with one missing file → errors to stderr for missing file, but `{stem}-transcript.txt` written for all files (success or error)
8. ✓ Credential error: `transcribe ...` (credentials unset) → error to stderr, no files processed
9. ✓ Call DB missing/unreadable: Invalid `--call-db` or bad database → error to stderr, no files processed
10. ✓ Transcription error: Azure returns non-2xx → error to stderr, error-echoing `{stem}-transcript.txt` written
11. ✓ Empty transcript: Azure returns empty phrases → no body in output, but `{stem}-transcript.txt` written with frontmatter
12. ✓ Call lookup failure: No matching call record → `{stem}-transcript.txt` written with all call fields null but transcript body present

**Exit code 2 (usage error):**
13. ✓ Invalid arguments: `--audiopath` without `--ref`/`--target`, or `--manifest` with `--audiopath`, etc. → usage message to stderr (automatic via argparse)

## Phase 2 (deferred): Blob-staged batch transcription

Not yet built. When implemented:

- Stage each local file to Azure Blob Storage (Cold access tier)
- Mint short-lived SAS URLs for each file
- Submit a batch job via Azure's batch endpoint (async)
- Poll the job until terminal status (Succeeded, Failed) or timeout
- Download transcript from result files
- Transform to output schema (same as Phase 1)

See [spec.md Phase 2 section](../spec/spec.md#phase-2-deferred-blob-staged-batch-mode) and [ADR-0003](../spec/adr/0003-fast-transcription-for-local-files.md) for rationale.

**Why deferred:**
- Current workload: ~400 small files, ~quick turnaround (fast mode sufficient)
- Fast mode is simpler: no blob infrastructure, no polling, no SAS lifecycle
- Batch mode is more expensive per audio hour but suits bulk/large-file workloads
- Revisit when volume or file sizes justify batch infrastructure

## Design decisions

- **Azure AI Speech (not local ML):** See [ADR-0001](../spec/adr/0001-azure-ai-speech-transcription.md)
- **Fast (not batch) for Phase 1:** See [ADR-0003](../spec/adr/0003-fast-transcription-for-local-files.md)
- **Terraform for infra:** See [ADR-0002](../spec/adr/0002-terraform-for-azure-infra.md)
- **httpx as HTTP client:** Used in ADR-0003 decision; direct REST call vs. Azure SDK

## Edge cases & constraints

1. **File size cap:** Azure's fast endpoint caps at ~500 MB and ~5 hours per file. Exceeding this triggers a transcription error → exit 1. For larger files, use Phase 2 batch mode.

2. **Timeout:** Default timeout TBD (likely 30–60s). If a file exceeds the timeout during transcription, exit 1 with timeout error.

3. **Empty audio:** If a file has no detectable speech, Azure returns `phrases: []` → treat as transcription error, exit 1.

4. **Concurrent files (Phase 1):** Files are processed sequentially. No parallelization in Phase 1. (Could optimize later with thread pool or async I/O.)

5. **Duplicate output files:** If `audio.mp3.json` already exists, overwrite it (no append, no version numbering).

6. **Special characters in filenames:** Handled by OS; no validation or sanitization of filename characters.

## Testing requirements

- **Unit tests:** All validation logic (CLI parsing, file checks, credential loading) must have 70%+ coverage
- **Integration tests:** End-to-end flow with mock or real Azure endpoint (deferred until issue #8)
- **Spec compliance:** Each done criterion should have a corresponding test case

See [Testing Guide](./testing.md) for detailed test structure.

## References

- [spec.md](../spec/spec.md): Authoritative functional spec
- [Architecture & Workflows](./architecture.md): Design and layered architecture
- [ADRs](../spec/adr/): Architecture decision records
- [build-order.md](../spec/build-order.md): Issue sequencing for Phase 1 and Phase 2
