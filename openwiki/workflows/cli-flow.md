# CLI Flow — Argument Parsing through Output

End-to-end walkthrough of what happens when you run `transcribe audio.mp3`.

## High-level flow

```
User: transcribe audio.mp3
   ↓
[Parse args & load credentials]
   ↓
[For each file: transcribe → transform → write output]
   ↓
[Report errors & exit]
```

## Detailed execution path

### 1. Entry point (`src/transcribe/main.py`)

**Function:** `main(argv: list[str] | None = None) → int`

```python
def main(argv: list[str] | None = None) -> int:
    paths = parse_args(sys.argv[1:] if argv is None else argv)  # ← Step 1
    
    try:
        credentials = load_azure_credentials()  # ← Step 2
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    
    had_failure = False
    for path in paths:  # ← Step 3: per-file loop
        try:
            _process_file(path, credentials)
        except AppError as err:
            print(f"Error: {err}", file=sys.stderr)
            had_failure = True
    
    return 1 if had_failure else 0  # ← Exit code
```

**Why this structure:**
- Parse and validate all CLI args upfront (fail fast)
- Load credentials once (not per-file)
- Process each file independently (collect errors, don't stop on first failure)
- Report all errors to stderr, then exit

### 2. Parse arguments (`src/transcribe/cli.py:parse_args`)

**Input:** `argv = ["audio.mp3", "interview.wav"]`

```python
def parse_args(argv: list[str]) -> list[Path]:
    parser = build_arg_parser()
    args = parser.parse_args(argv)  # Let argparse handle usage & exit code 2
    return [Path(f) for f in args.files]
```

**Output:** `[Path("audio.mp3"), Path("interview.wav")]`

**Error cases:**
- No args provided: argparse exits with code 2 and prints usage
- Invalid options: argparse exits with code 2

### 3. Load credentials (`src/transcribe/credentials.py:load_azure_credentials`)

**Input:** Environment variables `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY`

```python
def load_azure_credentials() -> AzureCredentials:
    endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT", "")
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    
    missing = []
    if not endpoint:
        missing.append("AZURE_SPEECH_ENDPOINT")
    if not key:
        missing.append("AZURE_SPEECH_KEY")
    
    if missing:
        raise CredentialError(f"Missing required environment variable(s): {', '.join(missing)}")
    
    return AzureCredentials(endpoint=endpoint, key=key)
```

**Output:** `AzureCredentials(endpoint="https://...", key="sk-...")`

**Error cases:**
- Either env var missing or empty: raises `CredentialError`
- Caught in `main()`, printed to stderr, exits code 1

### 4. Process one file (`src/transcribe/main.py:_process_file`)

```python
def _process_file(path: Path, credentials: AzureCredentials) -> None:
    validate_file(path)  # ← Step 4a: validate
    result = transcribe_file(path, credentials)  # ← Step 4b: transcribe
    output = transform_result(result, path)  # ← Step 4c: transform
    write_transcript_json(output, path)  # ← Step 4d: write
```

#### 4a. Validate file (`src/transcribe/cli.py:validate_file`)

**Input:** `Path("audio.mp3")`

```python
def validate_file(path: Path) -> None:
    if not path.exists():
        raise MissingFileError(path)
    
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:  # {".mp3", ".wav"}
        raise UnsupportedFileTypeError(path)
```

**Exit conditions:**
- File not found: raises `MissingFileError`
- Extension not in {".mp3", ".wav"}: raises `UnsupportedFileTypeError`

#### 4b. Transcribe via Azure (`src/transcribe/transcription.py:transcribe_file`)

**Input:** `Path("audio.mp3")`, `AzureCredentials`

```python
def transcribe_file(
    path: Path,
    credentials: AzureCredentials,
    requested_locale: str = DEFAULT_LOCALE,
) -> dict[str, Any]:
    # Read file from disk
    with open(path, "rb") as f:
        audio_bytes = f.read()
    
    # Build multipart request
    response = httpx.post(
        f"{credentials.endpoint}/cognitiveservices/v1/speechtotext/transcriptions:transcribe",
        params={"api-version": "2025-10-15"},
        headers={"Ocp-Apim-Subscription-Key": credentials.key},
        files={
            "audio": audio_bytes,
            "definition": json.dumps({"locales": [requested_locale]})
        },
        timeout=300,
    )
    
    if response.status_code != 200:
        raise TranscriptionError(path, f"HTTP {response.status_code}")
    
    return response.json()
```

**Azure response format:**
```json
{
  "durationMilliseconds": 12340,
  "phrases": [
    {"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}
  ]
}
```

**Error cases:**
- Network timeout: raises `TranscriptionTimeoutError`
- Non-2xx response: raises `TranscriptionError`

#### 4c. Transform result (`src/transcribe/transform.py:transform_result`)

**Input:** Azure result dict + `Path("audio.mp3")`

```python
def transform_result(
    result: dict[str, Any],
    source_path: Path,
    requested_locale: str = "en-US",
) -> TranscriptOutput:
    phrases = result.get("phrases") or []
    if not phrases:
        raise EmptyTranscriptionResultError(source_path)
    
    segments: list[Segment] = sorted(
        (
            Segment(
                start=phrase["offsetMilliseconds"] / 1000,
                end=(phrase["offsetMilliseconds"] + phrase["durationMilliseconds"]) / 1000,
                text=phrase["text"],
            )
            for phrase in phrases
        ),
        key=lambda segment: segment["start"],
    )
    
    return TranscriptOutput(
        source_file=source_path.name,
        language=phrases[0].get("locale") or requested_locale,
        duration_seconds=result["durationMilliseconds"] / 1000,
        segments=segments,
    )
```

**Output schema:**
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

**Error cases:**
- No phrases in result: raises `EmptyTranscriptionResultError`

#### 4d. Write output (`src/transcribe/transform.py:write_transcript_json`)

**Input:** `TranscriptOutput` + `Path("audio.mp3")`

```python
def write_transcript_json(output: TranscriptOutput, source_path: Path) -> Path:
    destination = source_path.with_name(source_path.name + ".json")  # audio.mp3.json
    
    # Write to temp file first, then atomically rename
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, ...)
    tmp_path = Path(tmp_name)
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(output, tmp_file, indent=2)
        os.replace(tmp_path, destination)  # ← Atomic rename
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise OutputWriteError(destination, str(err)) from err
    
    return destination
```

**Side effects:**
- Creates `audio.mp3.json` in the same directory as the input file
- Uses atomic rename to ensure no partial/corrupt files on failure

**Error cases:**
- Permission denied: raises `OutputWriteError`
- Disk full: raises `OutputWriteError`

### 5. Exit and error reporting

**Success case** (all files processed):
```
$ transcribe audio.mp3 interview.wav
# No output
$ echo $?
0
```

**Failure case** (one or more files failed):
```
$ transcribe audio.mp3 missing.wav
Error: file not found: missing.wav
$ echo $?
1
```

**Multiple failures** (errors collected and reported):
```
$ transcribe a.mp3 missing.wav b.mp3 broken.wav
Error: file not found: missing.wav
Error: HTTP 401 when calling Azure for broken.wav
$ echo $?
1
```

## Exception hierarchy

All exceptions inherit from `AppError`. Caught in `main()`, each prints `f"Error: {err}"` and sets `had_failure = True`.

```
AppError (base)
├── MissingFileError(path)        ← File doesn't exist
├── UnsupportedFileTypeError(path) ← Extension not .mp3 or .wav
├── CredentialError               ← Env var missing
├── TranscriptionError(path, reason) ← HTTP non-2xx from Azure
├── TranscriptionTimeoutError(path, timeout) ← Network timeout
├── EmptyTranscriptionResultError(path) ← Azure returned no phrases
└── OutputWriteError(path, reason) ← Can't write JSON file
```

## Key design decisions

1. **Upfront parsing & validation:** All CLI args validated before any credentials/Azure calls → fail fast on bad input
2. **Credentials loaded once:** Not per-file, saves repeated env var lookups
3. **Per-file error collection:** One file's failure doesn't stop the rest; all errors reported before exit
4. **Atomic output writes:** Temp file → rename ensures no corrupt .json files
5. **Single-threaded:** Files processed sequentially (Phase 2 may add parallelization)

## Common error scenarios

### No arguments
```
$ transcribe
usage: transcribe [-h] files [files ...]
transcribe: error: the following arguments are required: files
$ echo $?
2
```

### Missing env var
```
$ transcribe audio.mp3
Error: Missing required environment variable(s): AZURE_SPEECH_KEY
$ echo $?
1
```

### File not found
```
$ transcribe missing.mp3
Error: file not found: missing.mp3
$ echo $?
1
```

### Unsupported extension
```
$ transcribe audio.flac
Error: unsupported file type: audio.flac (supported: .mp3, .wav)
$ echo $?
1
```

### Azure error (e.g., invalid key)
```
$ transcribe audio.mp3  # With wrong AZURE_SPEECH_KEY
Error: HTTP 401 when calling Azure for audio.mp3
$ echo $?
1
```

## Related documentation

- **Architecture:** [architecture/overview.md](../architecture/overview.md) — Component relationships and design rationale
- **Testing:** [testing/overview.md](../testing/overview.md) — How to test each layer
- **Specification:** [domain/spec-and-contracts.md](../domain/spec-and-contracts.md) — Input/output contracts
- **Azure Integration:** [integrations/azure-speech.md](../integrations/azure-speech.md) — Endpoint details, request/response format
