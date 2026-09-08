# Operations & Infrastructure

## Azure resource provisioning

**transcribe** requires Azure AI Speech credentials. These are provisioned via Terraform under `/infra`.

### Prerequisites

- **Terraform:** >= 1.7.0 (see [install](https://developer.hashicorp.com/terraform/install))
- **Azure CLI:** Installed and authenticated (`az login`)
- **Permissions:** Rights to create resource groups and Cognitive Services accounts in your Azure subscription

### Setup (one-time)

1. **Copy the example variables:**
   ```bash
   cd infra
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **Edit terraform.tfvars** with your values:
   ```hcl
   resource_group_name = "my-transcribe-rg"
   location             = "eastus"  # or your preferred region
   account_name         = "my-speech-account"
   sku_name             = "S0"      # Standard tier
   ```

3. **Initialize Terraform:**
   ```bash
   terraform init
   ```

4. **Review the plan:**
   ```bash
   terraform plan -var-file=terraform.tfvars
   ```

5. **Apply:**
   ```bash
   terraform apply -var-file=terraform.tfvars
   ```

   Terraform creates:
   - Azure Resource Group
   - Cognitive Services Speech resource
   - Outputs the endpoint and key

### Extract credentials

After `terraform apply`, extract the credentials:

```bash
# Endpoint (non-sensitive, can be echoed)
terraform output -raw speech_endpoint
# Example output: https://eastus.cognitiveservices.azure.com/

# Key (sensitive, do not log/print)
terraform output -raw speech_primary_key
```

### Set environment variables

Before running `transcribe`, export the credentials:

```bash
export AZURE_SPEECH_ENDPOINT="$(terraform output -raw speech_endpoint)"
export AZURE_SPEECH_KEY="$(terraform output -raw speech_primary_key)"
```

Or add to `.env` (do not commit):
```bash
# .env (git-ignored)
export AZURE_SPEECH_ENDPOINT=https://eastus.cognitiveservices.azure.com/
export AZURE_SPEECH_KEY=your-key-here
```

Then source it before running:
```bash
source .env
uv run python src/main.py audio.mp3
```

### State management

- **State file:** `terraform.tfstate` (local, not remote)
- **Location:** `/infra/terraform.tfstate*` (git-ignored, never commit)
- **Backups:** Keep safe on the machine that runs `terraform apply`; it's the authoritative record

Rationale: See [ADR-0002](../spec/adr/0002-terraform-for-azure-infra.md#consequences) for why local state is used (not remote backend).

### Update or destroy resources

**Update** (e.g., change SKU or location):
```bash
# Edit terraform.tfvars
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

**Destroy** (remove all resources):
```bash
terraform destroy -var-file=terraform.tfvars
```

Credentials will be revoked; the CLI will fail with auth errors until new resources are provisioned.

### Cost notes

- **SKU:** Default is `S0` (Standard tier)
  - ~$4 per 1,000 fast-transcription requests
  - Fast transcription charged per audio minute (see [Azure pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/))
- **Estimate for current workload:** ~400 files, small audio → expect <$20/month (rough estimate)
- **Optimize:** Monitor usage in Azure Portal; consider lower SKUs for development

## Local development setup

### One-time setup

```bash
make setup
# Installs dependencies via uv, pre-commit hooks
```

Or manually:
```bash
uv sync                              # Install dependencies
uv run pre-commit install            # Install commit hook
uv run pre-commit install --hook-type pre-push  # Install push hook
```

### Pre-commit hooks

Configured in `.pre-commit-config.yaml`:

| Hook | Runs on | Commands |
|------|---------|----------|
| format check | `git commit` | `ruff format --check` |
| lint | `git commit` | `ruff check` |
| type-check | `git commit` | `mypy src` |
| pytest | `git push` | `pytest` |

**Bypass hooks (not recommended):**
```bash
git commit --no-verify        # Skip pre-commit hooks
git push --no-verify          # Skip pre-push hook (pytest)
```

These are safety gates; CI will catch problems regardless.

### Running checks manually

```bash
# Format (modifies files in-place)
uv run ruff format .

# Lint (reports issues)
uv run ruff check .

# Type-check (reports type errors)
uv run mypy src

# Tests (runs all markers)
uv run pytest

# All checks (same as pre-commit)
uv run pre-commit run --all-files
```

## CI/CD pipeline

GitHub Actions workflows (`.github/workflows/`) run on every PR and push to `main`:

| Workflow | Runs | Command | Status |
|----------|------|---------|--------|
| format-lint.yml | PR + push | `ruff format --check` + `ruff check` | ✓ must pass to merge |
| type-check.yml | PR + push | `mypy src` | ✓ must pass to merge |
| unit-tests.yml | PR + push | `pytest -m unit` | ✓ must pass to merge |
| integration-tests.yml | PR + push | `pytest -m integration` | ⏳ deferred (no tests yet) |
| openwiki-update.yml | PR + push | Regenerates `/openwiki` docs | 🔔 informational |
| template-sync.yml | Manual trigger | `cruft check` | 🔔 informational |

### Viewing CI results

- Open the PR on GitHub
- Look for the status checks at the bottom of the PR description
- Click "Details" on any failing check to see logs

### Re-running CI

If CI fails, fix the issue locally and push again:
```bash
git add .
git commit -m "fix: resolve lint/type/test failures"
git push
```

GitHub will automatically re-run all checks.

## Troubleshooting

### Credentials not found

**Error:**
```
Error: Missing required environment variable(s): AZURE_SPEECH_ENDPOINT, AZURE_SPEECH_KEY
```

**Solution:**
```bash
# Check if variables are set
echo $AZURE_SPEECH_ENDPOINT
echo $AZURE_SPEECH_KEY

# Export them
export AZURE_SPEECH_ENDPOINT="$(terraform output -raw speech_endpoint)"
export AZURE_SPEECH_KEY="$(terraform output -raw speech_primary_key)"

# Verify
echo $AZURE_SPEECH_ENDPOINT
```

### File validation errors

**Error:**
```
Error: file not found: audio.mp3
```

**Solution:**
```bash
# Check file exists
ls -la audio.mp3

# Use absolute path if needed
transcribe /absolute/path/to/audio.mp3
```

**Error:**
```
Error: unsupported file extension '.m4a': audio.m4a
```

**Solution:**
Only `.mp3` and `.wav` are supported in Phase 1. Convert the file:
```bash
# Using ffmpeg
ffmpeg -i audio.m4a -codec:a libmp3lame -q:a 4 audio.mp3
transcribe audio.mp3
```

### Azure auth failures (Phase 1 completion)

When issue #8 adds transcription, these errors may occur:

**Error:**
```
Error: fast-transcription request failed for audio.mp3: 401 Unauthorized
```

**Solution:**
- Check credentials are correct: `terraform output -raw speech_primary_key`
- Check endpoint is correct: `terraform output -raw speech_endpoint`
- Check resource hasn't been deleted: `az cognitiveservices account list --output table`

**Error:**
```
Error: fast-transcription request for audio.mp3 timed out after 30s
```

**Solution:**
- File may be too large for fast endpoint (cap ~500 MB, ~5 hours)
- Network may be slow; try again or increase timeout (if configurable)
- Use Phase 2 batch mode for large files (not yet implemented)

### Template sync

If the project drifts from the template:

1. **Check status:**
   ```bash
   uvx cruft check
   ```

2. **Update locally:**
   ```bash
   uvx cruft update
   ```

   (Prompts to keep/overwrite conflicting files.)

3. **Resolve conflicts:**
   - Look for `.rej` files (rejected changes)
   - Manually merge or keep your version
   - Delete `.rej` files

4. **Test:**
   ```bash
   uv run pytest
   uv run ruff check .
   uv run mypy src
   ```

5. **Commit:**
   ```bash
   git add .
   git commit -m "chore: update from template"
   git push
   ```

See [README.md - Staying in sync](../README.md#staying-in-sync-with-the-template) for more details.

## Documentation updates

The `/openwiki` documentation is auto-generated via OpenWiki. Do not hand-edit it; instead:

1. Make code/design changes
2. Regenerate docs:
   ```bash
   openwiki code --update
   ```
3. Commit alongside the code change:
   ```bash
   git add .
   git commit -m "feat: add transcription logic (docs updated)"
   git push
   ```

The `openwiki-update.yml` workflow also regenerates on every push (informational, not a gate).

## Monitoring and debugging

### Logs

Currently, the CLI only prints errors to stderr. Future phases may add:
- Structured logging (see `.claude/standards/logging.md`)
- Debug flags (`--verbose`, `--debug`)
- Telemetry/tracing (deferred)

### Debugging a failed transcription (when Phase 1 complete)

```bash
# Enable Python debugging
python -m pdb src/main.py audio.mp3

# Or add print statements
import sys
print(f"DEBUG: credentials={credentials}", file=sys.stderr)
```

### Azure resource monitoring

Check usage and costs in Azure Portal:
1. Go to your resource group
2. Click the Speech resource
3. "Metrics" tab shows API requests, errors
4. "Cost Management" shows usage-based costs

## Operational runbook

### Daily operations

1. **Run transcriptions:**
   ```bash
   uv run python src/main.py *.mp3
   ```

2. **Check for errors:**
   - Review stderr output for validation/credential/transcription errors
   - Each error is printed with filename
   - No partial files created on error

3. **Verify outputs:**
   ```bash
   ls -la *.json
   cat audio.mp3.json | jq .
   ```

### Monthly operations

1. **Check Azure costs:**
   - Portal → Resource group → Cost Management
   - Compare against budget

2. **Update dependencies:**
   ```bash
   uvx cruft check
   uvx cruft update  # if behind template
   ```

3. **Rotate credentials** (if required by security policy):
   ```bash
   # Generate new key in Azure Portal
   export AZURE_SPEECH_KEY="new-key-here"
   uv run python src/main.py test-audio.mp3
   # Verify it works, then update Terraform/environment
   ```

## References

- [infra/README.md](../infra/README.md): Terraform usage
- [spec/adr/0002-terraform-for-azure-infra.md](../spec/adr/0002-terraform-for-azure-infra.md): Why Terraform + local state
- [README.md - Setup](../README.md#setup): General setup instructions
- [Architecture & Workflows](./architecture.md): System design
