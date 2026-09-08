# Setup, Development & Operations

This page covers local development setup, common workflows, running tests, infrastructure provisioning, and Git hook configuration.

## One-Time Setup

### Prerequisites

- **Python 3.13** (or use `pyenv` or `asdf` to manage versions)
- **uv** (package manager; install from https://docs.astral.sh/uv/)
- **Git** and **pre-commit** (installed via uv)
- **Terraform 1.7.0+** (for Azure infrastructure; optional if using pre-provisioned resources)
- **Azure subscription** (for provisioning Speech resource; optional if using existing resource)

### Bootstrap

```bash
# Clone the repository
git clone https://github.com/<org>/transcribe.git
cd transcribe

# One-time setup: install dependencies and Git hooks
make setup
# Equivalent to:
#   uv sync
#   uv run pre-commit install
#   uv run pre-commit install --hook-type pre-push
```

This installs:
- Python dependencies (httpx, pytest, ruff, mypy, etc.)
- Pre-commit hooks (run on `git commit` and `git push`)
- Local mypy cache and poetry lock state

**Note:** `make setup` is idempotent; safe to run multiple times.

## Development Workflow

### Edit, Test, Commit

```bash
# 1. Make code changes
# (edit src/cli.py, src/main.py, etc.)

# 2. Run local quality gates
make check
# Equivalent to:
#   uv run ruff check .    # Lint
#   uv run mypy src        # Type-check
#   uv run pytest          # Run tests

# 3. Stage and commit
git add -A
git commit -m "feat: add feature X"
# Pre-commit hooks run: ruff check + mypy
# If hooks fail, fix and re-commit

# 4. Before pushing, optionally run full suite again
make check
# (CI will run this regardless; local run catches issues early)

# 5. Push
git push
# Pre-push hook runs: pytest (full test suite)
# If tests fail, fix locally and re-push
```

### Common Commands

```bash
# Install or refresh dependencies
make sync
# Equivalent to: uv sync

# Run tests only
make test
# Equivalent to: uv run pytest

# Lint only
make lint
# Equivalent to: uv run ruff check .

# Format code (fixes ruff issues)
make format
# Equivalent to: uv run ruff format .

# Type-check only
make typecheck
# Equivalent to: uv run mypy src

# Run all quality gates
make check
# Equivalent to: lint + typecheck + test

# Check if template is behind
make template-check
# Equivalent to: uvx cruft check
```

### Running the CLI Locally

**Note:** Currently (as of issues #6–#7), the CLI only validates files; actual transcription is awaiting issue #8.

```bash
# Set environment variables (required by credential validation)
export AZURE_SPEECH_ENDPOINT="https://your-region.cognitiveservices.azure.com"
export AZURE_SPEECH_KEY="your-key"

# Run (currently validates files only, exits 0 if OK)
uv run python src/main.py sample.mp3

# Example: file does not exist
$ uv run python src/main.py missing.mp3
Error: file not found: missing.mp3
# Exit code: 1

# Example: unsupported extension
$ uv run python src/main.py notes.txt
Error: unsupported file extension '.txt': notes.txt
# Exit code: 1

# Example: missing credentials
$ uv run python src/main.py sample.mp3
Error: Missing required environment variable(s): AZURE_SPEECH_ENDPOINT
# Exit code: 1
```

## Testing

### Test Structure

```
tests/
├── conftest.py          # Shared pytest configuration (e.g., log-level setup)
├── test_cli.py          # CLI argument parsing and file validation
├── test_credentials.py  # Azure credential loading
└── test_main.py         # Main entrypoint (integration placeholder)
```

### Test Markers

- `@pytest.mark.unit` — Unit tests (fast, no I/O); run by default
- `@pytest.mark.integration` — Integration tests (may require services); run separately

### Running Tests

```bash
# Run all unit tests (default)
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_cli.py

# Run a specific test
uv run pytest tests/test_cli.py::test_parse_args_returns_paths_for_each_argument

# Run only integration tests
uv run pytest -m integration

# Run with coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run with live output (INFO level logs visible)
uv run pytest -v
# (conftest.py auto-enables INFO logs when -v is used)
```

### Coverage Requirements

**Minimum:** 70% (see `pyproject.toml` `tool.coverage.report.fail_under`)

```bash
# Check coverage
uv run pytest --cov=src --cov-report=html
# Opens htmlcov/index.html in browser

# Identify untested lines
uv run pytest --cov=src --cov-report=term-missing
```

## Linting and Formatting

### Ruff (Linting & Formatting)

```bash
# Check for linting issues
uv run ruff check .

# Check a specific file
uv run ruff check src/cli.py

# Automatically fix issues (applies safe fixes)
uv run ruff check --fix .

# Format code (fixes style issues)
uv run ruff format .

# Dry-run (show what would change)
uv run ruff format --diff .
```

**Configuration:** `pyproject.toml` → `[tool.ruff]`
- Line length: 120
- Target Python version: 3.13
- Enabled rules: E, F, I, UP, B, N, ARG, SIM, ERA, PLR, C901

### mypy (Type Checking)

```bash
# Type-check all source files
uv run mypy src

# Check a specific file
uv run mypy src/cli.py

# Verbose output (show inferred types)
uv run mypy src --verbose
```

**Configuration:** `pyproject.toml` → `[tool.mypy]`
- Disallow untyped definitions: true
- Python version: 3.13
- Files: `src/`

### Pre-commit Hooks

Hooks run automatically on `git commit` (ruff) and `git push` (pytest):

```bash
# Run hooks manually for all files
uv run pre-commit run --all-files

# Run only one hook
uv run pre-commit run ruff --all-files

# Skip hooks on commit (not recommended!)
git commit --no-verify -m "message"
```

## Infrastructure & Azure Provisioning

### Terraform Setup

```bash
# Navigate to infra directory
cd infra

# Create terraform.tfvars with your resource names
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   resource_group_name = "my-rg"
#   location = "eastus"
#   cognitiveservices_account_name = "my-speech"
#   etc.

# Initialize Terraform
terraform init

# Plan the infrastructure
terraform plan -var-file=terraform.tfvars

# Apply (creates resources on Azure)
terraform apply -var-file=terraform.tfvars

# Capture outputs
terraform output speech_endpoint
terraform output -raw speech_primary_key  # (sensitive, do not log)
```

### Environment Variables from Terraform

```bash
# Set environment variables from Terraform outputs
export AZURE_SPEECH_ENDPOINT=$(terraform output -raw speech_endpoint)
export AZURE_SPEECH_KEY=$(terraform output -raw speech_primary_key)

# Verify
echo $AZURE_SPEECH_ENDPOINT
echo $AZURE_SPEECH_KEY
```

### Terraform State

- **State file:** `infra/terraform.tfstate` (local, not remote backend)
- **Backup:** `infra/terraform.tfstate.backup`
- **Git status:** Both files are `.gitignore`'d (never commit state)
- **Persistence:** Keep state file safe on the machine where you run `terraform apply`

See `/spec/adr/0002-terraform-for-azure-infra.md` for the rationale on local state.

### Destroying Resources (Cleanup)

```bash
cd infra
terraform destroy -var-file=terraform.tfvars
# Confirms before destroying
```

## CI/CD Pipelines

### GitHub Actions Workflows

Workflows run on pull requests and can be triggered manually from the Actions tab.

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `format-lint.yml` | PR | Ruff lint + format check |
| `type-check.yml` | PR | mypy static type checking |
| `unit-tests.yml` | PR | pytest (unit tests only) |
| `integration-tests.yml` | PR (if tests exist) | pytest (integration marker) |
| `ci.yml` | PR | Orchestrates above in sequence |
| `template-sync.yml` | Manual | Check if project is behind template |
| `openwiki-update.yml` | Manual or scheduled | Regenerate OpenWiki documentation |

### Local Equivalents

```bash
# Lint + format
uv run ruff check . && uv run ruff format .

# Type-check
uv run mypy src

# Unit tests
uv run pytest -m unit

# Integration tests
uv run pytest -m integration

# All at once
make check
```

## Git Workflow & Hooks

### Commit Hook (Pre-commit)

Runs on every `git commit`:
- **ruff check** (lint)
- **ruff format** (format)
- **mypy src** (type-check)

If any hook fails, the commit is rejected. Fix and re-commit.

### Push Hook (Pre-push)

Runs on every `git push`:
- **pytest** (full test suite)

If tests fail, the push is rejected. Fix locally and re-push.

### Bypassing Hooks (Not Recommended)

```bash
git commit --no-verify -m "message"  # Skips pre-commit hooks
git push --no-verify                 # Skips pre-push hooks
```

## Template Sync

This project is scaffolded from the `basic` cookiecutter template and managed with [cruft](https://cruft.github.io/cruft/).

### Check for Updates

```bash
make template-check
# or
uvx cruft check
```

Exit code 0 = up to date; non-zero = behind.

### Update from Template

If behind, use the `update-from-template` skill:

```bash
# (Agent-friendly; uses the .claude/skills/update-from-template/SKILL.md workflow)
```

Or manually:

```bash
uvx cruft update
# Fetches template and applies delta
# May create *.rej conflict files if local changes conflict with template
# Resolve conflicts, re-run checks, and commit
```

## Credential Management

### Environment Variables

```bash
# Set locally for development
export AZURE_SPEECH_ENDPOINT="https://your-region.cognitiveservices.azure.com"
export AZURE_SPEECH_KEY="your-key"

# Or in a .env file (git-ignored)
echo "AZURE_SPEECH_ENDPOINT=https://..." >> .env
echo "AZURE_SPEECH_KEY=..." >> .env
source .env  # load into shell
```

### Never Commit

- `.env` files
- `terraform.tfvars` (use `terraform.tfvars.example` as template)
- Azure keys
- Any credentials or secrets

These are git-ignored by default.

### Secret Management (Production)

For CI/CD and production:
- Use GitHub Actions Secrets for storing credentials
- Use Azure Key Vault for long-lived credentials
- Rotate keys regularly
- Use short-lived tokens/SAS URLs when possible

## Troubleshooting

### "ModuleNotFoundError: No module named 'cli'"

**Cause:** Tests are running without the src directory on PYTHONPATH.

**Fix:** Check `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
```

If missing, add it. Then re-run.

### "ruff format" or "ruff check" fails

```bash
# Check what's wrong
uv run ruff check . --show-settings

# Auto-fix
uv run ruff check --fix .

# Format
uv run ruff format .
```

### mypy reports "error: Unsupported operand type"

Likely a missing type annotation. Add types to function signatures:

```python
def parse_args(argv: list[str]) -> list[Path]:
    ...

def validate_file(path: Path) -> None:
    ...
```

See `src/` files for examples.

### Tests fail with "credentials.load_azure_credentials() raises CredentialError"

**Cause:** Tests expect credentials to be absent (testing error case).

**Fix:** Ensure environment variables are not set:
```bash
unset AZURE_SPEECH_ENDPOINT
unset AZURE_SPEECH_KEY
```

Or use pytest's `monkeypatch` fixture (already done in `test_credentials.py`).

### "Terraform: Error authenticating via Azure CLI"

**Cause:** Not logged into Azure via `az login`.

**Fix:**
```bash
az login  # opens browser, authenticate, then returns to terminal
terraform init
terraform plan -var-file=terraform.tfvars
```

## Key Files & References

| Path | Purpose |
|------|---------|
| `Makefile` | Common development commands |
| `pyproject.toml` | Dependencies, tool config (pytest, ruff, mypy) |
| `uv.lock` | Locked dependency versions |
| `.pre-commit-config.yaml` | Pre-commit hook definitions |
| `/.github/workflows/` | CI/CD pipeline definitions |
| `/infra/terraform.tfvars.example` | Template for Terraform variables |
| `/README.md` | Top-level setup instructions |

## Next Steps

- **First run:** `make setup` to bootstrap locally
- **Start developing:** Edit source files in `src/`, run `make check` to validate
- **Running the CLI:** Set Azure credentials, then `uv run python src/main.py <audio-file>`
- **Infrastructure:** See `/infra/README.md` for provisioning Azure resources
- **Understanding the code:** See [Architecture Overview](../architecture/overview.md)
