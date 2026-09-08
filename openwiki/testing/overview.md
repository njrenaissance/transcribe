# Testing Overview

This page describes the testing strategy, test structure, coverage requirements, and guidance for adding tests as new features are implemented.

## Testing Philosophy

- **Fail fast locally.** Run `make check` (lint + type-check + tests) before pushing.
- **Unit tests by default.** Fast, no I/O, no external dependencies (mock Azure calls).
- **Integration tests for workflows.** Test end-to-end flows once implementation is complete.
- **Coverage target:** 70% minimum (enforced by pytest configuration).
- **Markers:** Use `@pytest.mark.unit` and `@pytest.mark.integration` to organize and run subsets.

## Test Structure

```
tests/
├── conftest.py          # Shared pytest configuration
├── test_cli.py          # Unit: argument parsing, file validation
├── test_credentials.py  # Unit: credential loading from env
└── test_main.py         # Integration placeholder: main entrypoint
```

## Current Tests

### test_cli.py — Argument Parsing & File Validation

**Status:** ✅ Complete (issues #6)

**What's tested:**
- Argument parsing returns Path objects
- Usage error (exit code 2) when no arguments given
- Supported extensions (.mp3, .wav, case-insensitive) accepted
- Missing file raises MissingFileError
- Unsupported extension raises UnsupportedFileTypeError
- Multiple files: validation stops at first error

**Key tests:**

```python
@pytest.mark.unit
def test_parse_args_returns_paths_for_each_argument():
    assert parse_args(["a.mp3", "b.wav"]) == [Path("a.mp3"), Path("b.wav")]


@pytest.mark.unit
def test_validate_file_accepts_supported_extensions(tmp_path, extension):
    audio_file = tmp_path / f"audio{extension}"
    audio_file.touch()
    validate_file(audio_file)  # Should not raise


@pytest.mark.unit
def test_validate_file_raises_when_file_missing(tmp_path):
    missing = tmp_path / "missing.mp3"
    with pytest.raises(MissingFileError, match="missing.mp3"):
        validate_file(missing)
```

### test_credentials.py — Credential Loading

**Status:** ✅ Complete (issue #7)

**What's tested:**
- Both credentials loaded when present
- CredentialError naming only the missing variable (not the one that's set)
- CredentialError naming both when both are missing
- Handles unset and empty-string cases

**Key tests:**

```python
@pytest.mark.unit
def test_load_azure_credentials_returns_credentials_when_both_present(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "secret-key")
    
    credentials = load_azure_credentials()
    
    assert credentials == AzureCredentials(
        endpoint="https://example.cognitiveservices.azure.com",
        key="secret-key"
    )

@pytest.mark.unit
@pytest.mark.parametrize(
    ("endpoint_value", "key_value", "expected_present", "expected_missing"),
    [
        pytest.param(None, "secret-key", "AZURE_SPEECH_KEY", "AZURE_SPEECH_ENDPOINT", id="endpoint_unset"),
        pytest.param("", "secret-key", "AZURE_SPEECH_KEY", "AZURE_SPEECH_ENDPOINT", id="endpoint_empty"),
        # ... more cases
    ],
)
def test_load_azure_credentials_raises_naming_only_the_missing_variable(
    monkeypatch, endpoint_value, key_value, expected_present, expected_missing
):
    # (fixture sets env vars, calls load_azure_credentials, verifies error message)
```

### test_main.py — Main Entrypoint

**Status:** ✅ Partial (issues #6–#7); awaiting #8–#11 (Azure transcription & orchestration)

**What's tested:**
- Valid files return exit code 0
- No arguments: usage error, exit code 2
- Missing file: error message to stderr, exit code 1
- Unsupported extension: error message to stderr, exit code 1

**Key tests:**

```python
@pytest.mark.unit
def test_main_returns_zero_for_valid_files(tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    assert main([str(audio_file)]) == 0


@pytest.mark.unit
def test_main_reports_missing_file(tmp_path, capsys):
    missing = tmp_path / "missing.mp3"

    exit_code = main([str(missing)])

    assert exit_code == 1
    assert "missing.mp3" in capsys.readouterr().err
```

**Awaiting:**
- Azure credential validation in main() (issue #7 complete, but not yet integrated into main flow)
- Azure transcription call (issue #8)
- Output JSON transformation and writing (issue #10)
- End-to-end orchestration for multiple files (issue #11)

## Running Tests

### Run All Tests

```bash
uv run pytest
# or
make test
```

**Output:**
```
tests/test_cli.py .........                    [ 35%]
tests/test_credentials.py .......              [ 70%]
tests/test_main.py ....                        [100%]
======================== 20 passed in 0.23s ========================
```

### Run Specific Marker

```bash
# Unit tests only (default)
uv run pytest -m unit

# Integration tests only (currently empty)
uv run pytest -m integration

# Exclude integration
uv run pytest -m "not integration"
```

### Run Specific File or Test

```bash
# Single file
uv run pytest tests/test_cli.py

# Single test
uv run pytest tests/test_cli.py::test_parse_args_returns_paths_for_each_argument

# Verbose (show test names)
uv run pytest -v

# With output (print to console during test run)
uv run pytest -s

# Stop at first failure
uv run pytest -x
```

### Coverage Report

```bash
# Generate coverage report
uv run pytest --cov=src --cov-report=term-missing

# HTML report (open in browser)
uv run pytest --cov=src --cov-report=html
# Then: open htmlcov/index.html
```

**Minimum coverage:** 70% (enforced by `pyproject.toml`)

## Test Fixtures & Utilities

### pytest Fixtures

**Built-in:**
- `tmp_path` — Temporary directory for test files
- `capsys` — Capture stdout/stderr

**From test files:**
- `monkeypatch` — Modify environment variables (used in test_credentials.py)

### Example: Using tmp_path and capsys

```python
def test_main_reports_missing_file(tmp_path, capsys):
    # Create a temporary directory with test files
    missing = tmp_path / "missing.mp3"
    
    # Call main (doesn't create the file)
    exit_code = main([str(missing)])
    
    # Verify exit code and stderr output
    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "missing.mp3" in stderr
```

### Example: Using monkeypatch

```python
def test_load_azure_credentials_raises_when_endpoint_unset(monkeypatch):
    # Unset AZURE_SPEECH_ENDPOINT
    monkeypatch.delenv("AZURE_SPEECH_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "secret-key")
    
    # Verify error
    with pytest.raises(CredentialError) as exc_info:
        load_azure_credentials()
    
    assert "AZURE_SPEECH_ENDPOINT" in str(exc_info.value)
    assert "AZURE_SPEECH_KEY" not in str(exc_info.value)  # Only missing var mentioned
```

## Adding Tests for New Features

### Test for Issue #8: Azure Transcription Call

**Location:** Create `tests/test_transcriber.py` (new module for transcription logic)

**What to test:**
- Request URL construction (endpoint, API version, query params)
- Multipart request body (audio file part, definition JSON part)
- Request headers (Ocp-Apim-Subscription-Key)
- Response parsing (durationMilliseconds, phrases array)
- Error handling: 401 Unauthorized → TranscriptionError
- Error handling: 4xx/5xx → TranscriptionError
- Error handling: timeout → TranscriptionTimeoutError
- Error handling: empty phrases → TranscriptionError
- Specific phrase fields extracted correctly

**Example test (mocking Azure):**

```python
@pytest.mark.unit
def test_transcribe_file_constructs_correct_request(mocker):
    """Verify the transcription request has correct URL, headers, body."""
    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "durationMilliseconds": 1000,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "hello", "locale": "en-US"}],
    }

    audio_path = Path("audio.mp3")
    credentials = AzureCredentials(endpoint="https://example.cognitiveservices.azure.com", key="key")

    result = transcribe_file(audio_path, credentials, timeout=30.0)

    # Verify httpx.post was called with correct args
    mock_post.assert_called_once()
    call_args = mock_post.call_args

    assert call_args[1]["url"].startswith("https://example.cognitiveservices.azure.com")
    assert "api-version=2025-10-15" in call_args[1]["url"]
    assert call_args[1]["headers"]["Ocp-Apim-Subscription-Key"] == "key"
    assert call_args[1]["timeout"] == 30.0
```

### Test for Issue #10: Output JSON Transformation

**Location:** `tests/test_transcriber.py` (same file as #8)

**What to test:**
- Source file name extraction (base name only, not full path)
- Language mapping from Azure phrases
- Duration calculation (milliseconds to seconds)
- Segment start/end time conversion (milliseconds to seconds)
- Segments ordered by start time (if Azure doesn't guarantee order)
- Empty text handling (should reject)
- Segment count matches phrase count

**Example test:**

```python
@pytest.mark.unit
def test_transform_azure_result_to_schema_maps_correctly():
    """Verify Azure response maps to output schema correctly."""
    azure_result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "hello", "locale": "en-US"},
            {"offsetMilliseconds": 2500, "durationMilliseconds": 2500, "text": "world", "locale": "en-US"},
        ],
    }
    
    output = transform_azure_result_to_schema(azure_result, Path("audio.mp3"))
    
    assert output["source_file"] == "audio.mp3"
    assert output["language"] == "en-US"
    assert output["duration_seconds"] == 5.0
    assert len(output["segments"]) == 2
    assert output["segments"][0] == {"start": 0.0, "end": 2.5, "text": "hello"}
    assert output["segments"][1] == {"start": 2.5, "end": 5.0, "text": "world"}
```

### Test for Issue #11: End-to-End Orchestration

**Location:** `tests/test_main.py` (add integration tests)

**What to test:**
- Multiple files: each transcribed independently
- Multiple files with one failure: stops at first error, no further files processed
- Output files created in correct location (same dir as input file)
- Output file named correctly (input file name + ".json")
- Exit code 0 on success, 1 on any error

**Example test (integration, requires mocking or real Azure):**

```python
@pytest.mark.integration
def test_main_transcribes_multiple_files_and_writes_json(mocker, tmp_path):
    """Verify end-to-end: CLI -> validation -> transcription -> JSON output."""
    # Create audio files
    audio1 = tmp_path / "audio1.mp3"
    audio2 = tmp_path / "audio2.wav"
    audio1.touch()
    audio2.touch()

    # Mock Azure responses
    mock_post = mocker.patch("httpx.post")
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "durationMilliseconds": 1000,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "test", "locale": "en-US"}],
    }

    # Set credentials
    mocker.patch.dict(
        "os.environ",
        {
            "AZURE_SPEECH_ENDPOINT": "https://example.com",
            "AZURE_SPEECH_KEY": "key",
        },
    )

    # Run
    exit_code = main([str(audio1), str(audio2)])

    # Verify
    assert exit_code == 0
    assert (tmp_path / "audio1.mp3.json").exists()
    assert (tmp_path / "audio2.wav.json").exists()
```

## Test Coverage Goals

### Phase 1 (Current: Issues #6–#7)
- ✅ CLI parsing: 100% (argument parsing is simple and straightforward)
- ✅ File validation: 100% (existence and extension checks)
- ✅ Credential loading: 100% (env var reads)
- 🟡 Main entrypoint: ~60% (orchestration tested, transcription not yet)

### Phase 2 (Awaiting: Issues #8–#11)
- 🚧 Azure transcription call: ~80% (all request/response paths, error cases)
- 🚧 Output transformation: ~90% (edge cases like empty text, unsorted phrases)
- 🚧 JSON file writing: ~80% (write success, write failure, file location)
- 🚧 End-to-end orchestration: ~85% (multi-file, error handling, exit codes)

**Overall target:** 70% minimum (currently ~70%, will be 85%+ after #8–#11)

## CI Test Runs

### Unit Tests in CI

```bash
# CI job runs:
uv run pytest -m unit
```

Runs on every PR. Must pass before merge.

### Integration Tests in CI

```bash
# CI job runs (if docker-compose.yml exists):
docker compose up -d --wait
uv run pytest -m integration
docker compose down -v
```

Currently: No integration tests, so this job is skipped (green).

Once issue #8 is implemented: Will require mocking Azure or standing up a test service.

## Debugging Failed Tests

### Run with verbose output

```bash
uv run pytest -vv
```

### Run with live output (print statements visible)

```bash
uv run pytest -s
```

### Stop at first failure

```bash
uv run pytest -x
```

### Show local variables on failure

```bash
uv run pytest -l
```

### Post-mortem debugging (drop into pdb on failure)

```bash
uv run pytest --pdb
```

## Best Practices

1. **Test one thing per test.** Don't combine multiple assertions into one test.
2. **Use descriptive names.** Test name should describe what's being tested.
3. **Use fixtures.** Mock external dependencies (Azure, file I/O).
4. **Test error paths.** Not just happy paths; verify error messages and exit codes.
5. **Use parametrize for variations.** Don't write 10 similar tests; use `@pytest.mark.parametrize`.
6. **Keep tests fast.** Unit tests should run in milliseconds, not seconds.
7. **Make tests deterministic.** Same input → same output every time.

## Key References

- **pytest docs:** https://docs.pytest.org/
- **pytest-mock:** https://pytest-mock.readthedocs.io/
- **Current tests:** `/tests/`
- **pyproject.toml:** Coverage config, pytest markers, pythonpath
- **CI configuration:** `/.github/workflows/unit-tests.yml`, `/.github/workflows/integration-tests.yml`
