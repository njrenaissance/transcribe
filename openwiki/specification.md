# Specification & Requirements

For authoritative functional requirements, input/output schemas, and done criteria, see [spec.md](../spec/spec.md).

This page summarizes the key requirements and links to design decisions.

## Current phase: Local files via fast transcription

**Status:** In progress (issues #6, #7 done; #8, #10, #11 in progress)

**Scope:** Transcribe local audio files using Azure AI Speech's synchronous (fast) endpoint. No intermediate storage, no polling — transcript returned inline.

## Input/Output contract

### Input

**Command line:**
```bash
transcribe audio.mp3 interview.wav notes.m4a
```

- One or more file paths as positional arguments
- Paths can be absolute or relative

**Environment:**
```bash
export AZURE_SPEECH_ENDPOINT=https://your-region.cognitiveservices.azure.com/
export AZURE_SPEECH_KEY=your-api-key
```

- Required: `AZURE_SPEECH_ENDPOINT` (non-empty)
- Required: `AZURE_SPEECH_KEY` (non-empty)

### Output

**Exit codes:**
- `0`: All files successfully transcribed
- `1`: Validation error, credential error, or transcription error
- `2`: CLI usage error (no arguments, unrecognized flags)

**Files written:**
```bash
$ transcribe audio.mp3
$ ls -la audio.mp3*
-rw-r--r--  audio.mp3
-rw-r--r--  audio.mp3.json
```

**Output schema** (one JSON file per input audio file, named `{input}.json`):
```json
{
  "source_file": "audio.mp3",
  "language": "en",
  "duration_seconds": 12.34,
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "Hello world"},
    {"start": 2.5, "end": 5.0, "text": "How are you?"}
  ]
}
```

**Fields:**
- `source_file` (string): Input file's name (basename, not full path)
- `language` (string): Locale inferred from transcription (e.g. "en", "es")
- `duration_seconds` (float): Total audio duration in seconds
- `segments` (array): List of transcribed phrases with timing
  - `start` (float): Segment start time in seconds, >= 0
  - `end` (float): Segment end time in seconds, > start
  - `text` (string): Transcribed text, non-empty

**stderr output:**
```bash
$ transcribe missing.mp3 unsupported.txt
Error: file not found: missing.mp3
Error: unsupported file extension '.txt': unsupported.txt
```

- One error message per failure
- All failures reported before exit

## File validation requirements

**Supported file types:**
- `.mp3` (MPEG-3 audio)
- `.wav` (Waveform Audio)
- Extensions are case-insensitive: `.MP3`, `.WAV`, `.mp3`, `.wav` all accepted

**Validation order:**
1. CLI argument parsing (must have at least one argument)
2. File existence (each file must exist on disk)
3. File extension (must be `.mp3` or `.wav`)

**Validation happens before any Azure calls.** If any file is invalid, report the error(s) to stderr and exit 1 without making any transcription requests.

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

## Transcription requirements (issue #8, in progress)

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
- Non-2xx response: Report to stderr, exit 1, do not create output file
- Network timeout (configurable, default TBD): Report to stderr, exit 1
- Empty phrases list: Report to stderr, exit 1
- Auth failure (401, 403): Report to stderr, exit 1

## Output transformation requirements (issue #10, in progress)

**Azure response → output schema mapping:**

| Azure field | Output field | Transform |
|---|---|---|
| `durationMilliseconds` | `duration_seconds` | Divide by 1000 |
| `phrases[].locale` | `language` | Use as-is (e.g., "en-US" → "en") |
| `phrases[].offsetMilliseconds` | `segment.start` | Convert to seconds: offset / 1000 |
| `phrases[].offsetMilliseconds + durationMilliseconds` | `segment.end` | Convert to seconds: (offset + duration) / 1000 |
| `phrases[].text` | `segment.text` | Use as-is |
| (input filename) | `source_file` | Use as-is (basename) |

**Segment ordering:**
- Segments must be ordered by non-decreasing start time
- Typically already in order from Azure, but validate/sort if needed

**Empty transcript handling:**
- If `phrases` is empty or missing: Error condition, exit 1, do not write output file

## Done criteria (from spec.md)

**Exit code 0 (success):**
1. ✓ Single file: `transcribe audio.mp3` creates `audio.mp3.json` with correct schema, valid segments
2. ✓ Multiple files: `transcribe a.mp3 b.mp3` creates both `a.mp3.json` and `b.mp3.json`

**Exit code 1 (validation errors):**
3. ✓ Missing file: `transcribe missing.mp3` → error to stderr, no output file
4. ✓ Unsupported type: `transcribe notes.txt` → error to stderr, no output file
5. ✓ Mixed valid/invalid: `transcribe a.mp3 missing.wav` → error for missing file, but still write `a.mp3.json`
6. ✓ Credential error: `transcribe audio.mp3` (credentials unset) → error to stderr, no output file
7. ✓ Transcription error: Azure returns non-2xx or error response → error to stderr, no output file

**Exit code 2 (usage error):**
8. ✓ No arguments: `transcribe` → usage message to stderr (automatic via argparse)

**Current progress:**
- ✓ Done: #1, #3, #4, #6, #8 (usage)
- 🔄 In progress: #2, #5, #7
- ⏳ Deferred: #9 (batch polling, Phase 2)

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
