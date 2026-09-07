# ADR-0001: Use Azure AI Speech as the transcription provider

## Status
accepted

## Context
`transcribe` needs to turn local audio files into timestamped text. Two
broad approaches were available: run a pretrained speech-to-text model
locally (e.g. `faster-whisper`), which needs no network access or
credentials, or call a hosted cloud transcription API. The organization
already holds a commercial agreement with Azure, and this project has no
other cross-cutting infrastructure enabled (config, telemetry, and
security-scanning are all off per `CLAUDE.md`'s Profile section), so this
choice is the project's one significant external dependency.

## Decision
Use Azure AI Speech's batch/fast transcription REST API as the sole
transcription backend, authenticated via an endpoint and key supplied
through environment variables (`AZURE_SPEECH_ENDPOINT`, `AZURE_SPEECH_KEY`).

## Consequences
- The CLI is no longer usable offline or in an environment without network
  egress to Azure and valid credentials — every run has an external
  dependency and a per-call latency/cost, unlike a local model.
- Transcription quality, supported languages, and available features (e.g.
  diarization) are governed by Azure's product roadmap and pricing tier
  rather than a model we control or can fine-tune.
- Credential handling (issuing, rotating, and scoping the Speech key)
  becomes an operational concern for this project; the Terraform in
  `/infra` (see ADR-0002) provisions the resource but key distribution to
  runtime environments is still the deployer's responsibility.
- Switching away from Azure later (e.g. to a local model or another cloud
  provider) means replacing the transcription call, its error handling,
  and the credential contract in `spec.md` — a rewrite-scale change, not a
  small edit, which is why this is recorded as an ADR rather than left
  implicit in the spec.
