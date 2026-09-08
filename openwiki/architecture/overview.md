# Architecture Overview

`transcribe` is a lightweight CLI for fast transcription of local audio files using Azure AI Speech. The design prioritizes simplicity for Phase 1 (local files via synchronous transcription) and defers complexity (Phase 2: blob-staged batch) until needed.

## Core Design

### Phase 1: Local Files → Fast Transcription (Current)

```
CLI Input
  ↓ (e.g., "transcribe audio.mp3")
Argument Parser (cli.py)
  ↓ (parse, reject if no files)
File Validator (cli.py)
  ↓ (check exists, check extension in {.mp3, .wav})
Credential Loader (credentials.py)
  ↓ (read AZURE_SPEECH_ENDPOINT, AZURE_SPEECH_KEY from env)
Azure Fast-Transcription Request
  ↓ (POST to /speechtotext/transcriptions:transcribe)
Response Transform
  ↓ (map Azure result → output schema)
Write JSON Output (audio.mp3.json)
  ↓
Exit (code 0 on success, 1 on any error)
```

**Key insight:** Validation happens *before* any Azure call. If input files or credentials are invalid, the CLI fails locally and exits without touching Azure (cheaper, faster feedback).

### Phase 2: Blob-Staged Batch (Deferred)

Planned for larger/bulk audio exceeding the fast-transcription cap (< 5 h / < 500 MB per file). Will add:
- Azure Blob Storage upload (Cold tier, long-term retention)
- Batch submit with polling loop
- Transcript download from results

See `/spec/adr/0003-fast-transcription-for-local-files.md` for the rationale: fast transcription is simpler and cheaper for the current small-file workload.

## Components

### CLI Module (`src/cli.py`)

**Responsibilities:**
- Parse command-line arguments (`transcribe file1.mp3 file2.wav`)
- Validate each file (exists on disk, extension in `.mp3` or `.wav`)
- Raise `MissingFileError` or `UnsupportedFileTypeError` if validation fails

**Key functions:**
- `build_arg_parser()` — Creates ArgumentParser with "files" positional arg (nargs="+")
- `parse_args(argv)` — Parses and returns list of Path objects; exits with code 2 if no args
- `validate_file(path)` — Checks existence and extension
- `validate_files(paths)` — Validates each path in sequence; stops at first error

**Design pattern:** Fail fast and locally. No I/O beyond stat(); no external calls.

### Credentials Module (`src/credentials.py`)

**Responsibilities:**
- Read `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` from environment
- Validate both are set and non-empty
- Return frozen dataclass `AzureCredentials`

**Key functions:**
- `load_azure_credentials()` — Reads env vars; raises `CredentialError` if either is missing, naming specifically which one(s)

**Design pattern:** Environment variables only (no file-based config, no pydantic-settings). Raises early with clear error message.

### Error Hierarchy (`src/errors.py`)

All exceptions inherit from `AppError` (root), enabling uniform error handling in `main.py`.

```
AppError (base)
├── MissingFileError(path)      # File not found on disk
├── UnsupportedFileTypeError(path)  # Unsupported file extension
├── CredentialError(msg)        # Missing/empty env vars
├── TranscriptionError(path, reason)  # Transcription request failed (auth, non-2xx, network)
└── TranscriptionTimeoutError(path, timeout)  # Request exceeded timeout
```

Each includes the context (path, reason) for clear error messages to stderr.

### Main Entrypoint (`src/main.py`)

**Responsibilities:**
- Call `parse_args()` to get file paths
- Call `validate_files()` to check all files exist and have valid extensions
- Call `load_azure_credentials()` to get credential context (not yet used; awaits issue #8)
- Catch `AppError`, print to stderr, return exit code 1 (or 2 for usage errors)
- Return 0 on success

**Current flow (Phase 1 incomplete):**
```python
try:
    paths = parse_args(sys.argv[1:])
    validate_files(paths)
    # TODO: load credentials
    # TODO: for each path, call Azure and transform result
except AppError as err:
    print(f"Error: {err}", file=sys.stderr)
    return 1
return 0
```

Issues #8, #10, #11 will fill the TODO sections.

## Data Contracts

### Input

```
CLI arguments: str (file paths)
→ parse_args() → list[Path]
→ validate_files() → ok or raise MissingFileError/UnsupportedFileTypeError
```

**Validation rules:**
- At least one file path (argparse nargs="+" enforces; exit code 2 if missing)
- Each file must exist on disk
- Each file extension must be in `{".mp3", ".wav"}` (case-insensitive)

### Credentials

```
Environment variables:
  AZURE_SPEECH_ENDPOINT = "https://region.cognitiveservices.azure.com"
  AZURE_SPEECH_KEY = "key-string"

→ load_azure_credentials() → AzureCredentials(endpoint, key)
```

If either is unset or empty, raises `CredentialError` naming the missing variable(s).

### Output (JSON)

Once issue #10 is implemented, for each input `FILE`:

```json
{
  "source_file": "audio.mp3",
  "language": "en-US",
  "duration_seconds": 12.34,
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "Hello world"
    },
    {
      "start": 2.5,
      "end": 5.0,
      "text": "This is a test"
    }
  ]
}
```

**Mapping (from Azure fast-transcription response):**
- `source_file` ← input file name
- `language` ← phrases' locale (or requested locale from definition)
- `duration_seconds` ← `durationMilliseconds / 1000`
- `segments[].start` ← `offsetMilliseconds / 1000`
- `segments[].end` ← `(offsetMilliseconds + durationMilliseconds) / 1000`
- `segments[].text` ← phrase text

See `/spec/spec.md` "Result → output-schema mapping" for full details.

## Dependencies

### Runtime
- **`httpx >= 0.28.1`** — HTTP client for Azure REST calls. Chosen in ADR-0003 because Azure's batch/fast transcription endpoints are not covered by the Azure SDK; direct REST is required.

### Development
- **`pytest >= 8.0.0`** — Test framework
- **`pytest-cov >= 5.0.0`** — Coverage reporting
- **`pytest-mock >= 3.14.0`** — Mocking for tests
- **`ruff >= 0.9.0`** — Linting and formatting
- **`mypy >= 1.13.0`** — Static type checking
- **`pre-commit >= 4.0.0`** — Git hooks

### Python Version
- **Python 3.13** (see `pyproject.toml` requires-python)

## Key Design Decisions

| Decision | Reference | Rationale |
|----------|-----------|-----------|
| **Use Azure AI Speech (not local model)** | [ADR-0001](/spec/adr/0001-azure-ai-speech-transcription.md) | Existing Azure agreement; no on-premise infra needed; quality and features managed by Azure |
| **Fast (sync) transcription for local files; batch deferred** | [ADR-0003](/spec/adr/0003-fast-transcription-for-local-files.md) | ~400 small files on disk; batch would require blob storage, SAS, polling overhead; fast is simpler and cost-neutral for small volumes |
| **Local Terraform state (not remote backend)** | [ADR-0002](/spec/adr/0002-terraform-for-azure-infra.md) | Lightweight infra; local state is sufficient; keeps barrier to entry low |
| **Environment variables for credentials (no pydantic-settings)** | `/CLAUDE.md` Profile | Project has app config disabled; env-var-only is simple and sufficient |
| **Plain exceptions + error hierarchy (no structured logging)** | `/CLAUDE.md` Profile | Structured logging disabled; AppError hierarchy + stderr printing is sufficient for CLI error reporting |

## Extension Points (Phase 2 and Beyond)

### Adding Blob-Staged Batch Mode
- Add storage credentials (`AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_KEY`) to `credentials.py`
- Create `transcriber_batch.py` module for blob upload, SAS, batch submit, polling
- Modify `main.py` to detect file size and route to fast-vs-batch
- Add `TranscriptionBatchError` and `BatchTimeoutError` to error hierarchy

### Scaling Output
- Currently outputs one JSON file per input. For bulk transcription, consider:
  - Batch output to a single results file
  - Async job tracking / status API
  - Database storage (currently deferred)

### Supporting More Audio Formats
- Currently `{".mp3", ".wav"}`. To add more:
  - Update `SUPPORTED_EXTENSIONS` in `cli.py`
  - Test Azure support for the format
  - Update `/spec/spec.md` "done criteria" if format-specific behavior differs

## Testing Strategy

- **Unit tests** (in `/tests/`, marked `@pytest.mark.unit`):
  - `test_cli.py` — Argument parsing and validation logic
  - `test_credentials.py` — Env var loading
  - `test_main.py` — Main entrypoint and error handling
  
- **Integration tests** (marked `@pytest.mark.integration`):
  - Currently empty (awaiting issue #8 implementation of transcription call)
  - Will mock or use real Azure endpoint to verify transcription and output transformation

- **Coverage:** 70% minimum (enforced by `pyproject.toml` `tool.coverage.report.fail_under`)

See [Testing Guide](../testing/overview.md) for details.

## Related Architecture Decision Records

- **[ADR-0001: Use Azure AI Speech](../spec/adr/0001-azure-ai-speech-transcription.md)** — Why Azure (not local model)
- **[ADR-0002: Terraform for Azure Infra](../spec/adr/0002-terraform-for-azure-infra.md)** — Local state, resource group, scaling
- **[ADR-0003: Fast Transcription for Local Files](../spec/adr/0003-fast-transcription-for-local-files.md)** — Two-mode design, fast vs batch split, Phase 2 deferral
