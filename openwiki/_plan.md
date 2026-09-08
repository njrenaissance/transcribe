# OpenWiki Documentation Plan for `transcribe`

## Project Summary
A Python CLI tool for transcribing local audio files (MP3, WAV) into timestamped text using Azure AI Speech.
Currently implements Phase 1: fast (synchronous) transcription for local files.
Phase 2 (blob-staged batch transcription) is deferred.

## Intended Documentation Pages

### Core (Required)
1. **quickstart.md** - Entry point with project overview, setup, and navigation
   - What the project does (Azure Speech-based audio transcription CLI)
   - Key workflows (local file → validation → Azure fast transcription → JSON output)
   - Setup, build, run, test commands
   - Link to all major sections

2. **architecture/overview.md** - Technical architecture and design
   - Core components: CLI, validation, credentials, error handling
   - Current Phase 1 design (fast transcription)
   - ADR references (fast-vs-batch rationale in ADR-0003)
   - Key dependencies (httpx, pydantic for types)
   - Phase 2 deferral and what will change

3. **workflows/cli-flow.md** - Step-by-step CLI execution flow
   - Input parsing and validation (CLI args, file existence, extension)
   - Credential loading and validation (env vars)
   - Currently: placeholder for Azure fast-transcription call (issue #8, not yet merged)
   - Output transformation and JSON writing (issue #10, not yet merged)
   - End-to-end orchestration (issue #11, not yet merged)
   - Error handling and exit codes (per spec.md criteria)

4. **operations/setup-and-run.md** - Setup, development, and operations
   - One-time setup: `make setup`
   - Development workflow (edit, test, format, commit)
   - Running the CLI (uv run)
   - Git hooks and pre-commit rules
   - Template sync (cruft) process
   - Infrastructure: Terraform provisioning of Azure Speech resource

5. **testing/overview.md** - Testing strategy and guidelines
   - Test structure: unit (CLI validation, credentials) and integration markers
   - Current coverage: CLI parsing, validation, credentials, error messages
   - Missing: fast-transcription integration tests (awaiting issue #8-#10)
   - Running tests locally and in CI
   - Coverage requirements (70% minimum)

6. **domain/spec-and-contracts.md** - Specification, data models, and contracts
   - Input contract: file paths, supported extensions (.mp3, .wav)
   - Credential contract: AZURE_SPEECH_ENDPOINT, AZURE_SPEECH_KEY env vars
   - Output schema: JSON with source_file, language, duration_seconds, segments
   - Done criteria (10 specific scenarios from spec.md)
   - Phase 2 additions (blob storage, SAS, batch polling)

7. **integrations/azure-speech.md** - Azure Speech API and integration details
   - ADR-0001: why Azure Speech (existing agreement, hosted model)
   - ADR-0003: fast vs batch split (fast for local files, batch deferred)
   - Fast transcription endpoint: POST to `.../speechtotext/transcriptions:transcribe`
   - Request format: multipart/form-data with audio + definition (locales)
   - Response: durationMilliseconds, phrases array → map to output schema
   - Error handling: auth, non-2xx, network, timeout (per spec criteria)
   - Current implementation status: not yet in codebase (pending issue #8)

## Source Evidence
- `/README.md` - template-based project structure, wiki policy
- `/CLAUDE.md` - project profile (disabled: config, logging, telemetry, security)
- `/spec/spec.md` - full specification, input/output contracts, done criteria
- `/spec/build-order.md` - issue sequencing (Phase 1: issues 6, 7, 8, 10, 11)
- `/spec/adr/` - ADR-0001 (Azure), ADR-0002 (Terraform), ADR-0003 (fast transcription)
- `/src/` - CLI parsing (cli.py), credentials (credentials.py), errors (errors.py), main entry (main.py)
- `/tests/` - test_cli.py, test_credentials.py, test_main.py (all unit)
- `/infra/` - Terraform for Azure Speech resource
- `/.github/workflows/` - CI pipeline, unit/integration test jobs, OpenWiki update workflow
- `/pyproject.toml` - dependencies (httpx), Python 3.13, linting/formatting rules
- `/Makefile` - developer commands (setup, test, lint, format, typecheck)

## Coverage and Scope
- Focus on Phase 1 (local fast transcription)
- Explain Phase 2 deferral with ADR-0003
- Document current state: validation only (issues 6, 7 done), transcription TBD (issues 8, 10, 11 pending)
- Link to spec and ADRs as source of truth
- Keep pages practical: show where code is, what's missing, where to start

## Open Questions / Notes
- Fast-transcription implementation (issue #8) not yet in codebase → mark as pending in workflows
- Integration tests will require mocked/real Azure calls once #8 merged
- Phase 2 will add blob storage credentials, SAS generation, batch polling
- Current README still references "greet()" from template; note that template structure info is now out of date
