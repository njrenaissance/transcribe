import json

import httpx
import pytest

from transcribe.credentials import AzureCredentials
from transcribe.errors import LanguageNotIdentifiedError, TranscriptionError, TranscriptionTimeoutError
from transcribe.transcription import CANDIDATE_LOCALES, transcribe_file

_CREDENTIALS = AzureCredentials(endpoint="https://example.cognitiveservices.azure.com", key="secret-key")


@pytest.mark.unit
def test_transcribe_file_returns_parsed_result_on_success(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    expected_result = {"durationMilliseconds": 2500, "phrases": [{"text": "Hello world"}]}
    response = httpx.Response(200, json=expected_result, request=httpx.Request("POST", "https://example.com"))
    mock_post = mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    result = transcribe_file(audio_path, _CREDENTIALS)

    assert result == expected_result
    args, kwargs = mock_post.call_args
    assert args[0] == (
        "https://example.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
    )
    assert kwargs["headers"] == {"Ocp-Apim-Subscription-Key": "secret-key"}
    assert kwargs["files"]["audio"][0] == "audio.wav"
    assert kwargs["files"]["audio"][1] == b"fake-audio-bytes"
    assert kwargs["files"]["definition"][2] == "application/json"


@pytest.mark.unit
def test_transcribe_file_sends_every_candidate_locale_for_language_identification(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    response = httpx.Response(
        200, json={"durationMilliseconds": 0, "phrases": []}, request=httpx.Request("POST", "https://example.com")
    )
    mock_post = mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    transcribe_file(audio_path, _CREDENTIALS)

    definition = json.loads(mock_post.call_args.kwargs["files"]["definition"][1])
    assert definition["locales"] == list(CANDIDATE_LOCALES)


@pytest.mark.unit
def test_transcribe_file_disables_profanity_filtering(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    response = httpx.Response(
        200, json={"durationMilliseconds": 0, "phrases": []}, request=httpx.Request("POST", "https://example.com")
    )
    mock_post = mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    transcribe_file(audio_path, _CREDENTIALS)

    definition = json.loads(mock_post.call_args.kwargs["files"]["definition"][1])
    assert definition["profanityFilterMode"] == "None"


@pytest.mark.unit
def test_transcribe_file_requests_diarization_for_up_to_two_speakers(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    response = httpx.Response(
        200, json={"durationMilliseconds": 0, "phrases": []}, request=httpx.Request("POST", "https://example.com")
    )
    mock_post = mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    transcribe_file(audio_path, _CREDENTIALS)

    definition = json.loads(mock_post.call_args.kwargs["files"]["definition"][1])
    assert definition["diarization"] == {"maxSpeakers": 2, "enabled": True}


@pytest.mark.unit
def test_transcribe_file_raises_transcription_error_on_non_2xx_response(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(401, json={"error": "unauthorized"}, request=request)
    mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    with pytest.raises(TranscriptionError) as exc_info:
        transcribe_file(audio_path, _CREDENTIALS)

    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
    assert "401" in str(exc_info.value)


@pytest.mark.unit
def test_transcribe_file_raises_language_not_identified_on_no_language_identified_response(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    request = httpx.Request("POST", "https://example.com")
    body = {
        "code": "UnprocessableEntity",
        "message": "No language was identified.",
        "innerError": {"code": "NoLanguageIdentified", "message": "No language was identified."},
    }
    response = httpx.Response(422, json=body, request=request)
    mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    with pytest.raises(LanguageNotIdentifiedError, match="audio.wav"):
        transcribe_file(audio_path, _CREDENTIALS)


@pytest.mark.unit
def test_transcribe_file_raises_transcription_error_on_other_422_response(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    request = httpx.Request("POST", "https://example.com")
    body = {"code": "UnprocessableEntity", "message": "Something else entirely."}
    response = httpx.Response(422, json=body, request=request)
    mocker.patch("transcribe.transcription.httpx.post", return_value=response)

    with pytest.raises(TranscriptionError):
        transcribe_file(audio_path, _CREDENTIALS)


@pytest.mark.unit
def test_transcribe_file_raises_transcription_error_on_network_error(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    network_error = httpx.ConnectError("connection refused")
    mocker.patch("transcribe.transcription.httpx.post", side_effect=network_error)

    with pytest.raises(TranscriptionError) as exc_info:
        transcribe_file(audio_path, _CREDENTIALS)

    assert exc_info.value.__cause__ is network_error


@pytest.mark.unit
def test_transcribe_file_raises_timeout_error_on_timeout(mocker, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake-audio-bytes")
    timeout_error = httpx.ReadTimeout("timed out")
    mocker.patch("transcribe.transcription.httpx.post", side_effect=timeout_error)

    with pytest.raises(TranscriptionTimeoutError) as exc_info:
        transcribe_file(audio_path, _CREDENTIALS, timeout=5.0)

    assert exc_info.value.__cause__ is timeout_error
    assert "5.0" in str(exc_info.value)
