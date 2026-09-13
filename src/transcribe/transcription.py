"""Azure fast (synchronous) transcription for local audio files, with per-utterance language identification."""

import json
from pathlib import Path
from typing import Any

import httpx

from .credentials import AzureCredentials
from .errors import (
    AppError,
    LanguageNotIdentifiedError,
    MultipleLanguagesIdentifiedError,
    TranscriptionError,
    TranscriptionTimeoutError,
)

_API_VERSION = "2025-10-15"
_DEFAULT_TIMEOUT_SECONDS = 60.0
# Candidate locales for Azure's per-utterance language identification (issue #21):
# passing more than one locale here makes the fast-transcription endpoint pick the
# best-matching candidate per phrase (reported back as that phrase's `locale`)
# instead of forcing every phrase into a single fixed locale.
CANDIDATE_LOCALES = ("en-US", "es-US")
# Azure defaults to masking profanity with asterisks. These are legal-discovery
# transcripts, not consumer-facing text — a masked word is lost evidence, not a
# feature, so recognition results pass through unfiltered.
_PROFANITY_FILTER_MODE = "None"
# Every call in the live-fire manifest is a two-party phone call (target +
# associate); diarization tags each phrase with which of the (at most) two
# speakers said it.
_MAX_SPEAKERS = 2
_NO_LANGUAGE_IDENTIFIED_CODE = "NoLanguageIdentified"
_MULTIPLE_LANGUAGES_IDENTIFIED_CODE = "MultipleLanguagesIdentified"
# Errors Azure's language identification (see CANDIDATE_LOCALES) can return as
# a 422 instead of a successful result, mapped to the domain error each means.
_LANGUAGE_IDENTIFICATION_ERRORS = {
    _NO_LANGUAGE_IDENTIFIED_CODE: LanguageNotIdentifiedError,
    _MULTIPLE_LANGUAGES_IDENTIFIED_CODE: MultipleLanguagesIdentifiedError,
}
_UNPROCESSABLE_ENTITY_STATUS = 422
_AUDIO_CONTENT_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
_DEFAULT_AUDIO_CONTENT_TYPE = "application/octet-stream"


def _language_identification_error(response: httpx.Response) -> type[AppError] | None:
    """The domain error class for `response`, if it's a known language-identification 422.

    Confirmed live (issue #21): on very short/low-signal audio, or on audio
    with no single dominant language among `CANDIDATE_LOCALES`, language
    identification can fail outright with a 422 rather than the request
    succeeding with no (or ambiguous) usable phrases.
    """
    if response.status_code != _UNPROCESSABLE_ENTITY_STATUS:
        return None
    try:
        body = response.json()
    except json.JSONDecodeError:
        return None
    code = body.get("innerError", {}).get("code")
    return _LANGUAGE_IDENTIFICATION_ERRORS.get(code)


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
        LanguageNotIdentifiedError: if Azure can't identify a locale among
            `CANDIDATE_LOCALES` for the audio (its 422 `NoLanguageIdentified`
            response).
        MultipleLanguagesIdentifiedError: if Azure identifies more than one
            language with no single dominant one (its 422
            `MultipleLanguagesIdentified` response).
        TranscriptionError: on an authentication failure, any other non-2xx
            response, or a network error.
        TranscriptionTimeoutError: if the request exceeds `timeout`.
    """
    url = f"{credentials.endpoint}/speechtotext/transcriptions:transcribe?api-version={_API_VERSION}"
    headers = {"Ocp-Apim-Subscription-Key": credentials.key}
    audio_content_type = _AUDIO_CONTENT_TYPES.get(path.suffix.lower(), _DEFAULT_AUDIO_CONTENT_TYPE)
    definition = json.dumps(
        {
            "locales": list(CANDIDATE_LOCALES),
            "profanityFilterMode": _PROFANITY_FILTER_MODE,
            "diarization": {"maxSpeakers": _MAX_SPEAKERS, "enabled": True},
        }
    ).encode("utf-8")
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
        language_error = _language_identification_error(err.response)
        if language_error is not None:
            raise language_error(path) from err
        reason = f"HTTP {err.response.status_code} {err.response.reason_phrase}"
        raise TranscriptionError(path, reason) from err
    except httpx.HTTPError as err:
        raise TranscriptionError(path, str(err)) from err

    result: dict[str, Any] = response.json()
    return result
