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
[POST to Azure fast-transcription endpoint]  (azure call via httpx)
   ↓
[Transform result → output schema]
   ↓
[Write FILE.json]
   ↓
User ← exit code + stderr errors
```

## Layered architecture

### 1. CLI Layer (`cli.py`)

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

### 2. Credentials Layer (`credentials.py`)

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

### 3. Error Handling (`errors.py`)

**Purpose:** Domain-specific exception hierarchy for expected failure modes.

**Exception tree:**
```
AppError (base)
├── MissingFileError(path: Path)
├── UnsupportedFileTypeError(path: Path)
├── CredentialError
├── TranscriptionError(path: Path, reason: str)
└── TranscriptionTimeoutError(path: Path, timeout: float)
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

### 4. Main Entrypoint (`main.py`)

**Purpose:** Orchestrate the pipeline and convert exceptions to exit codes.

```python
def main(argv: list[str] | None = None) -> int:
    try:
        paths = parse_args(sys.argv[1:] if argv is None else argv)
        validate_files(paths)
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0
```

**Current behavior (Phase 1):**
- Parses and validates all files
- Stops at first error
- Reports error to stderr; exits 1
- Does not yet transcribe files (issues #8 and #10 will add that)

**Future behavior (Phase 1 completion, issue #11):**
- Process each file individually
- Collect per-file errors
- Transcribe successful files
- Report all errors at the end
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
parse_args() + validate_files() ✓
   ↓
[Issue #8 will call load_azure_credentials()]
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

## HTTP call (future: issues #8, #10)

When [issue #8](https://github.com/njrenaissance/transcribe/issues/8) adds transcription, the flow will be:

```python
# POST to Azure fast-transcription endpoint
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

**Transform to output schema** (issue #10):
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

**Current test coverage (Phase 1):**
- Unit tests for CLI parsing (`test_cli.py`)
  - Argument parsing (with/without arguments)
  - File existence and extension validation
  - Parametrized tests for case-insensitive extension matching

- Unit tests for credentials (`test_credentials.py`)
  - Loading when both env vars present
  - Raising `CredentialError` when one or both missing
  - Naming exactly which variable(s) are missing

- Unit tests for main entrypoint (`test_main.py`)
  - Exit code 0 on success
  - Exit code 1 on AppError
  - Error message to stderr

**Integration tests (deferred):** Will test end-to-end flow with mock or real Azure endpoint after issue #8 (transcription call) is implemented.

## Next steps for implementation

1. **Issue #8:** Add `transcribe_file(path: Path, credentials: AzureCredentials) → dict` function to make the Azure call and return the raw response
   - Use `httpx.post()` to send multipart request
   - Handle non-2xx responses as `TranscriptionError`
   - Handle timeouts as `TranscriptionTimeoutError`

2. **Issue #10:** Add `transform_result(azure_response: dict, source_file: str) → dict` to map Azure's response to output schema
   - Extract `durationMilliseconds`, `phrases`
   - Build segments list with start/end/text
   - Infer language from phrases' `locale` field

3. **Issue #11:** Update `main()` to orchestrate end-to-end:
   - For each file, call `load_azure_credentials()`, `transcribe_file()`, `transform_result()`, write JSON
   - Collect per-file errors
   - Report all errors to stderr
   - Exit 0 only if all files succeeded

See [spec.md](../spec/spec.md) for detailed requirements and done criteria for each issue.

