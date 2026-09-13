# CLI Flow — Argument Parsing through YAML Frontmatter Output

End-to-end walkthrough of what happens when you run `transcribe --manifest manifest.csv --call-db calls.db`.

## High-level flow

```
User: transcribe --manifest manifest.csv --call-db calls.db
   ↓
[Parse & validate arguments]
   ↓
[Load credentials]
   ↓
[For each file in manifest:]
│  ├→ [Check resume: does {stem}-transcript.txt exist with no error?]
│  ├→ [Validate audio file]
│  ├→ [Transcribe via Azure]
│  ├→ [Look up call metadata]
│  ├→ [Transform → YAML frontmatter + body]
│  └→ [Write {stem}-transcript.txt atomically]
   ↓
[Report errors & exit]
```

## Detailed execution path

### 1. Entry point (`src/transcribe/main.py`)

**Function:** `main(argv: list[str] | None = None) → int`

```python
def main(argv: list[str] | None = None) -> int:
    parsed_args = parse_args(sys.argv[1:] if argv is None else argv)  # ← Step 1
    
    try:
        credentials = load_azure_credentials()  # ← Step 2
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    
    # Open the call database once (stays open for all lookups)
    try:
        call_db = CallDatabase(parsed_args.call_db)
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    
    had_failure = False
    for entry in parsed_args.entries:  # ← Step 3: per-file loop
        try:
            _process_file(entry, credentials, call_db, parsed_args.clobber)
        except AppError as err:
            print(f"Error: {err}", file=sys.stderr)
            had_failure = True
    
    return 1 if had_failure else 0  # ← Exit code
```

**Why this structure:**
- Parse and validate CLI args + manifest upfront (fail fast, exit code 2 on usage error)
- Load credentials and call database once (not per-file)
- Process each file independently (collect errors, don't stop on first failure)
- Report all errors to stderr, then exit

### 2. Parse arguments (`src/transcribe/cli.py:parse_args`)

**Input (batch mode):** `argv = ["--manifest", "manifest.csv", "--call-db", "calls.db"]`

**Input (single-file mode):** `argv = ["--ref", "C001", "--target", "5551234567", "--audiopath", "audio.mp3", "--call-db", "calls.db"]`

```python
def parse_args(argv: list[str]) -> ParsedArgs:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    
    # Validate mutual exclusivity and resolve entries
    entries = _resolve_entries(args)  # Returns list[ManifestEntry]
    validate_timestamp_format(args.timestamp_format)  # Fail early on bad strftime format
    
    return ParsedArgs(
        entries=entries,
        clobber=args.clobber,
        call_db=args.call_db,
        destination=args.destination,
        timestamp_format=args.timestamp_format,
    )
```

**Output (batch mode):** `ParsedArgs(entries=[ManifestEntry(ref="C001", target="5551234567", audio_path="audio.mp3"), ...], clobber=False, call_db=Path("calls.db"), destination=None, timestamp_format="%H:%M:%S")`

**Output (single-file mode with options):** `ParsedArgs(entries=[ManifestEntry(ref="C001", target="5551234567", audio_path="audio.mp3")], clobber=False, call_db=Path("calls.db"), destination=Path("/archive"), timestamp_format="%M:%S")`

**Error cases:**
- No args provided: argparse exits with code 2 and prints usage
- Invalid mutual exclusivity (both `--manifest` and `--audiopath`, etc.): exits code 2
- `--call-db` missing or file not found: `ManifestError`, printed to stderr, exit code 1
- Manifest CSV cannot be read or has wrong columns: `ManifestError`, exit code 1

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

### 4. Open call database (`src/transcribe/call_lookup.py:CallDatabase`)

**Input:** `Path("calls.db")`

```python
class CallDatabase:
    def __init__(self, db_path: Path) -> None:
        try:
            self._conn = sqlite3.connect(db_path)
        except sqlite3.Error as err:
            raise CallDbError(f"Cannot open database at {db_path}: {err}") from err
    
    def lookup(self, ref: str, target: str) -> CallRecord | None:
        # Query calls table; see spec/adr/0005
        ...
```

**Error cases:**
- Database file not found or unreadable: raises `CallDbError`
- Caught in `main()`, printed to stderr, exits code 1

### 5. Process one file (`src/transcribe/main.py:_process_entry`)

```python
def _process_entry(
    entry: ManifestEntry,
    credentials: AzureCredentials,
    call_db: sqlite3.Connection,
    options: RunOptions,
) -> bool:
    audio_path = Path(entry.audio_path)
    
    # Step 5a: Resume check (honors --destination and --clobber)
    if not options.clobber and has_existing_transcript(audio_path, entry.ref, entry.target, options.destination):
        return True  # Skip this file
    
    # Step 5b: Validate audio file
    validate_file(audio_path)
    
    # Step 5c: Transcribe via Azure
    result = transcribe_file(audio_path, credentials)
    
    # Step 5d: Look up call metadata
    call_record = find_call_record(call_db, entry.ref, entry.target)  # May be None
    
    # Step 5e: Transform to YAML frontmatter + body (with timestamp format + speaker labels)
    output = transform_result(result, audio_path, call_record, options.timestamp_format)
    
    # Step 5f: Write to output path (respects --destination for naming)
    write_transcript_txt(output, audio_path, entry.ref, entry.target, options.destination)
    
    return False  # Not skipped
```

**RunOptions** carries per-run settings:
- `clobber`: Skip resume check if True
- `destination`: Directory to write transcripts (if None, co-locate with source)
- `timestamp_format`: `time.strftime` format for segment timestamps

#### 5a. Resume check (`src/transcribe/transform.py:has_existing_transcript`)

**Input:** `Path("audio.mp3")`, `ref="C001"`, `target="5551234567"`, `destination=None`

```python
def has_existing_transcript(source_path: Path, ref: str, target: str, destination: Path | None = None) -> bool:
    """Check if a successful transcript already exists at the expected output path."""
    # Calculate output path (respects --destination)
    output_file = output_path(source_path, ref, target, destination)
    
    if not output_file.exists():
        return False
    
    try:
        frontmatter = _read_frontmatter(output_file)
        return "error" not in frontmatter  # Success if no error field
    except (OSError, ValueError, yaml.YAMLError):
        return False  # Corrupt or unreadable = not done, retry
```

**Output:** `True` if file exists and succeeded (no `error` key), `False` otherwise

**Logic:** If `--clobber` is set, this check is skipped entirely and the file is always reprocessed. Output path respects `--destination` flag (e.g., `/archive/C001-5551234567-audio-transcript.txt`).

#### 5b. Validate file (`src/transcribe/cli.py:validate_file`)

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

#### 5c. Transcribe via Azure (`src/transcribe/transcription.py:transcribe_file`)

**Input:** `Path("audio.mp3")`, `AzureCredentials`, `timeout=60.0` (optional)

```python
def transcribe_file(
    path: Path,
    credentials: AzureCredentials,
    timeout: float = 60.0,
) -> dict[str, Any]:
    # Read file from disk
    with open(path, "rb") as f:
        audio_bytes = f.read()
    
    # Build multipart request with multi-locale candidates and diarization
    response = httpx.post(
        f"{credentials.endpoint}/speechtotext/transcriptions:transcribe",
        params={"api-version": "2025-10-15"},
        headers={"Ocp-Apim-Subscription-Key": credentials.key},
        files={
            "audio": audio_bytes,
            "definition": json.dumps({
                "locales": list(transcription.CANDIDATE_LOCALES),  # ("en-US", "es-US")
                "profanityFilterMode": "None",  # Legal discovery requires unfiltered text
                "diarization": {"maxSpeakers": 2, "enabled": True}  # Two-party calls
            })
        },
        timeout=timeout,
    )
    
    if response.status_code != 200:
        raise TranscriptionError(path, f"HTTP {response.status_code}")
    
    return response.json()
```

**Azure response format (success, 2xx):**
```json
{
  "durationMilliseconds": 12340,
  "phrases": [
    {"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US", "speaker": 1},
    {"offsetMilliseconds": 2500, "durationMilliseconds": 2500, "text": "How are you?", "locale": "es-US", "speaker": 2}
  ]
}
```

**Error handling:**
- Network timeout: raises `TranscriptionTimeoutError`, caught in `_process_entry` per-file handler, error output written
- Non-2xx response (Azure 422 `NoLanguageIdentified`): raises `LanguageNotIdentifiedError`, caught per-file, error output written (very short/low-signal audio)
- Non-2xx response (Azure 422 `MultipleLanguagesIdentified`): raises `MultipleLanguagesIdentifiedError`, caught per-file, error output written (mixed-language/code-switching audio)
- Other non-2xx response: raises `TranscriptionError`, caught per-file, error output written
- All error types carry the source path and a reason string for audit trailing

#### 5d. Look up call metadata (`src/transcribe/call_lookup.py:CallDatabase.lookup`)

**Input:** `entry.ref` (string), `entry.target` (string)

```python
def lookup(self, ref: str, target: str) -> CallRecord | None:
    """Query calls table for a record matching (ref, target)."""
    target_digits = _digits(target)  # Normalize to bare digits
    
    query = f"SELECT {_CALL_COLUMNS} FROM calls WHERE ref = ? AND target = ? ORDER BY id LIMIT 1"
    
    try:
        row = self._conn.execute(query, (ref, target_digits)).fetchone()
    except sqlite3.Error as err:
        raise CallDbError(f"Query failed for ref={ref}, target={target}: {err}") from err
    
    if row is None:
        return None  # No matching record; frontmatter will have all fields as null
    
    return CallRecord(*row)  # NamedTuple with all fields
```

**Output:** `CallRecord(ref="C001", target="5551234567", ..., text_message=None)` or `None`

**Error cases:**
- Database query fails: raises `CallDbError`, caught in per-file handler, error-echoing output written

#### 5e. Transform result (`src/transcribe/transform.py:transform_result`)

**Input:** Azure result dict + `Path("audio.mp3")` + `CallRecord | None` + `timestamp_format="%H:%M:%S"`

```python
def transform_result(
    result: dict[str, Any],
    source_path: Path,
    call_record: CallRecord | None,
    timestamp_format: str = DEFAULT_TIMESTAMP_FORMAT,
) -> TranscriptOutput:
    """Transform Azure result + call record into YAML frontmatter + body with speaker labels."""
    
    # Extract and validate phrases
    phrases = result.get("phrases") or []
    if not phrases:
        raise EmptyTranscriptionResultError(source_path)
    
    # Build frontmatter from call_record (or None fields if no record)
    frontmatter = _base_frontmatter(source_path, call_record)
    frontmatter["audio_duration"] = result["durationMilliseconds"]
    frontmatter["detected_locales"] = _detected_locales(phrases)  # List of distinct locales per phrase
    
    # Build segments with speaker labels and timestamps
    segments: list[Segment] = sorted(
        (
            Segment(
                start=phrase["offsetMilliseconds"] / 1000,
                end=(phrase["offsetMilliseconds"] + phrase["durationMilliseconds"]) / 1000,
                text=phrase["text"],
                speaker=phrase.get("speaker"),  # 1, 2, or None
            )
            for phrase in phrases
        ),
        key=lambda segment: segment["start"],
    )
    
    # Render body with speaker labels formatted per timestamp_format
    body = _render_body(segments, timestamp_format)
    
    return TranscriptOutput(frontmatter=frontmatter, body=body)
```

**Helper: `_detected_locales(phrases)`** — Collects distinct locales from all phrases:
```python
def _detected_locales(phrases: list[dict[str, Any]]) -> list[str]:
    """Distinct locales across phrases, sorted (see ADR-0007 on language identification)."""
    return sorted({locale for phrase in phrases if (locale := phrase.get("locale"))})
```

**Helper: `_render_segment(segment, timestamp_format)`** — Formats one segment with speaker:
```python
def _render_segment(segment: Segment, timestamp_format: str) -> str:
    start = _format_timestamp(segment["start"], timestamp_format)
    end = _format_timestamp(segment["end"], timestamp_format)
    timing = f"{start} - {end}"
    if segment["speaker"] is None:
        return f"{timing} {segment['text']}"
    return f"{timing} Speaker {segment['speaker']}: {segment['text']}"
```

**Output schema (on success):**
```
---
source_file: audio.mp3
ref: C001
target: 5551234567
associate: null
direction: null
audio_duration: 12340
detected_locales:
  - en-US
  - es-US
average_confidence: 0.78
coverage_ratio: 0.85
word_density: 1.9
needs_review: false
call_start: null
duration: null
end_time: null
classification: null
call_progress: null
language: en-US
monitor: null
text_message: null
---

[0.0-2.5] Hello world
[2.5-5.0] How are you?
```

**Error cases:**
- No phrases in result: raises `EmptyTranscriptionResultError`

#### 5f. Write output (`src/transcribe/transform.py:write_transcript_file`)

**Input:** `TranscriptOutput` + `Path("audio-transcript.txt")`

```python
def write_transcript_file(output: TranscriptOutput | ErrorOutput, output_path: Path) -> Path:
    """Write YAML frontmatter + body to {stem}-transcript.txt, atomically."""
    
    # Build content
    content = yaml.dump(output.frontmatter, default_flow_style=False)
    content = f"---\n{content}---\n"
    
    if isinstance(output, TranscriptOutput):
        content += f"\n{output.body}"
    
    # Write to temp file first, then atomically rename
    fd, tmp_name = tempfile.mkstemp(dir=output_path.parent, suffix=".txt", ...)
    tmp_path = Path(tmp_name)
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.replace(tmp_path, output_path)  # ← Atomic rename
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise OutputWriteError(output_path, str(err)) from err
    
    return output_path
```

**Side effects:**
- Creates `{stem}-transcript.txt` in the same directory as the input audio file
- Uses atomic rename to ensure no partial/corrupt files on failure

**Error cases:**
- Permission denied: raises `OutputWriteError`
- Disk full: raises `OutputWriteError`

### 6. Error handling during per-file processing

When any exception is raised inside `_process_file()`, the per-file handler catches it:

```python
for entry in parsed_args.entries:
    try:
        _process_file(entry, credentials, call_db, parsed_args.clobber)
    except AppError as err:
        print(f"Error: {err}", file=sys.stderr)
        
        # Try to write an error-echoing output file (ADR-0004)
        audio_path = Path(entry.audio_path)
        output_path = audio_path.with_stem(audio_path.stem + "-transcript")
        try:
            error_output = ErrorOutput(
                frontmatter={
                    "source_file": audio_path.name,
                    "ref": entry.ref,
                    "target": entry.target,
                    "error": str(err),
                }
            )
            write_transcript_file(error_output, output_path)
        except Exception:
            pass  # Error output write failed; at least stderr has the message
        
        had_failure = True
```

**Result:** Every input file gets an output file (success or error), ensuring batch output is a complete audit trail.

### 7. Exit and error reporting

**Success case** (all files processed, all succeeded):
```
$ transcribe --manifest manifest.csv --call-db calls.db
# No output to stderr
$ ls *.txt
audio1-transcript.txt  audio2-transcript.txt
$ echo $?
0
```

**Failure case** (one file failed):
```
$ transcribe --ref C001 --target 5551234567 --audiopath missing.mp3 --call-db calls.db
Error: file not found: missing.mp3
$ ls *.txt
missing-transcript.txt  # Has "error" field in frontmatter
$ echo $?
1
```

**Multiple failures** (batch with errors collected):
```
$ transcribe --manifest manifest.csv --call-db calls.db
Error: file not found: audio2.mp3
Error: HTTP 401 when calling Azure for audio3.mp3
$ ls *.txt
audio1-transcript.txt  audio2-transcript.txt  audio3-transcript.txt
$ echo $?
1
```

**Resume** (re-running, skips successful files):
```
$ transcribe --manifest manifest.csv --call-db calls.db  # First run
Error: file not found: audio2.mp3
# audio1 and audio3 succeeded; audio2 failed

$ transcribe --manifest manifest.csv --call-db calls.db  # Second run
Error: file not found: audio2.mp3  # Only audio2 retried, not audio1/audio3
```

**Clobber** (force full re-run):
```
$ transcribe --manifest manifest.csv --call-db calls.db --clobber
# All files reprocessed, even if they already succeeded
```

## Exception hierarchy

All exceptions inherit from `AppError`. Caught in `main()` per-file handler, each prints `f"Error: {err}"` to stderr and attempts to write error-echoing output.

**Per-file failures** (caught in loop, error output written):
```
AppError (base)
├── MissingFileError(path)            ← Audio file doesn't exist
├── UnsupportedFileTypeError(path)     ← Extension not .mp3 or .wav
├── TranscriptionError(path, reason)   ← HTTP non-2xx from Azure
├── TranscriptionTimeoutError(path)    ← Network timeout
├── EmptyTranscriptionResultError(path) ← Azure returned empty phrases
├── CallDbError(reason)                ← Database lookup failed
├── CallRecordNotFoundError(ref, target) ← No matching call record (optional, see spec)
└── OutputWriteError(path, reason)     ← Can't write output file
```

**Startup failures** (abort before per-file loop, no output files):
```
├── CredentialError                    ← AZURE_SPEECH_* env var missing
├── ManifestError                      ← Argument parsing or manifest loading failed
└── CallDbError                        ← Call database cannot be opened
```

## Key design decisions

1. **Upfront parsing & validation:** All CLI args + manifest validated before any credentials/Azure calls → fail fast on bad input (exit code 2)
2. **Credentials & database loaded once:** Not per-file, saves repeated lookups
3. **Resume on successful output:** Check if `{stem}-transcript.txt` exists and has no `error` key; skip if so. `--clobber` overrides.
4. **Per-file error collection:** One file's failure doesn't stop the rest; all errors reported to stderr before exit
5. **Error-echoing output:** Every input file gets an output file (success or error), enabling audit trails and resume without separate tracking (ADR-0004)
6. **Atomic output writes:** Temp file → rename ensures no corrupt `.txt` files
7. **Single-threaded:** Files processed sequentially (Phase 2 may add parallelization)

## Common error scenarios

### No arguments
```
$ transcribe
usage: transcribe [-h] [--manifest ...] [--audiopath ...] [--ref ...] [--target ...] [--call-db ...] [--clobber]
transcribe: error: must provide either --manifest or (--audiopath, --ref, --target)
$ echo $?
2
```

### Missing call database
```
$ transcribe --ref C001 --target 5551234567 --audiopath audio.mp3 --call-db missing.db
Error: Invalid --call-db path: missing.db does not exist
$ echo $?
1
```

### Missing Azure credential
```
$ transcribe --ref C001 --target 5551234567 --audiopath audio.mp3 --call-db calls.db
Error: Missing required environment variable(s): AZURE_SPEECH_KEY
$ echo $?
1
```

### Audio file not found (per-file)
```
$ transcribe --ref C001 --target 5551234567 --audiopath missing.mp3 --call-db calls.db
Error: file not found: missing.mp3
$ ls *.txt
missing-transcript.txt  # Contains error in frontmatter
$ echo $?
1
```

### Unsupported audio extension (per-file)
```
$ transcribe --ref C001 --target 5551234567 --audiopath audio.flac --call-db calls.db
Error: unsupported file type: audio.flac (supported: .mp3, .wav)
$ ls *.txt
audio-transcript.txt  # Contains error in frontmatter
$ echo $?
1
```

### Azure error, e.g., invalid key (per-file)
```
$ transcribe --ref C001 --target 5551234567 --audiopath audio.mp3 --call-db calls.db
Error: HTTP 401 when calling Azure for audio.mp3
$ ls *.txt
audio-transcript.txt  # Contains error in frontmatter
$ echo $?
1
```

### Batch with mixed results
```
$ transcribe --manifest manifest.csv --call-db calls.db
Error: file not found: audio2.mp3
Error: HTTP 500 when calling Azure for audio3.mp3
$ ls *.txt
audio1-transcript.txt  # Success
audio2-transcript.txt  # Error: file not found
audio3-transcript.txt  # Error: HTTP 500
$ echo $?
1
```

## Related documentation

- **Architecture:** [architecture/overview.md](../architecture/overview.md) — Component relationships and design rationale
- **Testing:** [testing/overview.md](../testing/overview.md) — How to test each layer
- **Specification:** [domain/spec-and-contracts.md](../domain/spec-and-contracts.md) — Input/output contracts
- **Azure Integration:** [integrations/azure-speech.md](../integrations/azure-speech.md) — Endpoint details, request/response format
