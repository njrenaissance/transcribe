import csv
import json
from pathlib import Path

import httpx
import pytest

from transcribe.main import main

EXIT_CODE_USAGE_ERROR = 2
_ENDPOINT_VAR = "AZURE_SPEECH_ENDPOINT"
_KEY_VAR = "AZURE_SPEECH_KEY"

_VALID_RESULT = {
    "durationMilliseconds": 2500,
    "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}],
}


@pytest.fixture(autouse=True)
def _no_dotenv(mocker):
    """Keep tests hermetic regardless of a developer's local `.env` file."""
    mocker.patch("transcribe.main.dotenv.load_dotenv")


@pytest.fixture
def valid_credentials_env(monkeypatch):
    monkeypatch.setenv(_ENDPOINT_VAR, "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv(_KEY_VAR, "secret-key")


def _mock_response(mocker, json_body, status_code=200):
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, json=json_body, request=request)
    return mocker.patch("transcribe.transcription.httpx.post", return_value=response)


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_writes_output_file_and_returns_zero_for_valid_file(mocker, tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main([str(audio_file)])

    assert exit_code == 0
    output_file = tmp_path / "audio.mp3.json"
    assert output_file.exists()
    output = json.loads(output_file.read_text(encoding="utf-8"))
    assert output["source_file"] == "audio.mp3"
    assert output["segments"] == [{"start": 0.0, "end": 2.5, "text": "Hello world"}]


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_writes_output_files_for_all_valid_files_and_returns_zero(mocker, tmp_path):
    audio_a = tmp_path / "a.mp3"
    audio_a.write_bytes(b"fake-audio-bytes")
    audio_b = tmp_path / "b.wav"
    audio_b.write_bytes(b"fake-audio-bytes")
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main([str(audio_a), str(audio_b)])

    assert exit_code == 0
    assert (tmp_path / "a.mp3.json").exists()
    assert (tmp_path / "b.wav.json").exists()


@pytest.mark.unit
def test_main_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_missing_file(tmp_path, capsys):
    missing = tmp_path / "missing.mp3"

    exit_code = main([str(missing)])

    assert exit_code == 1
    assert "missing.mp3" in capsys.readouterr().err
    assert not (tmp_path / "missing.mp3.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_unsupported_extension(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.touch()

    exit_code = main([str(notes)])

    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "unsupported" in stderr.lower()
    assert ".txt" in stderr
    assert not (tmp_path / "notes.txt.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_isolates_per_file_failure_and_still_writes_valid_files(mocker, tmp_path, capsys):
    valid = tmp_path / "a.mp3"
    valid.write_bytes(b"fake-audio-bytes")
    missing = tmp_path / "missing.mp3"
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main([str(valid), str(missing)])

    assert exit_code == 1
    assert (tmp_path / "a.mp3.json").exists()
    assert "missing.mp3" in capsys.readouterr().err
    assert not (tmp_path / "missing.mp3.json").exists()


def _write_manifest(path: Path, urls: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(["url"])
        for url in urls:
            writer.writerow([url])


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_writes_output_files_for_manifest_rows_and_returns_zero(mocker, tmp_path):
    audio_a = tmp_path / "a.mp3"
    audio_a.write_bytes(b"fake-audio-bytes")
    audio_b = tmp_path / "b.wav"
    audio_b.write_bytes(b"fake-audio-bytes")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [str(audio_a), str(audio_b)])
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main(["--manifest", str(manifest)])

    assert exit_code == 0
    assert (tmp_path / "a.mp3.json").exists()
    assert (tmp_path / "b.wav.json").exists()


@pytest.mark.unit
def test_main_reports_invalid_manifest_without_calling_azure(mocker, tmp_path, capsys):
    missing_manifest = tmp_path / "missing.csv"
    mock_post = mocker.patch("transcribe.transcription.httpx.post")

    exit_code = main(["--manifest", str(missing_manifest)])

    assert exit_code == 1
    assert "missing.csv" in capsys.readouterr().err
    mock_post.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "unset_vars",
    [
        pytest.param([_ENDPOINT_VAR], id="endpoint_unset"),
        pytest.param([_KEY_VAR], id="key_unset"),
        pytest.param([_ENDPOINT_VAR, _KEY_VAR], id="both_unset"),
    ],
)
def test_main_reports_missing_credentials_without_calling_azure(mocker, tmp_path, capsys, monkeypatch, unset_vars):
    monkeypatch.setenv(_ENDPOINT_VAR, "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv(_KEY_VAR, "secret-key")
    for var in unset_vars:
        monkeypatch.delenv(var, raising=False)
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    mock_post = mocker.patch("transcribe.transcription.httpx.post")

    exit_code = main([str(audio_file)])

    stderr = capsys.readouterr().err
    assert exit_code == 1
    for var in unset_vars:
        assert var in stderr
    mock_post.assert_not_called()
    assert not (tmp_path / "audio.mp3.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_failure_on_non_2xx_response(mocker, tmp_path, capsys):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    _mock_response(mocker, {"error": "unauthorized"}, status_code=401)

    exit_code = main([str(audio_file)])

    assert exit_code == 1
    assert "401" in capsys.readouterr().err
    assert not (tmp_path / "audio.mp3.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_failure_on_network_error(mocker, tmp_path, capsys):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    mocker.patch("transcribe.transcription.httpx.post", side_effect=httpx.ConnectError("connection refused"))

    exit_code = main([str(audio_file)])

    assert exit_code == 1
    assert capsys.readouterr().err
    assert not (tmp_path / "audio.mp3.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_timeout(mocker, tmp_path, capsys):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    mocker.patch("transcribe.transcription.httpx.post", side_effect=httpx.ReadTimeout("timed out"))

    exit_code = main([str(audio_file)])

    assert exit_code == 1
    assert "audio.mp3" in capsys.readouterr().err
    assert not (tmp_path / "audio.mp3.json").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_empty_transcript(mocker, tmp_path, capsys):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    _mock_response(mocker, {"durationMilliseconds": 0, "phrases": []})

    exit_code = main([str(audio_file)])

    assert exit_code == 1
    assert capsys.readouterr().err
    assert not (tmp_path / "audio.mp3.json").exists()
