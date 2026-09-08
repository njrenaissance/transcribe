"""Azure fast (synchronous) transcription for local audio files."""

import json
from pathlib import Path
from typing import Any

import httpx

from credentials import AzureCredentials
from errors import TranscriptionError, TranscriptionTimeoutError

_API_VERSION = "2025-10-15"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_LOCALE = "en-US"
_AUDIO_CONTENT_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
_DEFAULT_AUDIO_CONTENT_TYPE = "application/octet-stream"


def transcribe_file(
    path: Path,
    credentials: AzureCredentials,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Send one local audio file to Azure's fast-transcription endpoint.

    Args:
        path: an already-validated local audio file.
        credentials: already-validated Azure Speech endpoint/key.
        timeout: request timeout in seconds.

    Returns:
        The parsed fast-transcription result JSON (`durationMilliseconds`,
        `phrases`, etc.).

    Raises:
        TranscriptionError: on an authentication failure, any other non-2xx
            response, or a network error.
        TranscriptionTimeoutError: if the request exceeds `timeout`.
    """
    url = f"{credentials.endpoint}/speechtotext/transcriptions:transcribe?api-version={_API_VERSION}"
    headers = {"Ocp-Apim-Subscription-Key": credentials.key}
    audio_content_type = _AUDIO_CONTENT_TYPES.get(path.suffix.lower(), _DEFAULT_AUDIO_CONTENT_TYPE)
    definition = json.dumps({"locales": [_DEFAULT_LOCALE]}).encode("utf-8")
    files = {
        "audio": (path.name, path.read_bytes(), audio_content_type),
        "definition": (None, definition, "application/json"),
    }

    try:
        response = httpx.post(url, headers=headers, files=files, timeout=timeout)
        response.raise_for_status()
    except httpx.TimeoutException as err:
        raise TranscriptionTimeoutError(path, timeout) from err
    except httpx.HTTPStatusError as err:
        reason = f"HTTP {err.response.status_code} {err.response.reason_phrase}"
        raise TranscriptionError(path, reason) from err
    except httpx.HTTPError as err:
        raise TranscriptionError(path, str(err)) from err

    result: dict[str, Any] = response.json()
    return result
