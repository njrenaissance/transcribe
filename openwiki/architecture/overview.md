# Architecture & Workflows

## System overview

**transcribe** is a CLI for batch transcribing local audio files with Azure AI Speech, enriched with call metadata from SQLite, and output as SharePoint-ready text files with YAML frontmatter. The design prioritizes simplicity, early validation, and resume capability: bad inputs are rejected before any network call; successful outputs are tracked and can be resumed without re-processing.

```
User → CLI args
   ↓
[Parse & validate arguments, load manifest]  (cli.py)
   ↓
[Load Azure credentials]  (credentials.py)
   ↓
[Open call-inventory SQLite database]  (call_lookup.py)
   ↓
[For each file in manifest:]
  ├→ [Resume check: successful output exists?]
  ├→ [Validate audio file]  (cli.py)
  ├→ [Transcribe: POST to Azure]  (transcription.py)
  ├→ [Look up call metadata]  (call_lookup.py)
  ├→ [Transform → YAML frontmatter + body]  (transform.py)
  └→ [Write {stem}-transcript.txt atomically]  (transform.py)
   ↓
User ← exit code + stderr errors + output files (all or partial)
```

## Layered architecture

**Package structure:** All core code lives in `src/transcribe/` — a Python package exposed by the `transcribe` CLI entrypoint.

### 1. CLI Layer (`src/transcribe/cli.py`)

**Purpose:** Parse CLI arguments, resolve input mode (batch manifest or single-file), and validate files/database before any system call.

**Key functions:**
- `build_arg_parser()` → `argparse.ArgumentParser`
  - Batch mode: `--manifest` (CSV file path), `--call-db` (SQLite db path), optional `--clobber`
  - Single-file mode: `--audiopath`, `--ref`, `--target` (all three required together), `--call-db`, optional `--clobber`
  - Exactly one of `--manifest` or (`--audiopath` + `--ref` + `--target`) must be given
  - Exits with code 2 and usage message on invalid combination (automatic via argparse)

- `parse_args(argv)` → `ParsedArgs`
  - Validates argument combination (manifest XOR single-file)
  - Loads and parses manifest CSV if in batch mode (must have `ref`, `target`, `audio_path` columns)
  - Resolves `--call-db` from CLI flag or `CALL_DB_PATH` environment variable
  - Returns `ParsedArgs(entries=[ManifestEntry(...)], clobber=bool, call_db=Path)`
  - Raises `ManifestError` if manifest or database path is invalid

- `validate_file(path)` → `None` or raises
  - Checks file exists on disk (local files only; URLs not supported today)
  - Checks extension is in `SUPPORTED_EXTENSIONS = {".mp3", ".wav"}`
  - Raises `MissingFileError` or `UnsupportedFileTypeError` (domain exceptions)

**Why here:** Validation before credentials or Azure calls means:
- Fast feedback on bad input
- No wasted API calls
- Clear error messages before any auth is attempted
- Resume check and per-file failures are separate concerns (handled in orchestration)

### 2. Credentials Layer (`src/transcribe/credentials.py`)

**Purpose:** Load and validate Azure Speech credentials from environment variables.

**Key structure:**
```python
@dataclass(frozen=True)
class AzureCredentials:
    endpoint: str
    key: str
```

**Key function:**
- `load_azure_credentials()` → `AzureCredentials`
  - Reads `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` from `os.environ`
  - Raises `CredentialError` if either is unset or empty
  - Error message names every missing variable
  - No caching; each call re-reads from environment

**Why here:** Credentials are a security boundary and resource dependency. Loading explicitly before transcription makes:
- Credential errors discoverable early
- The credential contract (env var names, requirements) visible and testable
- Thread-safe retrieval (no module-level state)

### 3. Error Handling (`src/transcribe/errors.py`)

**Purpose:** Domain-specific exception hierarchy for expected failure modes.

**Exception tree:**
```
AppError (base)
├── MissingFileError(path: Path)           ← Audio file not found
├── UnsupportedFileTypeError(path: Path)   ← Wrong file extension
├── CredentialError(reason: str)           ← Missing/invalid env var
├── ManifestError(reason: str)             ← Manifest parse or DB path error
├── TranscriptionError(path: Path, reason) ← HTTP non-2xx from Azure
├── TranscriptionTimeoutError(path: Path)  ← Network timeout
├── EmptyTranscriptionResultError(path)    ← Azure returned no phrases
├── CallDbError(reason: str)               ← Database query error
├── CallRecordNotFoundError(ref, target)   ← No matching call record (optional)
└── OutputWriteError(path: Path, reason)   ← Can't write output file
```

**Design rationale:**
- All domain exceptions inherit from `AppError`
- Specific subclasses for each failure mode (validation, credentials, transcription, lookup, I/O)
- Each exception carries context: file path, timeout value, reason, ref/target
- Caught at the CLI entrypoint, converted to exit code + stderr message
- Per-file failures trigger error-echoing output file write (ADR-0004)

**Why typed exceptions matter:**
- Allows the main entrypoint to catch `AppError` and convert to exit code 1
- Lets argparse's own `SystemExit` (exit code 2, usage) pass through unchanged
- Makes each error mode distinguishable in tests and caller code
- Supports per-file error collection and error-echoing output (issues #11, #18)
- Different handling for startup errors (abort) vs. per-file errors (write output, continue)

### 4. Transcription Layer (`src/transcribe/transcription.py`)

**Purpose:** Make the Azure fast-transcription HTTP call and return the parsed result.

**Key function:**
- `transcribe_file(path: Path, credentials: AzureCredentials) → dict[str, Any]`
  - Reads audio file from disk
  - POSTs to Azure's `/speechtotext/transcriptions:transcribe` endpoint
  - Sends `Ocp-Apim-Subscription-Key` header with `credentials.key`
  - Returns parsed JSON response: `{"durationMilliseconds": ..., "phrases": [...]}`
  - Raises `TranscriptionError` on non-2xx response
  - Raises `TranscriptionTimeoutError` on timeout

**Why separate:** This layer encapsulates all Azure HTTP details:
- Keeps main entrypoint focused on orchestration
- Makes the Azure contract testable in isolation
- Centralizes error handling for network/API failures

### 5. Call Lookup Layer (`src/transcribe/call_lookup.py`)

**Purpose:** Query call-inventory's SQLite database for metadata to populate YAML frontmatter (issue #20, ADR-0005).

**Key structure:**
```python
class CallRecord(NamedTuple):
    """One row from the calls table, frontmatter-relevant fields only."""
    ref: str | None
    target: str | None
    associate: str | None
    direction: str | None
    call_start: str | None
    duration: str | None
    end_time: str | None
    classification: str | None
    call_progress: str | None
    language: str | None
    monitor: str | None
    text_message: str | None

class CallDatabase:
    """SQLite connection to the calls table."""
    def __init__(self, db_path: Path) -> None: ...
    def lookup(self, ref: str, target: str) -> CallRecord | None: ...
```

**Key function:**
- `CallDatabase.lookup(ref: str, target: str) → CallRecord | None`
  - Opens SQLite connection to the database (opened once in main)
  - Normalizes `target` to digits-only (strips non-digit chars, matching call-inventory's own filtering)
  - Queries: `SELECT (columns) FROM calls WHERE ref = ? AND target = ? ORDER BY id LIMIT 1`
  - Returns `CallRecord` if found, `None` if no match
  - Raises `CallDbError` on query failure

**Why separate:** Call metadata is independent from transcription:
- Decouples this project from `wireline` package internals (see ADR-0005)
- Uses only the documented `calls` table schema, treating it as a versioned data contract
- Makes lookup testable with a local SQLite file
- Enables auditing (all call fields in output YAML)

### 6. Transform Layer (`src/transcribe/transform.py`)

**Purpose:** Convert Azure's transcription result + call record into YAML frontmatter + text body output (issue #20, ADR-0006).

**Key structure:**
```python
class TranscriptOutput(NamedTuple):
    """Success: YAML frontmatter + transcript body."""
    frontmatter: dict[str, str | None]
    body: str

class ErrorOutput(NamedTuple):
    """Failure: YAML frontmatter only (with 'error' field)."""
    frontmatter: dict[str, str | None]  # Always includes "error"
```

**Key functions:**
- `transform_result(result: dict, source_path: Path, call_record: CallRecord | None) → TranscriptOutput`
  - Extracts phrases from Azure result
  - Converts timestamps from milliseconds to seconds
  - Builds frontmatter from `call_record` (or null fields if lookup failed)
  - Renders body as `[start-end] text` lines
  - Raises `EmptyTranscriptionResultError` if no phrases found (but output file still written, see orchestration)
  - Returns `TranscriptOutput(frontmatter, body)`

- `write_transcript_file(output: TranscriptOutput | ErrorOutput, output_path: Path) → Path`
  - Serializes frontmatter to YAML with `---` delimiters
  - Appends body (if `TranscriptOutput`); omits for `ErrorOutput`
  - Writes to a temp file first, then atomically renames into place
  - Ensures partial/corrupt writes never leave a broken destination
  - Raises `OutputWriteError` on permission/disk failures

**Why separate:** Transformation is domain logic, distinct from HTTP and orchestration:
- Keeps Azure response parsing independent
- Makes YAML/frontmatter format testable without network calls
- Atomic writes guarantee data integrity
- Error vs. success output use the same file path convention (enables resume)

### 7. Main Entrypoint (`src/transcribe/main.py`)

**Purpose:** Orchestrate the pipeline and convert exceptions to exit codes. Handles per-file error collection and error-echoing output (ADR-0004).

**Behavior (Phase 1, complete):**
- Parses and validates CLI arguments + manifest upfront (fail fast, exit 2 on bad args)
- Loads credentials and call database before per-file loop
- Resume check: skips files with successful output (unless `--clobber`)
- Processes each file independently:
  - Validate audio file
  - Transcribe via Azure
  - Look up call metadata
  - Transform to YAML + body
  - Write to `{stem}-transcript.txt` atomically
- Per-file failures: write error-echoing output, print to stderr, continue with next file
- Collects per-file errors
- Reports all errors to stderr
- Exit 0 only if all files succeeded (or were skipped via resume); 1 if any failed/errored

**Exception handling:**
- Startup errors (`CredentialError`, `ManifestError`, `CallDbError`): caught in startup phase, exit 1, no files processed
- Per-file errors (all others): caught in loop, error output written, continue
- `SystemExit` (argparse usage): exit 2 (unchanged)
- Programmer errors propagate (for development debugging)

**Why this design:**
- Single point of translation from domain exception to exit code
- Separates startup failures (abort) from per-file failures (error output + continue)
- Error-echoing output enables complete audit trails and safe resume without separate tracking (ADR-0004)
- Keeps business logic in CLI/credentials/lookup/transform layers; orchestration and error translation at the boundary

## Dependencies

**Runtime:**
- `httpx`: HTTP client for Azure transcription API calls
- `python-dotenv`: Environment variable loading
- `pyyaml`: YAML serialization for frontmatter output (new in ADR-0006)
- `types-pyyaml`: Type stubs for PyYAML (for `mypy`)

**Dev/Test:**
- `pytest`, `pytest-cov`: Testing framework and coverage
- `ruff`: Linting and formatting
- `mypy`: Type checking
- `pre-commit`: Git hooks

**Note:** No dependency on `wireline`/`call-inventory`; call record lookups use stdlib `sqlite3` (ADR-0005).

## Data flow: File validation

```
User: transcribe a.mp3 missing.wav
   ↓
parse_args() → [Path("a.mp3"), Path("missing.wav")]
   ↓
validate_files([Path("a.mp3"), Path("missing.wav")])
   ├→ validate_file(Path("a.mp3"))
   │   ├→ path.exists() ✓
   │   ├→ path.suffix.lower() in {".mp3", ".wav"} ✓
   │   └→ OK
   ├→ validate_file(Path("missing.wav"))
   │   ├→ path.exists() ✗
   │   └→ raise MissingFileError(Path("missing.wav"))
   ↓
main() catches MissingFileError
   ↓
print("Error: file not found: missing.wav", file=sys.stderr)
return 1
   ↓
User ← exit code 1, stderr has error message
```

## Data flow: Credentials validation

```
User: transcribe audio.mp3
      (AZURE_SPEECH_KEY unset)
   ↓
parse_args() → [Path("audio.mp3")]
   ↓
load_azure_credentials()
   ├→ endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT") → "https://..."
   ├→ key = os.environ.get("AZURE_SPEECH_KEY") → ""
   ├→ missing = ["AZURE_SPEECH_KEY"]
   └→ raise CredentialError("Missing required environment variable(s): AZURE_SPEECH_KEY")
   ↓
main() catches CredentialError
   ↓
print("Error: Missing required environment variable(s): AZURE_SPEECH_KEY", file=sys.stderr)
return 1
   ↓
User ← exit code 1
```

## HTTP call and transformation (issues #8, #10, #20 — complete)

The transcription, lookup, and output pipeline is now fully implemented:

**1. Transcription call** (`transcription.py:transcribe_file`):
```python
POST /cognitiveservices/v1/speechtotext/transcriptions:transcribe
  ?api-version=2025-10-15
  
Headers:
  Ocp-Apim-Subscription-Key: {credentials.key}
  
Body:
  multipart/form-data
  ├ audio: (file bytes)
  └ definition: {"locales": ["en-US"], ...}
  
Response (2xx):
  {
    "durationMilliseconds": 12340,
    "phrases": [
      {"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}
    ]
  }
```

**2. Call metadata lookup** (`call_lookup.py:CallDatabase.lookup`):
```sql
SELECT ref, target, associate, direction, call_start, duration, end_time, 
       classification, call_progress, language, monitor, text_message
FROM calls
WHERE ref = ? AND target = ?
ORDER BY id LIMIT 1
```
- Queries call-inventory's SQLite `calls` table by (ref, target)
- Returns `CallRecord` or `None` (if not found, frontmatter fields are null)
- No dependency on `wireline` package; direct SQLite query (ADR-0005)

**3. Transformation to YAML+text** (`transform.py:transform_result`):
```
---
source_file: audio.mp3
ref: C001
target: 5551234567
associate: 5559876543
direction: Inbound
call_start: "2024-01-15T14:30:00"
duration: "00:02:15"
end_time: "2024-01-15T14:32:15"
classification: Business
call_progress: Completed
language: en-US
monitor: "Agent 1"
text_message: null
---

[0.0-2.5] Hello world
[2.5-5.0] How are you?
```
- Frontmatter: call record fields (12 fields + source_file) in fixed order
- Body: one line per segment, `[start-end] text` format
- On error: frontmatter only, includes `error` field, no body (ADR-0004)

**4. Atomic write** (`transform.py:write_transcript_file`):
- Writes to a temporary file in the same directory first
- Atomically renames temp → destination using `os.replace()`
- Ensures mid-write failures never leave a corrupt file
- Raises `OutputWriteError` on I/O permission or disk-full errors

**5. Resume check** (`main.py:has_existing_transcript`):
- Before processing, checks if `{stem}-transcript.txt` already exists
- Parses YAML frontmatter; if no `error` key, file is considered successful and skipped
- `--clobber` flag forces reprocessing all files (ADR-0004)

## Design decisions

See [ADRs](../spec/adr/) for detailed rationale:

- **ADR-0001:** Azure AI Speech as the transcription provider
- **ADR-0002:** Terraform for infrastructure (local state, Cognitive Services resource)
- **ADR-0003:** Fast (synchronous) transcription for local files; batch (asynchronous) deferred to Phase 2
  - Simplicity: no blob storage, no polling, no separate download
  - Cost-effective for small files (current workload ~400 files, small total audio)
  - Limitation: capped at ~5 hours / ~500 MB per file; larger files require Phase 2 batch mode
- **ADR-0004:** Error-echoing output and resume via `--clobber`
  - Every input file gets an output file (success or error) for complete audit trail
  - Resume checks for successful output; `--clobber` forces full re-run without checking (issue #18)
- **ADR-0005:** Direct SQLite read of call-inventory's `calls` table
  - No dependency on `wireline` package; decouples from implementation details
  - Uses documented schema as data contract between projects (issue #20)
  - Avoids CLI-output parsing, subprocess overhead; direct SQL queries
- **ADR-0006:** YAML frontmatter text output for SharePoint ingestion
  - Plain-text files with YAML header, renderable in SharePoint
  - Call metadata embedded in frontmatter (ref, target, language, etc.) for self-describing files
  - Replaces prior JSON output; new runtime dependency: `pyyaml` (issue #20)

## Key constraints & limitations

1. **File size cap:** Azure's fast-transcription endpoint caps at ~500 MB and ~5 hours per file. Larger files require Phase 2 (batch mode via blob storage).

2. **Synchronous:** The CLI blocks until transcription completes. Not suitable for interactive use with very long files. Batch mode (Phase 2) will allow fire-and-forget jobs.

3. **No retry logic yet:** Failed calls (transient network errors, temporary Azure outages) are not retried automatically. The `--clobber` flag and resume mechanism allow manual re-runs.

4. **Single-threaded:** Files are processed sequentially. Parallelization (async I/O or thread pool) is deferred.

5. **Local audio files only:** URLs and remote paths are not supported today; manifest `audio_path` entries must be local filesystem paths.

6. **Call lookup is optional:** If a call record is not found (no matching row in the `calls` table), the output file is still written with all call fields set to null. No failure occurs.

## Testing strategy

See [Testing Guide](./testing.md) for detailed guidance.

**Test coverage (Phase 1 — complete):**
- **Unit tests for CLI parsing & validation** (`test_cli.py`)
  - Argument parsing: batch mode (`--manifest`), single-file mode (`--audiopath`/`--ref`/`--target`)
  - Mutual exclusivity validation
  - Manifest CSV loading (correct columns, missing file)
  - File existence and extension validation
  - Parametrized tests for case-insensitive extension matching

- **Unit tests for credentials** (`test_credentials.py`)
  - Loading when both env vars present
  - Raising `CredentialError` when one or both missing
  - Naming exactly which variable(s) are missing

- **Unit tests for call lookup** (`test_call_lookup.py`)
  - Opening SQLite database (success and error cases)
  - Querying `calls` table by (ref, target)
  - Phone number normalization (digits only)
  - Handling no matching record (`None` return)
  - Handling database errors

- **Unit tests for transcription** (`test_transcription.py`)
  - Mocking Azure endpoint responses
  - Testing error cases (non-2xx, timeouts)
  - Parsing response JSON

- **Unit tests for transformation** (`test_transform.py`)
  - Building YAML frontmatter from call record
  - Mapping Azure phrases to segments
  - Rendering `[start-end] text` body format
  - Handling empty result (EmptyTranscriptionResultError)
  - Handling missing call record (null frontmatter fields)
  - Atomic YAML+text write (temp file → destination)
  - Edge cases: missing locale, unsorted phrases, missing call fields

- **Integration tests** (`test_main.py`)
  - Full orchestration with mocked Azure endpoint and SQLite database
  - Resume check: skip successful files, retry failed ones
  - `--clobber` flag: force reprocessing all files
  - Per-file error handling and error-echoing output
  - Exit codes: 0 on success, 1 on any failure
  - Batch manifest processing with mixed success/failure

**Coverage target:** Minimum 70% (enforced by `pytest-cov` in `pyproject.toml`)

## Phase 2: Batch transcription (deferred)

Phase 2 will add asynchronous batch transcription for large files (>500 MB or >5 hours) via Azure Blob Storage:

- **Issue #9:** Poll Azure batch transcription job until terminal status or timeout
- Blob upload with SAS tokens
- Batch job submission and status polling
- Partial output collection (don't wait for all files)

See [spec/adr/0003](../spec/adr/0003-fast-transcription-for-local-files.md) and [spec/build-order.md](../spec/build-order.md) for Phase 2 planning.

## Phase 1 completion checklist

✅ All done criteria met:
- File validation (extension, existence) — issue #6
- Azure credential validation — issue #7
- Synchronous fast transcription via Azure — issue #8
- Output transformation and atomic file write — issue #10
- End-to-end orchestration and per-file error handling — issue #11
- Error-echoing output and resume via `--clobber` — issue #18
- Call metadata lookup and YAML frontmatter output — issue #20
- Result transformation and atomic JSON output — issue #10
- End-to-end orchestration with per-file error handling — issue #11
- Test coverage ≥ 70%
- CI/CD: lint, type-check, and unit tests all passing

See [spec.md](../spec/spec.md) for detailed done criteria and [source-map.md](../source-map.md) for current progress.

