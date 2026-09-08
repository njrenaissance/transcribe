# ADR-0003: Use fast (synchronous) transcription for local files; defer blob-staged batch

## Status
accepted

## Context
ADR-0001 committed `transcribe` to Azure AI Speech's "batch/fast transcription
REST API" without fixing *which* of the two endpoints the CLI uses. `spec.md`
originally described only the **batch** (asynchronous) pipeline: submit a job,
poll to a terminal status, list result files, download the transcript. During
implementation of issue #8 we hit a hard constraint: Azure's batch submit
endpoint (`.../transcriptions:submit`) does **not** accept a local file — its
request body requires `contentUrls`/`contentContainerUrl` pointing at audio
already in Azure Blob Storage. The only endpoint that accepts a local file
directly is **fast transcription** (`.../transcriptions:transcribe`), which the
original spec explicitly excluded.

The actual near-term workload clarified the tradeoff: ~400 files that already
exist on local disk, small in total audio length, needed quickly. At that
volume the per-audio-hour price difference between fast (~2–3× batch) is
negligible, while batch would force blob-storage infrastructure (a storage
account, SAS lifecycle, upload step) and an async poll/download pipeline — all
disproportionate for transcribing small local files fast.

## Decision
Adopt a **two-mode** design, built in priority order:

1. **Local files → fast (synchronous) transcription (primary, current).** Send
   the file directly to `.../speechtotext/transcriptions:transcribe` as
   `multipart/form-data`; the transcript is returned inline. No blob storage, no
   polling, no separate download.
2. **Blob-staged audio → batch (asynchronous) transcription (deferred, Phase
   2).** Retained in `spec.md` for larger/bulk audio; not built yet.

Azure's REST endpoints are called directly over HTTP (the Speech SDK does not
cover batch/fast REST), using **`httpx`** as the HTTP client — the project's
first runtime dependency, shared by any later batch-mode REST calls. This is the
"adopt a dependency for a subsystem" case that `.claude/standards/decisions.md`
flags as ADR-worthy.

## Consequences
- The local/fast path is dramatically simpler than the original batch pipeline:
  no `AzureBlob` staging, no SAS, no `/infra` storage account, and no
  poll/terminal-status/download logic. This retires the need for issue #9
  (polling) and reshapes issues #8 and #10 for the synchronous flow (see
  `spec/build-order.md`).
- Fast transcription is capped per call (currently < 5 h / < 500 MB per file).
  Fine for the current small-file workload, but the CLI is not suitable for
  very long single recordings on this path — those are a reason to build the
  deferred batch mode.
- Cost per audio hour is higher than batch, accepted because total audio volume
  is small; revisit if volume grows enough that the batch rate would materially
  win even after blob-storage overhead.
- `httpx` enters `pyproject.toml` as a runtime dependency; CI/pre-commit gates
  already cover it via the normal lint/type/test path.
- Phase 2 (blob-staged batch) remains a real requirement, deferred not dropped.
  Building it will add storage credentials and an `azurerm_storage_account` to
  `/infra` (extending ADR-0002), and reintroduce the batch submit/poll/download
  issues. This ADR does not supersede ADR-0001; it refines the endpoint choice
  ADR-0001 left open.
