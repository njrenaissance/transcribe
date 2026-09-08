# Architecture & Workflows

## System overview

**transcribe** is a thin CLI wrapper around Azure AI Speech's fast (synchronous) transcription endpoint. The design prioritizes simplicity and early validation: bad inputs are rejected before any network call is made.

```
User → CLI args
   ↓
[Parse & validate arguments]  (cli.py)
   ↓
[Load credentials]  (credentials.py)
   ↓
[For each file:]
  ├→ [Transcribe: POST to Azure]  (transcription.py)
  ├→ [Transform result → schema]  (transform.py)
  └→ [Write FILE.json atomically]  (transform.py)
   ↓
User ← exit code + stderr errors
```

## Layered architecture

**Package structure:** All core code lives in `src/transcribe/` — a Python package exposed by the `transcribe` CLI entrypoint.

### 1. CLI Layer (`src/transcribe/cli.py`)

**Purpose:** Parse CLI arguments and validate input files before any system call.

**Key functions:**
- `build_arg_parser()` → `argparse.ArgumentParser`
  - Requires one or more `files` positional arguments
  - Exits with code 2 and usage message if none given (automatic via argparse)

- `parse_args(argv)` → `list[Path]`
  - Converts CLI argument strings to `Path` objects
  - Lets argparse handle exit-on-no-args

- `validate_file(path)` → `None` or raises
  - Checks file exists on disk
  - Checks extension is in `SUPPORTED_EXTENSIONS = {".mp3", ".wav"}`
  - Raises `MissingFileError` or `UnsupportedFileTypeError` (domain exceptions)

- `validate_files(paths)` → `None` or raises
  - Validates each path in order; stops at first invalid file
  - Aggregate validation across multiple inputs

**Why here:** Validation before credentials or Azure calls means:
- Fast feedback on bad input
- No wasted API calls
- Clear error messages before any auth is attempted

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
├── MissingFileError(path: Path)
├── UnsupportedFileTypeError(path: Path)
├── CredentialError
├── TranscriptionError(path: Path, reason: str)
├── TranscriptionTimeoutError(path: Path, timeout: float)
├── EmptyTranscriptionResultError(path: Path)
└── OutputWriteError(path: Path, reason: str)
```

**Design rationale:**
- All domain exceptions inherit from `AppError`
- Specific subclasses for each failure mode (validation, credentials, transcription)
- Each exception carries context: file path, timeout value, reason
- Caught once at the CLI entrypoint, converted to exit code + stderr message

**Why typed exceptions matter:**
- Allows the main entrypoint to catch `AppError` and convert to exit code 1
- Lets argparse's own `SystemExit` (exit code 2, usage) pass through unchanged
- Makes each error mode distinguishable in tests and caller code
- Supports per-file error collection in Phase 1 orchestration ([issue #11](https://github.com/njrenaissance/transcribe/issues/11))

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

### 5. Transform Layer (`src/transcribe/transform.py`)

**Purpose:** Convert Azure's transcription result into the project's output schema and write it atomically to disk.

**Key functions:**
- `transform_result(result: dict, source_path: Path, requested_locale: str = "en-US") → TranscriptOutput`
  - Extracts phrases from Azure result
  - Converts timestamps from milliseconds to seconds
  - Raises `EmptyTranscriptionResultError` if no phrases found
  - Returns `TranscriptOutput` TypedDict with source_file, language, duration_seconds, segments

- `write_transcript_json(output: TranscriptOutput, source_path: Path) → Path`
  - Writes to a temp file first, then atomically renames into place
  - Ensures partial/corrupt writes never leave a broken destination
  - Raises `OutputWriteError` on permission/disk failures

**Why separate:** Transformation is domain logic, distinct from HTTP and orchestration:
- Keeps Azure response parsing logic independent
- Makes output schema testable without network calls
- Atomic writes guarantee data integrity

### 6. Main Entrypoint (`src/transcribe/main.py`)

**Purpose:** Orchestrate the pipeline and convert exceptions to exit codes.

```python
def main(argv: list[str] | None = None) -> int:
    paths = parse_args(sys.argv[1:] if argv is None else argv)
    
    try:
        credentials = load_azure_credentials()
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    
    had_failure = False
    for path in paths:
        try:
            _process_file(path, credentials)
        except AppError as err:
            print(f"Error: {err}", file=sys.stderr)
            had_failure = True
    
    return 1 if had_failure else 0
```

**Behavior (Phase 1, complete):**
- Parses and validates all files upfront
- Loads credentials once
- Processes each file independently:
  - Transcribe via Azure
  - Transform result
  - Write JSON
- Collects per-file errors
- Reports all errors to stderr
- Exit 0 only if all files succeeded; 1 if any failed

**Exception handling:**
- Catches `AppError` (domain exceptions) → exit 1
- Lets `SystemExit` (argparse usage) → exit 2
- Lets other exceptions propagate (programmer errors during development)

**Why this design:**
- Single point of translation from domain exception to exit code
- Separates "is this error expected?" (exception class) from "what's the response?" (caught here)
- Keeps business logic in CLI/credentials/validation layers; exit-code translation at the boundary

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

## HTTP call and transformation (issues #8, #10 — complete)

The transcription and output pipeline is now fully implemented:

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

**2. Transformation** (`transform.py:transform_result`):
```json
{
  "source_file": "audio.mp3",
  "language": "en-US",
  "duration_seconds": 12.34,
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "Hello world"}
  ]
}
```

**3. Atomic write** (`transform.py:write_transcript_json`):
- Writes to a temporary file in the same directory first
- Atomically renames temp → destination using `os.replace()`
- Ensures mid-write failures never leave a corrupt file
- Raises `OutputWriteError` on I/O permission or disk-full errors

## Design decisions

See [ADRs](../spec/adr/) for detailed rationale:

- **ADR-0001:** Azure AI Speech as the transcription provider
- **ADR-0002:** Terraform for infrastructure (local state, Cognitive Services resource)
- **ADR-0003:** Fast (synchronous) transcription for local files; batch (asynchronous) deferred to Phase 2
  - Simplicity: no blob storage, no polling, no separate download
  - Cost-effective for small files (current workload ~400 files, small total audio)
  - Limitation: capped at ~5 hours / ~500 MB per file; larger files require Phase 2 batch mode

## Key constraints & limitations

1. **File size cap:** Azure's fast-transcription endpoint caps at ~500 MB and ~5 hours per file. Larger files require Phase 2 (batch mode via blob storage).

2. **Synchronous:** The CLI blocks until transcription completes. Not suitable for interactive use with very long files. Batch mode (Phase 2) will allow fire-and-forget jobs.

3. **No retry logic yet:** Failed calls (transient network errors, temporary Azure outages) are not retried. Implement in orchestration phase if needed.

4. **Single-threaded:** Files are processed sequentially. Parallelization (async I/O or thread pool) is deferred.

## Testing strategy

See [Testing Guide](./testing.md) for detailed guidance.

**Test coverage (Phase 1 — complete):**
- **Unit tests for CLI parsing** (`test_cli.py`)
  - Argument parsing (with/without arguments)
  - File existence and extension validation
  - Parametrized tests for case-insensitive extension matching

- **Unit tests for credentials** (`test_credentials.py`)
  - Loading when both env vars present
  - Raising `CredentialError` when one or both missing
  - Naming exactly which variable(s) are missing

- **Unit tests for transcription** (`test_transcription.py`)
  - Mocking Azure endpoint responses
  - Testing error cases (non-2xx, timeouts)
  - Parsing response JSON

- **Unit tests for transformation** (`test_transform.py`)
  - Mapping Azure phrases to output segments
  - Handling empty result (EmptyTranscriptionResultError)
  - Atomic JSON write (temp file → destination)
  - Edge cases: missing locale, unsorted phrases

- **Integration tests** (`test_main.py`)
  - Full orchestration with mocked Azure endpoint
  - Per-file error handling
  - Exit codes: 0 on success, 1 on any failure

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
- Result transformation and atomic JSON output — issue #10
- End-to-end orchestration with per-file error handling — issue #11
- Test coverage ≥ 70%
- CI/CD: lint, type-check, and unit tests all passing

See [spec.md](../spec/spec.md) for detailed done criteria and [source-map.md](../source-map.md) for current progress.

