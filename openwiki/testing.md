# Testing Guide

## Test structure

Tests are organized by type and module under `/tests`:

```
tests/
├── conftest.py          # Shared pytest fixtures and configuration
├── test_main.py         # Main entrypoint (exit codes, error handling)
├── test_cli.py          # CLI parsing and file validation
└── test_credentials.py  # Azure credential loading and validation
```

Test markers (configured in `pyproject.toml`):
- `@pytest.mark.unit`: Unit tests for isolated functions/classes (current focus)
- `@pytest.mark.integration`: End-to-end tests with mocked or real Azure (deferred)

## Running tests

```bash
# All tests
uv run pytest

# Unit tests only (current, fast)
uv run pytest -m unit

# Integration tests (deferred)
uv run pytest -m integration

# Specific test file
uv run pytest tests/test_cli.py

# Specific test
uv run pytest tests/test_cli.py::test_parse_args_returns_paths_for_each_argument

# Verbose output
uv run pytest -v

# Show coverage (configured to require 70% minimum)
uv run pytest --cov
```

## Test coverage requirements

- **Minimum:** 70% (enforced by `pytest-cov` via `pyproject.toml`)
- **Target:** 80%+ for business-critical code (validation, error handling, credentials)
- **Coverage report:** `pytest --cov` shows missing lines

## CLI parsing tests (`test_cli.py`)

### Test categories

**Argument parsing:**
- ✓ Multiple file arguments are returned as Path objects
- ✓ Missing arguments trigger usage error (exit code 2)

**File validation (single file):**
- ✓ Extensions `.mp3`, `.wav` (case-insensitive: `.MP3`, `.WAV`) are accepted
- ✓ Nonexistent files raise `MissingFileError`
- ✓ Unsupported extensions raise `UnsupportedFileTypeError`

**Batch validation:**
- ✓ Stops at first invalid file (early exit, no partial validation)

### Representative test

```python
@pytest.mark.unit
@pytest.mark.parametrize("extension", [".mp3", ".wav", ".MP3", ".WAV"], ids=str)
def test_validate_file_accepts_supported_extensions(tmp_path, extension):
    audio_file = tmp_path / f"audio{extension}"
    audio_file.touch()
    
    validate_file(audio_file)  # Should not raise
```

**Key patterns:**
- Use `tmp_path` fixture for temporary files (isolated per test, cleaned up after)
- Parametrize to test multiple inputs (e.g., both `.mp3` and `.wav`)
- Test both happy path and error paths
- Verify exception message contains key details (filename, extension)

## Credentials tests (`test_credentials.py`)

### Test categories

**Happy path:**
- ✓ Both env vars present → returns `AzureCredentials` dataclass

**Error paths:**
- ✓ Endpoint unset or empty → raises `CredentialError` naming `AZURE_SPEECH_ENDPOINT`
- ✓ Key unset or empty → raises `CredentialError` naming `AZURE_SPEECH_KEY`
- ✓ Both unset/empty → raises `CredentialError` naming both variables
- ✓ Error message does not mention variables that *are* present (no noise)

### Representative test

```python
@pytest.mark.unit
@pytest.mark.parametrize(
    ("endpoint_value", "key_value", "expected_present", "expected_missing"),
    [
        pytest.param(None, "secret-key", _KEY_VAR, _ENDPOINT_VAR, id="endpoint_unset"),
        pytest.param("", "secret-key", _KEY_VAR, _ENDPOINT_VAR, id="endpoint_empty"),
        pytest.param("https://example.com", None, _ENDPOINT_VAR, _KEY_VAR, id="key_unset"),
        pytest.param("https://example.com", "", _ENDPOINT_VAR, _KEY_VAR, id="key_empty"),
    ],
)
def test_load_azure_credentials_raises_naming_only_the_missing_variable(
    monkeypatch, endpoint_value, key_value, expected_present, expected_missing
):
    _set_env(monkeypatch, _ENDPOINT_VAR, endpoint_value)
    _set_env(monkeypatch, _KEY_VAR, key_value)
    
    with pytest.raises(CredentialError) as exc_info:
        load_azure_credentials()
    
    message = str(exc_info.value)
    assert expected_missing in message
    assert expected_present not in message
```

**Key patterns:**
- Use `monkeypatch` fixture to set/delete environment variables (isolated, reverted after test)
- Parametrize to test multiple combinations (both vars, each var alone)
- Verify error message precision: names missing vars, doesn't mention present ones
- Test both unset (`None` via `delenv`) and empty string (`""`)

## Main entrypoint tests (`test_main.py`)

### Test categories

- ✓ Returns exit code 0 when validation succeeds
- ✓ Returns exit code 1 when an `AppError` (validation/credential/transcription error) is raised
- ✓ Error message written to stderr
- ✓ Usage errors from argparse exit with code 2 (not caught, allowed to propagate)

### Key patterns

```python
@pytest.mark.unit
def test_main_returns_0_on_success():
    exit_code = main(argv=[])  # Needs to be valid; currently only validation happens
    assert exit_code == 0

@pytest.mark.unit
def test_main_prints_error_and_returns_1_on_app_error(capsys):
    exit_code = main(argv=["nonexistent.mp3"])  # File doesn't exist
    
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "nonexistent.mp3" in captured.err
```

**Fixtures used:**
- `capsys`: Captures stdout/stderr for inspection
- `tmp_path`: Temporary directory for test files
- `monkeypatch`: Mocks environment, function attributes
- `mocker`: (from `pytest-mock`) mocks arbitrary functions/objects

## Conftest and shared fixtures

`conftest.py` can define fixtures used across all test files:

```python
# Example (not yet needed):
@pytest.fixture
def azure_credentials_env(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    return True
```

## Adding new tests

1. **Choose the right test file:**
   - CLI/arg parsing → `test_cli.py`
   - Credential loading → `test_credentials.py`
   - End-to-end flow → `test_main.py` (or new `test_transcription.py` for transcription logic)

2. **Mark with `@pytest.mark.unit` or `@pytest.mark.integration`:**
   ```python
   @pytest.mark.unit
   def test_my_feature():
       ...
   ```

3. **Use fixtures for isolation:**
   - `tmp_path` for file operations
   - `monkeypatch` for environment/global state
   - `capsys` for stdout/stderr capture
   - `mocker` for mocking external calls (e.g., httpx.post)

4. **Test both happy path and error paths:**
   - Success case: function returns expected value
   - Failure case: function raises expected exception with correct message/context

5. **Keep tests focused:**
   - One logical assertion per test (or use parametrization for multiple related cases)
   - Test one thing well rather than many things partially

## Integration testing (deferred)

When issue #8 (transcription call) is implemented, add integration tests that:

1. **Mock the HTTP call** (recommended for fast, reliable tests):
   ```python
   @pytest.mark.integration
   def test_transcribe_file_handles_azure_response(mocker):
       mock_response = {"durationMilliseconds": 12340, "phrases": [...]}
       mocker.patch("httpx.post", return_value=mock_response)
       
       result = transcribe_file(Path("audio.mp3"), credentials)
       
       assert result == mock_response
   ```

2. **Or use a real Azure endpoint** (for end-to-end validation, slower, requires credentials):
   ```python
   @pytest.mark.integration
   def test_transcribe_file_with_real_azure():
       # Requires AZURE_SPEECH_ENDPOINT and AZURE_SPEECH_KEY set
       result = transcribe_file(Path("tests/fixtures/sample.mp3"), credentials)
       
       assert "phrases" in result
       assert result["durationMilliseconds"] > 0
   ```

## Performance & CI expectations

- **Unit tests:** Should complete in <1 second total
- **CI gates:** All tests run on every PR; format/lint/type-check also run
- **Pre-commit hooks:** pytest runs before push (blocks push if tests fail)

See `.github/workflows/unit-tests.yml` and `integration-tests.yml` for CI job definitions.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Test fails locally but passes in CI | Check: env vars, file paths, fixture isolation (monkeypatch not cleaned) |
| Coverage below 70% | Add tests for the uncovered function/branch; use `pytest --cov` to identify gaps |
| Test hangs | Check for infinite loops, missing mock setup, or unhandled blocking I/O |
| Flaky test (passes/fails randomly) | Check for: test order dependency, monkeypatch not reverting, temp file conflicts |

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [pytest parametrization](https://docs.pytest.org/en/stable/parametrize.html)
- [pytest-mock](https://pytest-mock.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- Project standards: [`.claude/rules/pytest-rules.md`](../.claude/rules/pytest-rules.md)
