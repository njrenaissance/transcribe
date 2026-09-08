# Source Map

Quick navigation to the main source files, specifications, and infrastructure code.

## Source structure

```
transcribe/
├── src/
│   └── transcribe/
│       ├── __init__.py          # Package marker
│       ├── main.py              # CLI entrypoint & orchestration
│       ├── cli.py               # Argument parsing & file validation
│       ├── credentials.py       # Azure credential loading
│       ├── errors.py            # Exception hierarchy
│       ├── transcription.py     # Azure fast-transcription HTTP calls
│       └── transform.py         # Result transformation & JSON output
├── tests/
│   ├── conftest.py          # Pytest configuration & shared fixtures
│   ├── test_main.py         # Entrypoint tests
│   ├── test_cli.py          # CLI parsing & validation tests
│   ├── test_credentials.py  # Credential loading tests
│   ├── test_transcription.py # Transcription HTTP call tests
│   └── test_transform.py     # Result transformation & output tests
├── spec/
│   ├── spec.md              # Functional specification (authoritative)
│   ├── build-order.md       # Issue sequencing & Phase 1/2 plan
│   └── adr/
│       ├── 0001-azure-ai-speech-transcription.md
│       ├── 0002-terraform-for-azure-infra.md
│       └── 0003-fast-transcription-for-local-files.md
├── infra/
│   ├── README.md            # Terraform setup instructions
│   ├── main.tf              # Azure resource definitions
│   ├── variables.tf         # Variable declarations
│   ├── outputs.tf           # Output values (endpoint, key)
│   ├── versions.tf          # Provider versions
│   ├── terraform.tfvars.example  # Example configuration
│   └── terraform.tfstate*   # Local state (git-ignored)
├── .claude/
│   ├── rules/               # Coding standards (python-lang.md, pytest-rules.md, github-actions.md)
│   ├── standards/           # Cross-project guidelines (error-handling.md, testing.md, wiki.md, etc.)
│   ├── skills/              # Agent automation skills
│   └── settings.json        # IDE/editor config hints
├── .github/workflows/       # GitHub Actions CI/CD
├── .pre-commit-config.yaml  # Local Git hooks config
├── pyproject.toml           # Python project metadata, dependencies, tool config
├── Makefile                 # Development commands (make setup, make test, etc.)
├── README.md                # Project overview & getting started
├── CLAUDE.md                # Agent briefing document
└── AGENTS.md                # Agent task coordination
```

## Key files by concern

### Functional requirements & design

| File | Purpose |
|------|---------|
| [spec/spec.md](../spec/spec.md) | **Authoritative spec:** input/output contract, done criteria, error codes |
| [spec/build-order.md](../spec/build-order.md) | Issue sequencing, Phase 1 (current) vs Phase 2 (deferred) |
| [spec/adr/0001](../spec/adr/0001-azure-ai-speech-transcription.md) | Why Azure AI Speech (not local ML) |
| [spec/adr/0002](../spec/adr/0002-terraform-for-azure-infra.md) | Why Terraform (not manual Azure Portal, not remote state) |
| [spec/adr/0003](../spec/adr/0003-fast-transcription-for-local-files.md) | Why fast endpoint (not batch), Phase 1 priority |

### Implementation

| File | Purpose | Status |
|------|---------|--------|
| [src/transcribe/main.py](../src/transcribe/main.py) | CLI entrypoint; orchestrates parse → validate → transcribe → transform | ✓ Done (issues #6, #7, #8, #10, #11) |
| [src/transcribe/cli.py](../src/transcribe/cli.py) | Argument parsing & file validation (`validate_file`, `validate_files`) | ✓ Done (issue #6) |
| [src/transcribe/credentials.py](../src/transcribe/credentials.py) | Load & validate Azure Speech env vars | ✓ Done (issue #7) |
| [src/transcribe/errors.py](../src/transcribe/errors.py) | Exception hierarchy (`AppError`, `MissingFileError`, `TranscriptionError`, etc.) | ✓ Done |
| [src/transcribe/transcription.py](../src/transcribe/transcription.py) | Azure fast-transcription HTTP calls via httpx | ✓ Done (issue #8) |
| [src/transcribe/transform.py](../src/transcribe/transform.py) | Transform Azure result to output schema & atomic JSON write | ✓ Done (issue #10) |
| [tests/test_main.py](../tests/test_main.py) | Tests for entrypoint behavior, exit codes, error messages | ✓ Done |
| [tests/test_cli.py](../tests/test_cli.py) | Tests for arg parsing, file existence, file type validation | ✓ Done (issue #6) |
| [tests/test_credentials.py](../tests/test_credentials.py) | Tests for credential loading, env var validation | ✓ Done (issue #7) |
| [tests/test_transcription.py](../tests/test_transcription.py) | Tests for Azure HTTP call & error handling | ✓ Done (issue #8) |
| [tests/test_transform.py](../tests/test_transform.py) | Tests for schema transformation & output file writing | ✓ Done (issue #10) |

### Infrastructure & operations

| File | Purpose |
|------|---------|
| [infra/README.md](../infra/README.md) | Terraform setup: provisioning, extracting credentials, state management |
| [infra/main.tf](../infra/main.tf) | Azure resource group, Cognitive Services Speech account |
| [infra/variables.tf](../infra/variables.tf) | Terraform variables (region, account name, SKU) |
| [infra/outputs.tf](../infra/outputs.tf) | Outputs: endpoint URL, API key |
| [infra/terraform.tfvars.example](../infra/terraform.tfvars.example) | Example Terraform values (git-ignored when copied to `.tfvars`) |

### Configuration & standards

| File | Purpose |
|------|---------|
| [pyproject.toml](../pyproject.toml) | Python project metadata, dependencies, pytest/coverage/ruff/mypy config |
| [.pre-commit-config.yaml](../.pre-commit-config.yaml) | Local Git hooks (ruff, mypy, pytest) |
| [Makefile](../Makefile) | `make setup`, `make test`, `make lint`, etc. |
| [.claude/rules/python-lang.md](../.claude/rules/python-lang.md) | Python coding standards |
| [.claude/rules/pytest-rules.md](../.claude/rules/pytest-rules.md) | Pytest/testing conventions |
| [.claude/standards/error-handling.md](../.claude/standards/error-handling.md) | Exception hierarchy design |
| [.claude/standards/testing.md](../.claude/standards/testing.md) | Testing strategy & coverage requirements |
| [.claude/standards/decisions.md](../.claude/standards/decisions.md) | ADR (Architecture Decision Record) guidelines |
| [.claude/standards/wiki.md](../.claude/standards/wiki.md) | OpenWiki documentation standards |

### CI/CD

| File | Purpose |
|------|---------|
| [.github/workflows/unit-tests.yml](../.github/workflows/unit-tests.yml) | Runs `pytest -m unit` on PR/push |
| [.github/workflows/integration-tests.yml](../.github/workflows/integration-tests.yml) | Runs `pytest -m integration` (deferred, no tests yet) |
| [.github/workflows/format-lint.yml](../.github/workflows/format-lint.yml) | Runs `ruff format --check` + `ruff check` |
| [.github/workflows/type-check.yml](../.github/workflows/type-check.yml) | Runs `mypy src` |
| [.github/workflows/openwiki-update.yml](../.github/workflows/openwiki-update.yml) | Regenerates `/openwiki` docs (informational) |
| [.github/workflows/template-sync.yml](../.github/workflows/template-sync.yml) | Checks template sync status (manual trigger) |

## Navigation by workflow

### "I need to understand the project"
1. Start here: [Quick Start](./quickstart.md)
2. Read: [Specification](./specification.md)
3. Dive in: [Architecture](./architecture.md)
4. Check decisions: [spec/adr/](../spec/adr/)

### "I want to add a new feature"
1. Define requirements in [spec/spec.md](../spec/spec.md)
2. Write a design ADR (see [.claude/standards/decisions.md](../.claude/standards/decisions.md))
3. Create GitHub issues, sequenced in [spec/build-order.md](../spec/build-order.md)
4. Implement & test following [Architecture](./architecture.md) and [Testing Guide](./testing.md)
5. Update [spec/spec.md](../spec/spec.md) if requirements changed
6. Regenerate docs: `openwiki code --update`

### "I need to set up a development environment"
1. Follow [Quick Start - Setup](./quickstart.md#setup-one-time)
2. Run: `make setup`
3. Configure Azure: [Operations - Azure resource provisioning](./operations.md#azure-resource-provisioning)

### "Tests are failing"
1. Run locally: `uv run pytest -v`
2. Check what's being tested: [Testing Guide](./testing.md)
3. Review error messages and stack traces
4. Fix code, re-run: `uv run pytest`

### "I need to deploy or run the CLI in production"
1. Set up Azure: [Operations - Azure resource provisioning](./operations.md#azure-resource-provisioning)
2. Configure environment: [Quick Start - Environment configuration](./quickstart.md#environment-configuration)
3. Run: `transcribe audio.mp3` (or `uv run transcribe audio.mp3`)
4. Monitor: [Operations - Monitoring](./operations.md#monitoring-and-debugging)

### "I need to modify the infrastructure"
1. Read: [infra/README.md](../infra/README.md)
2. Edit: [infra/terraform.tfvars](../infra/terraform.tfvars) (or `.example`)
3. Plan: `terraform plan -var-file=terraform.tfvars`
4. Apply: `terraform apply -var-file=terraform.tfvars`
5. Extract credentials: `terraform output -raw speech_endpoint`

### "I need to sync with the template"
1. Check status: `uvx cruft check`
2. Update: `uvx cruft update`
3. Resolve conflicts (`.rej` files)
4. Test: `uv run pytest && uv run ruff check . && uv run mypy src`
5. Commit: `git add . && git commit -m "chore: update from template"`

## Current progress

**Phase 1 (local files, fast transcription) — ✓ Complete**

| Issue | Title | Status |
|-------|-------|--------|
| #6 | feat: validate CLI arguments and reject missing/unsupported input files | ✓ Done |
| #7 | feat: validate Azure Speech credentials from environment variables | ✓ Done |
| #8 | feat: transcribe a local audio file via Azure fast (synchronous) transcription | ✓ Done |
| #10 | feat: transform fast-transcription result into the output schema and write FILE.json | ✓ Done |
| #11 | feat: orchestrate end-to-end transcription for one or more files with per-file error handling | ✓ Done |

**Phase 2 (blob-staged batch transcription) — Deferred**

| Issue | Title | Status |
|-------|-------|--------|
| #9 | feat: poll Azure batch transcription job until terminal status or timeout | ⏳ Deferred (Phase 2) |

See [spec/build-order.md](../spec/build-order.md) for detailed sequencing.

## Code entry points

**For reading code:**
- Main CLI entrypoint: [src/transcribe/main.py](../src/transcribe/main.py)
- CLI parsing logic: [src/transcribe/cli.py](../src/transcribe/cli.py)
- Credential loading: [src/transcribe/credentials.py](../src/transcribe/credentials.py)
- Transcription (Azure calls): [src/transcribe/transcription.py](../src/transcribe/transcription.py)
- Result transformation: [src/transcribe/transform.py](../src/transcribe/transform.py)
- Exception definitions: [src/transcribe/errors.py](../src/transcribe/errors.py)

**For testing:**
- CLI tests: [tests/test_cli.py](../tests/test_cli.py)
- Credential tests: [tests/test_credentials.py](../tests/test_credentials.py)
- Main tests: [tests/test_main.py](../tests/test_main.py)
- Transcription tests: [tests/test_transcription.py](../tests/test_transcription.py)
- Transform tests: [tests/test_transform.py](../tests/test_transform.py)
- Shared fixtures: [tests/conftest.py](../tests/conftest.py)

**For configuration:**
- Project metadata & tool config: [pyproject.toml](../pyproject.toml)
- Git hooks: [.pre-commit-config.yaml](../.pre-commit-config.yaml)
- Development shortcuts: [Makefile](../Makefile)

## Search tips

| Question | Where to look |
|----------|----------------|
| What are the done criteria for issue #8? | [spec/spec.md](../spec/spec.md) - search "done criteria" |
| How is CredentialError used? | `grep -r CredentialError src/ tests/` |
| Which tests validate file extensions? | [tests/test_cli.py](../tests/test_cli.py) - test functions with "extension" |
| What's the Azure endpoint URL format? | [spec/spec.md](../spec/spec.md) or [src/credentials.py](../src/credentials.py) comments |
| How do I add a new exception type? | [src/errors.py](../src/errors.py) - define class, inherit from AppError |
| What's the pytest configuration? | [pyproject.toml](../pyproject.toml) - search `[tool.pytest]` |

## Useful commands

```bash
# Build/run
make setup                    # One-time: install deps, git hooks
uv sync                       # Install dependencies
uv run python src/main.py FILE.mp3

# Test
uv run pytest                # All tests
uv run pytest -m unit        # Unit tests only
uv run pytest tests/test_cli.py::test_parse_args_returns_paths_for_each_argument

# Lint & format
uv run ruff check .          # Report issues
uv run ruff format .         # Fix formatting
uv run mypy src              # Type check

# Infrastructure
cd infra && terraform plan -var-file=terraform.tfvars
cd infra && terraform apply -var-file=terraform.tfvars
terraform output -raw speech_endpoint

# Documentation
openwiki code --init         # Initial wiki generation
openwiki code --update       # Regenerate wiki after code changes
```

## References

- [Quick Start](./quickstart.md)
- [Architecture & Workflows](./architecture.md)
- [Specification & Requirements](./specification.md)
- [Testing Guide](./testing.md)
- [Operations & Infrastructure](./operations.md)
- [spec/spec.md](../spec/spec.md) — Authoritative functional specification
- [README.md](../README.md) — Project overview and getting started
