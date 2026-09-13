# transcribe — Quick Start

**transcribe** is a Python CLI that transcribes local audio files using **Azure AI Speech**, producing SharePoint-ready text transcripts with call metadata. It sends audio directly to Azure's fast (synchronous) transcription endpoint and outputs plain-text files with YAML frontmatter containing call details.

**Status:** Phase 1 complete (local fast transcription, call metadata lookup, SharePoint output format). Phase 2 (blob-staged batch) deferred; see `/spec/adr/0003-fast-transcription-for-local-files.md`.

## What it does

**Single-file mode:**
```bash
transcribe --ref CALL-001 --target 5551234567 --audiopath audio.mp3
```

**Batch mode (CSV manifest):**
```bash
transcribe --manifest manifest.csv --call-db calls.db
```

For each input audio file:
1. **Validate**: Check file exists, extension supported (`.mp3`, `.wav`), call database accessible
2. **Load credentials**: Read `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` from environment
3. **Look up call metadata**: Query the call-inventory SQLite database by `ref` and `target`
4. **Transcribe**: POST file to Azure's fast transcription endpoint
5. **Transform**: Build YAML frontmatter + timestamped transcript body
6. **Output**: Write `{source_file}-transcript.txt` (or error output on failure)

Output format (success):
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
classification: "Business"
call_progress: "Completed"
language: en
monitor: "Agent 1"
text_message: null
---

[0.0-2.5] Hello, this is the call center.
[2.5-5.0] How can I assist you today?
```

**Error output** (when transcription or lookup fails):
```
---
source_file: audio.mp3
ref: CALL-001
target: 5551234567
error: "Transcription failed: timeout"
---
```
Every input file always gets an output file (success or error), enabling resume and audit trailing.

## Quick Start

### Setup (one-time)
```bash
make setup
# Installs dependencies and Git hooks (pre-commit, ruff, mypy)
```

### Environment variables
```bash
export AZURE_SPEECH_ENDPOINT=https://your-region.cognitiveservices.azure.com
export AZURE_SPEECH_KEY=your-key-here
```

To provision Azure resources:
```bash
cd infra
cp terraform.tfvars.example terraform.tfvars  # edit with your values
terraform init
terraform apply -var-file=terraform.tfvars
```

The outputs `speech_endpoint` and `speech_primary_key` feed the env vars above. See `/infra/README.md` for details.

### Run, test, lint
```bash
# Single-file mode
uv run transcribe --ref C001 --target 5551234567 --audiopath audio.mp3 --call-db calls.db

# Batch mode
uv run transcribe --manifest manifest.csv --call-db calls.db

# Resume a partial run (skips files that already have successful output)
uv run transcribe --manifest manifest.csv --call-db calls.db

# Reprocess all files, even if they succeeded before
uv run transcribe --manifest manifest.csv --call-db calls.db --clobber

# Run tests and checks
uv run pytest                                 # All tests
make check                                    # Lint + type-check + tests
```

## Documentation Map

| Topic | Purpose | Start Here |
|-------|---------|-----------|
| **Architecture** | Components, dependencies, design decisions | [architecture/overview.md](architecture/overview.md) |
| **Specification** | Input/output contracts, validation rules, done criteria | [domain/spec-and-contracts.md](domain/spec-and-contracts.md) |
| **CLI Workflow** | Argument parsing → validation → transcription → output | [workflows/cli-flow.md](workflows/cli-flow.md) |
| **Azure Integration** | Endpoint, request/response mapping, error handling | [integrations/azure-speech.md](integrations/azure-speech.md) |
| **Setup & Ops** | Local dev, Terraform, infra, Git hooks | [operations/setup-and-run.md](operations/setup-and-run.md) |
| **Testing** | Test structure, running, coverage | [testing/overview.md](testing/overview.md) |

## Repository Structure at a Glance

```
├── src/
│   └── transcribe/
│       ├── main.py          # CLI entrypoint
│       ├── cli.py           # Argument parsing, file/database validation
│       ├── credentials.py    # Azure credential loading
│       ├── call_lookup.py    # Call metadata lookup from SQLite
│       ├── errors.py        # Exception hierarchy
│       ├── transcription.py  # Azure transcription calls
│       └── transform.py      # YAML frontmatter + body output
├── tests/
│   ├── test_cli.py          # Unit: parsing, validation
│   ├── test_credentials.py   # Unit: env var loading
│   ├── test_transcription.py # Unit: Azure calls
│   ├── test_transform.py     # Unit: transformation & output
│   └── test_main.py          # Integration tests
├── spec/
│   ├── spec.md          # Full specification
│   ├── build-order.md   # Issue sequencing
│   └── adr/             # Architectural decisions
│       ├── 0001-azure-ai-speech-transcription.md
│       ├── 0002-terraform-for-azure-infra.md
│       └── 0003-fast-transcription-for-local-files.md
├── infra/
│   └── *.tf             # Terraform: Azure Cognitive Services resource
├── .claude/             # Agent rules, standards, skills
├── .github/workflows/   # CI/CD: unit tests, integration, type-check, lint, OpenWiki update
├── pyproject.toml       # Dependencies (httpx), Python 3.13, tooling config
├── Makefile             # Common commands (setup, test, lint, format)
└── openwiki/            # Generated wiki (read-only, regenerate with `openwiki code --update`)
```

## Key Files to Know

| Path | What | Why |
|------|------|-----|
| `/spec/spec.md` | Specification | Complete input/output contracts, done criteria, Phase 2 plan |
| `/spec/adr/0003-fast-transcription-for-local-files.md` | Design decision | Why fast (sync) for local files |
| `/spec/adr/0004-error-echoing-output-and-resume.md` | Design decision | Error output schema and `--clobber` resume flag |
| `/spec/adr/0005-direct-sqlite-read-of-call-inventory-index.md` | Design decision | Call metadata lookup without `wireline` dependency |
| `/spec/adr/0006-yaml-frontmatter-txt-output.md` | Design decision | YAML frontmatter + text body for SharePoint ingestion |
| `/src/transcribe/main.py` | Entrypoint | CLI orchestration: parse → validate → transcribe → lookup → transform → write |
| `/src/transcribe/cli.py` | Validation | Argument parsing (--manifest, --audiopath/--ref/--target, --call-db, --clobber); file/db validation |
| `/src/transcribe/call_lookup.py` | Call metadata | SQLite query by ref+target; calls-table contract from call-inventory |
| `/src/transcribe/transcription.py` | Transcription | HTTP POST to Azure fast endpoint; handles responses and errors |
| `/src/transcribe/transform.py` | Output | Builds YAML frontmatter + body; writes FILE-transcript.txt atomically; error handling |
| `/src/transcribe/credentials.py` | Credential handling | Loads, validates `AZURE_SPEECH_*` env vars; raises if missing |
| `/src/transcribe/errors.py` | Exceptions | Hierarchy: AppError subclasses for each failure mode (validation, transcription, lookup, I/O) |
| `/infra/main.tf` | Infrastructure | Terraform: provisions Azure Cognitive Services Speech resource |
| `/.github/workflows/ci.yml` | CI gate | Orchestrates lint → type-check → unit tests → integration tests |
| `/CLAUDE.md` | Agent brief | Project profile, enabled/disabled features, standards imports |

## Current Implementation Status

### ✅ Complete (Phase 1)
- **Issue #6**: CLI argument validation (file existence, extension)
- **Issue #7**: Azure credential validation (env var loading)
- **Issue #8**: Fast-transcription request (POST file to Azure endpoint)
- **Issue #10**: Output transformation and atomic file write
- **Issue #11**: End-to-end orchestration and per-file error handling
- **Issue #18**: Error-echoing output and resume via `--clobber`
- **Issue #20**: Call metadata lookup and SharePoint-ready YAML+text output

### 📋 Deferred (Phase 2)
- **Issue #9**: Batch polling (not for fast-transcription path)
- Blob upload, SAS generation, batch submit (Phase 2, see `/spec/build-order.md`)

## Where to Start

**I'm implementing the transcription call:**
→ Read [Architecture](architecture/overview.md) + [Azure Integration](integrations/azure-speech.md) + [Specification](domain/spec-and-contracts.md)

**I'm debugging a test or error:**
→ Read [Testing Guide](testing/overview.md) + [CLI Workflow](workflows/cli-flow.md)

**I'm setting up locally or running the CLI:**
→ Read [Setup & Operations](operations/setup-and-run.md)

**I'm adding a feature or understanding overall design:**
→ Read [Specification](domain/spec-and-contracts.md) + the relevant ADR in `/spec/adr/`

## Key Rules

- **Wiki is generated:** Do not hand-edit `/openwiki/`. Regenerate with `openwiki code --update` after code changes.
- **Credentials:** Never commit `.env`, `terraform.tfvars`, or Azure keys. Use environment variables or secret managers.
- **Git hooks:** `make setup` installs pre-commit hooks. CI enforces these regardless.
- **Template sync:** Check compatibility with `make template-check`; use `update-from-template` skill for updates.

### Test
```bash
uv run pytest                # all tests
uv run pytest -m unit        # unit tests only
uv run pytest -m integration # integration tests only
```

### Lint & format
```bash
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy src        # type-check
```

## Architecture overview

The CLI follows a **layered architecture**:

- **CLI layer** (`cli.py`): Argument parsing and file validation — runs before any Azure call
- **Credentials layer** (`credentials.py`): Loads and validates Azure Speech credentials from environment
- **Error handling** (`errors.py`): Domain-specific exception hierarchy for expected failures
- **Main entrypoint** (`main.py`): Orchestrates the pipeline and converts exceptions to exit codes

See [Architecture & Workflows](./architecture.md) for implementation details.

## Major workflows

### Current phase: Local files via fast transcription

1. **Parse & validate CLI arguments** ([issue #6](https://github.com/njrenaissance/transcribe/issues/6))
   - Reject if no file arguments given
   - Reject nonexistent files
   - Reject unsupported file types

2. **Validate credentials** ([issue #7](https://github.com/njrenaissance/transcribe/issues/7))
   - Load `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` from environment
   - Fail fast if either is missing or empty

3. **Transcribe local file** ([issue #8](https://github.com/njrenaissance/transcribe/issues/8))
   - POST file as `multipart/form-data` to Azure's fast transcription endpoint
   - Return inline transcript (no polling)

4. **Transform & output** ([issue #10](https://github.com/njrenaissance/transcribe/issues/10))
   - Map Azure's response to the spec's output schema
   - Write `FILE.json` with segments and timestamps

5. **End-to-end orchestration** ([issue #11](https://github.com/njrenaissance/transcribe/issues/11))
   - Process one or more files with per-file error handling
   - Report errors to stderr; exit 0 only if all files succeed

**Future phase (Phase 2, deferred):** Blob-staged batch transcription for larger files and bulk audio. See [spec.md](../spec/spec.md) for details.

## Key domains

- **Specification & design**: [spec.md](../spec/spec.md) — functional requirements, input/output schema, error criteria
- **Architecture & decision records**: [Architecture](./architecture.md), [ADRs](../spec/adr/)
- **Credentials & environment**: [credentials.py](../src/credentials.py) — loads Azure Speech credentials
- **Error handling**: [errors.py](../src/errors.py) — exception hierarchy for validation, credentials, transcription failures
- **CLI parsing**: [cli.py](../src/cli.py) — argument parsing, file existence/extension validation
- **Testing**: [Testing Guide](./testing.md) — unit & integration test structure

## Infrastructure & operations

Azure resources are provisioned with Terraform under `/infra`. See [infra/README.md](../infra/README.md) to:
- Create or update a Cognitive Services Speech resource
- Extract `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_KEY` for your environment

## Development practices

- **Code style**: Python Clean Code + Gang of Four patterns where applicable (see [CLAUDE.md](../CLAUDE.md))
- **Git hooks**: Local quality gates via pre-commit: commit runs ruff + mypy; push runs pytest
- **CI/CD**: GitHub Actions runs format, lint, type-check, and unit/integration tests on every PR
- **Template sync**: This project is generated from the `basic` cookiecutter template and linked via [cruft](https://cruft.github.io/cruft/). See [README.md](../README.md) for template update procedures
- **Documentation**: Hand-written docs in `/spec` and `/infra`; auto-generated code docs in `/openwiki` (this directory)

## Common tasks

| Task | Command |
|------|---------|
| Install dependencies | `make setup` or `uv sync` |
| Run the CLI | `uv run python src/main.py FILE.mp3` |
| Run all tests | `uv run pytest` |
| Run unit tests | `uv run pytest -m unit` |
| Format code | `uv run ruff format .` |
| Lint | `uv run ruff check .` |
| Type-check | `uv run mypy src` |
| Provision Azure resources | `cd infra && terraform init && terraform apply` |
| Update from template | `.claude/skills/update-from-template/SKILL.md` (or `uvx cruft update`) |

## Next steps

- Read [Architecture & Workflows](./architecture.md) for implementation details and how to modify the pipeline
- See [Testing Guide](./testing.md) for test structure and how to add tests
- Check [spec.md](../spec/spec.md) for functional requirements and exit codes
- Review [ADRs](../spec/adr/) (Architecture Decision Records) for design rationale
