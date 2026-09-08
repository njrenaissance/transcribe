# Azure Speech Integration

This page details the Azure AI Speech API used by `transcribe`, the fast (synchronous) transcription endpoint, request/response formats, and error handling. It's the reference for implementing issue #8 (transcription call).

## Overview

**Service:** Azure Cognitive Services — Speech to Text  
**Endpoint type:** Fast (synchronous) transcription — available in Phase 1 (current)  
**API version:** `2025-10-15` (per `/spec/spec.md`)  
**Authentication:** Subscription key header (`Ocp-Apim-Subscription-Key`)

## Design Decisions

| Decision | ADR | Rationale |
|----------|-----|-----------|
| **Use Azure (not local model)** | [ADR-0001](/spec/adr/0001-azure-ai-speech-transcription.md) | Existing Azure agreement; hosted service; no on-premise infra |
| **Fast (sync) for local files; batch deferred** | [ADR-0003](/spec/adr/0003-fast-transcription-for-local-files.md) | Fast is simpler for ~400 small files on disk; batch overhead (blob, SAS, polling) unjustified for current volume |
| **HTTP REST (not SDK)** | [ADR-0003](/spec/adr/0003-fast-transcription-for-local-files.md) | Azure Speech SDK does not cover batch/fast REST endpoints; direct HTTP required |
| **httpx HTTP client** | [ADR-0003](/spec/adr/0003-fast-transcription-for-local-files.md) | Lightweight, async-capable (future), matches Python 3.13 stack |

## Infrastructure Setup

### Provisioning

**Tool:** Terraform (see `/infra/README.md`)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars  # edit with your resource names
terraform init
terraform apply -var-file=terraform.tfvars
```

**Output:** Azure Cognitive Services Speech resource

**Resource details:** See `/spec/adr/0002-terraform-for-azure-infra.md`

### Credentials & Environment

After provisioning, capture the outputs:

```bash
terraform output speech_endpoint      # https://region.cognitiveservices.azure.com
terraform output -raw speech_primary_key  # (sensitive; do not print to logs)
```

Set environment variables:

```bash
export AZURE_SPEECH_ENDPOINT="https://region.cognitiveservices.azure.com"
export AZURE_SPEECH_KEY="key-string"
```

## Fast Transcription Endpoint

### URL Format

```
POST https://{endpoint}/cognitiveservices/v1/speechtotext/transcriptions:transcribe?api-version=2025-10-15
```

### Substitutions

- `{endpoint}` ← `AZURE_SPEECH_ENDPOINT` env var (e.g., `https://eastus.cognitiveservices.azure.com`)
- `api-version` ← `2025-10-15` (or later; check Azure docs for current version)

### Example URL

```
https://eastus.cognitiveservices.azure.com/cognitiveservices/v1/speechtotext/transcriptions:transcribe?api-version=2025-10-15
```

## Request Format

### HTTP Method & Headers

```
POST https://{endpoint}/cognitiveservices/v1/speechtotext/transcriptions:transcribe?api-version=2025-10-15
Content-Type: multipart/form-data; boundary=<boundary>
Ocp-Apim-Subscription-Key: {key}
```

### Body: Multipart Form Data

Two parts:

#### Part 1: Audio File

```
--{boundary}
Content-Disposition: form-data; name="audio"; filename="audio.mp3"
Content-Type: audio/mpeg

{binary audio data}
```

- **Part name:** `"audio"` (required)
- **Filename:** Original filename (e.g., `"audio.mp3"`)
- **Content-Type:** Matches file type
  - `.mp3` → `audio/mpeg`
  - `.wav` → `audio/wav`
- **Body:** Raw file bytes

#### Part 2: Transcription Definition

```
--{boundary}
Content-Disposition: form-data; name="definition"
Content-Type: application/json

{"locales": ["en-US"]}
--{boundary}--
```

- **Part name:** `"definition"` (required)
- **Content-Type:** `application/json`
- **Body:** JSON object with:
  - `"locales"`: array of BCP-47 locale codes (e.g., `["en-US"]`)
  - Other optional fields per Azure docs (e.g., `"profanityFilterMode"`, `"outputFormat"`)

### Example Request (using httpx)

```python
import httpx
from pathlib import Path

audio_path = Path("audio.mp3")
endpoint = "https://eastus.cognitiveservices.azure.com"
key = "key-string"

url = f"{endpoint}/cognitiveservices/v1/speechtotext/transcriptions:transcribe?api-version=2025-10-15"

with open(audio_path, "rb") as f:
    audio_bytes = f.read()

files = {
    "audio": (audio_path.name, audio_bytes, "audio/mpeg"),
    "definition": (None, '{"locales": ["en-US"]}', "application/json"),
}

headers = {
    "Ocp-Apim-Subscription-Key": key,
}

response = httpx.post(url, files=files, headers=headers, timeout=30.0)
```

## Response Format

### Status Code

- **2xx (Success):** Transcription succeeded; response body contains result
- **401 Unauthorized:** Invalid subscription key
- **4xx (Client error):** Malformed request, unsupported audio format, etc.
- **5xx (Server error):** Azure service error

### Success Response (2xx)

```json
{
  "durationMilliseconds": 12340,
  "phrases": [
    {
      "offsetMilliseconds": 0,
      "durationMilliseconds": 2500,
      "text": "Hello world",
      "locale": "en-US",
      "confidence": 0.95
    },
    {
      "offsetMilliseconds": 2500,
      "durationMilliseconds": 2500,
      "text": "This is a test",
      "locale": "en-US",
      "confidence": 0.92
    }
  ]
}
```

**Fields:**
- `durationMilliseconds` — Total audio duration in milliseconds
- `phrases` — Array of recognized phrases
  - `offsetMilliseconds` — Start of phrase relative to audio start
  - `durationMilliseconds` — Duration of phrase
  - `text` — Recognized text
  - `locale` — BCP-47 locale code (e.g., `"en-US"`)
  - `confidence` — Confidence score (0.0–1.0, optional)

### Error Response (4xx, 5xx)

Example 401:
```json
{
  "error": {
    "code": "401",
    "message": "Invalid subscription key or wrong API endpoint."
  }
}
```

Example 4xx (unsupported format):
```json
{
  "error": {
    "code": "BadRequest",
    "message": "audio format not supported"
  }
}
```

Parse the error and include details in the raised `TranscriptionError`.

## Response → Output Schema Mapping

Transform Azure's response into the spec's output JSON format (see [Specification & Contracts](../domain/spec-and-contracts.md)).

```python
def transform_azure_result_to_schema(azure_result, input_path: Path) -> dict:
    """Map Azure fast-transcription result to output schema."""
    return {
        "source_file": input_path.name,
        "language": azure_result["phrases"][0]["locale"] if azure_result["phrases"] else "unknown",
        "duration_seconds": azure_result["durationMilliseconds"] / 1000,
        "segments": [
            {
                "start": phrase["offsetMilliseconds"] / 1000,
                "end": (phrase["offsetMilliseconds"] + phrase["durationMilliseconds"]) / 1000,
                "text": phrase["text"],
            }
            for phrase in azure_result["phrases"]
        ],
    }
```

**Key transformations:**
- `source_file` ← input file's base name
- `language` ← first phrase's locale (or default if no phrases)
- `duration_seconds` ← `durationMilliseconds / 1000`
- `segments` ← flatten Azure's `phrases` array into our `segments` format
- Each segment: `start` and `end` in seconds (Azure times in milliseconds)

## Error Handling

### Timeout

**Issue #9 (polling) is deferred to Phase 2. For Phase 1 fast transcription:**

Configure a request timeout (e.g., 30 seconds). If the Azure request exceeds this timeout:

```python
try:
    response = httpx.post(url, files=files, headers=headers, timeout=30.0)
except httpx.TimeoutException as e:
    raise TranscriptionTimeoutError(audio_path, 30.0)
```

**Spec criterion 9:** "Request exceeds a configured request timeout" → exit code 1, error message naming timeout duration.

### Non-2xx Response

If Azure returns 4xx or 5xx:

```python
try:
    response = httpx.post(url, files=files, headers=headers, timeout=30.0)
    response.raise_for_status()  # raises httpx.HTTPStatusError on non-2xx
except httpx.HTTPStatusError as e:
    reason = f"{e.response.status_code} {e.response.reason_phrase}"
    raise TranscriptionError(audio_path, reason)
except httpx.RequestError as e:
    raise TranscriptionError(audio_path, str(e))
```

**Spec criterion 8:** "Fast-transcription call fails (auth, non-2xx, network error)" → exit code 1, error message.

### Empty Phrases

If Azure returns 2xx but `phrases` is empty (e.g., silent audio):

```python
if not azure_result.get("phrases"):
    raise TranscriptionError(audio_path, "no phrases in result")
```

**Spec criterion 10:** "Call succeeds but returns no usable transcript" → exit code 1, error message.

## Cost Considerations

### Fast Transcription Pricing

- **Charge:** Per audio hour (pricing tier dependent)
- **Example rates:** ~2–3× batch transcription per hour (trade-off for synchronous results and no blob storage)
- **Fast cap:** < 5 hours, < 500 MB per single request

### Phase 2 Batch Considerations

When Phase 2 is built, batch transcription will be cheaper per audio hour but requires:
- Azure Blob Storage account and upload
- SAS token generation and lifecycle
- Polling loop and network overhead
- Download from results blob

For the current ~400 small files workload, fast transcription is cost-justified. Revisit if volume grows.

See [ADR-0003](../spec/adr/0003-fast-transcription-for-local-files.md) for full rationale.

## Testing

### Unit Tests

**Current:** No unit tests for Azure calls (awaiting issue #8 implementation).

**Planned for issue #8:**
- Mock httpx to test request construction (URL, headers, multipart body)
- Mock Azure response to test result transformation
- Mock timeout and error conditions to test exception handling

### Integration Tests

**Current:** No integration tests (awaiting issue #8 implementation).

**Planned for issue #8 and #11:**
- Optional: use a real Azure account and test credential
- Or: mock entire Azure endpoint with a local server
- Verify end-to-end: file → request → Azure response → JSON output file

## Azure Documentation

- **Speech to Text API:** https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text
- **Fast transcription endpoint:** Search for "fast transcription" or "synchronous" in Azure Speech docs
- **Batch transcription endpoint:** Deferred to Phase 2; see `/spec/spec.md` "Phase 2" section

## Key Files

| Path | Purpose |
|------|---------|
| `/spec/spec.md` | Specification: input, output, done criteria, Phase 2 plan |
| `/spec/adr/0001-azure-ai-speech-transcription.md` | Why Azure (vs. local model) |
| `/spec/adr/0003-fast-transcription-for-local-files.md` | Fast vs. batch split, two-mode design |
| `/infra/main.tf` | Terraform provisioning |
| `/infra/README.md` | Infrastructure setup guide |
| `/src/credentials.py` | Credential loading from env |
| (TODO) | Implementation of issue #8 — transcription call |

## Next Steps for Implementation

1. **Read the spec:** `/spec/spec.md` (esp. "Inputs / Outputs" and "Result → output-schema mapping")
2. **Review Azure docs:** Fast transcription endpoint and multipart request format
3. **Plan the request:** Build the URL, headers, and multipart body in Python
4. **Test the request:** Mock Azure response; verify request construction and error handling
5. **Implement response transformation:** Map Azure result to output schema
6. **Implement output file writing:** Write JSON to sibling file (issue #10)
7. **Implement orchestration:** Loop over multiple files with error handling (issue #11)
