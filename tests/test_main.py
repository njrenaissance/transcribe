import csv
from pathlib import Path

import httpx
import pytest
import yaml

from transcribe.main import main

EXIT_CODE_USAGE_ERROR = 2
_ENDPOINT_VAR = "AZURE_SPEECH_ENDPOINT"
_KEY_VAR = "AZURE_SPEECH_KEY"

_VALID_RESULT = {
    "durationMilliseconds": 2500,
    "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}],
}
_CALL_ROW = (
    "123",
    "5551234567",
    "5559876543",
    "incoming",
    "2026-08-29 23:05:17",
    "00:00:35",
    "2026-08-29 23:05:52",
    "pertinent",
    "complete",
    "English",
    None,
    None,
)


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


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n", 2)[1])


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_writes_output_file_and_returns_zero_for_valid_entry(mocker, tmp_path, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    assert exit_code == 0
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.exists()
    frontmatter = _read_frontmatter(output_file)
    assert frontmatter["source_file"] == "audio.mp3"
    assert frontmatter["ref"] == "123"
    assert output_file.read_text(encoding="utf-8").endswith("[0.0-2.5] Hello world")


def _write_manifest(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(["ref", "target", "audio_path"])
        for row in rows:
            writer.writerow(row)


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_writes_output_files_for_manifest_rows_and_returns_zero(mocker, tmp_path, make_call_db):
    audio_a = tmp_path / "a.mp3"
    audio_a.write_bytes(b"fake-audio-bytes")
    audio_b = tmp_path / "b.wav"
    audio_b.write_bytes(b"fake-audio-bytes")
    call_row_b = ("456", "5559876543", *_CALL_ROW[2:])
    call_db = make_call_db([_CALL_ROW, call_row_b])
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [("123", "5551234567", str(audio_a)), ("456", "5559876543", str(audio_b))])
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main(["--manifest", str(manifest), "--call-db", str(call_db)])

    assert exit_code == 0
    assert (tmp_path / "a-transcript.txt").exists()
    assert (tmp_path / "b-transcript.txt").exists()


@pytest.mark.unit
def test_main_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_missing_file(tmp_path, capsys, make_call_db):
    missing = tmp_path / "missing.mp3"
    call_db = make_call_db([_CALL_ROW])

    exit_code = main(["--audiopath", str(missing), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)])

    assert exit_code == 1
    assert "missing.mp3" in capsys.readouterr().err
    output_file = tmp_path / "missing-transcript.txt"
    assert output_file.exists()
    frontmatter = _read_frontmatter(output_file)
    assert frontmatter["source_file"] == "missing.mp3"
    assert "missing.mp3" in frontmatter["error"]


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_unsupported_extension(tmp_path, capsys, make_call_db):
    notes = tmp_path / "notes.txt"
    notes.touch()
    call_db = make_call_db([_CALL_ROW])

    exit_code = main(["--audiopath", str(notes), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)])

    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "unsupported" in stderr.lower()
    assert ".txt" in stderr
    output_file = tmp_path / "notes-transcript.txt"
    assert output_file.exists()
    assert "unsupported" in _read_frontmatter(output_file)["error"].lower()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_isolates_per_entry_failure_and_still_writes_valid_files(mocker, tmp_path, capsys, make_call_db):
    valid = tmp_path / "a.mp3"
    valid.write_bytes(b"fake-audio-bytes")
    missing = tmp_path / "missing.mp3"
    call_row_b = ("456", "5559876543", *_CALL_ROW[2:])
    call_db = make_call_db([_CALL_ROW, call_row_b])
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [("123", "5551234567", str(valid)), ("456", "5559876543", str(missing))])
    _mock_response(mocker, _VALID_RESULT)

    exit_code = main(["--manifest", str(manifest), "--call-db", str(call_db)])

    assert exit_code == 1
    assert (tmp_path / "a-transcript.txt").exists()
    assert "missing.mp3" in capsys.readouterr().err
    assert (tmp_path / "missing-transcript.txt").exists()


@pytest.mark.unit
def test_main_reports_invalid_manifest_without_calling_azure(mocker, tmp_path, capsys, make_call_db):
    missing_manifest = tmp_path / "missing.csv"
    call_db = make_call_db([_CALL_ROW])
    mock_post = mocker.patch("transcribe.transcription.httpx.post")

    exit_code = main(["--manifest", str(missing_manifest), "--call-db", str(call_db)])

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
def test_main_reports_missing_credentials_without_calling_azure(  # noqa: PLR0913, PLR0917
    mocker, tmp_path, capsys, monkeypatch, make_call_db, unset_vars
):
    monkeypatch.setenv(_ENDPOINT_VAR, "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv(_KEY_VAR, "secret-key")
    for var in unset_vars:
        monkeypatch.delenv(var, raising=False)
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    mock_post = mocker.patch("transcribe.transcription.httpx.post")

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    stderr = capsys.readouterr().err
    assert exit_code == 1
    for var in unset_vars:
        assert var in stderr
    mock_post.assert_not_called()
    # Missing credentials abort the whole run before the per-entry loop starts,
    # so there is no single entry to attach an error-echoing output to.
    assert not (tmp_path / "audio-transcript.txt").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_missing_call_db_without_calling_azure(tmp_path, capsys):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    missing_db = tmp_path / "missing-calls.db"

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(missing_db)]
    )

    assert exit_code == 1
    assert str(missing_db) in capsys.readouterr().err
    assert not (tmp_path / "audio-transcript.txt").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_call_record_not_found_without_calling_azure(mocker, tmp_path, capsys, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    mock_post = mocker.patch("transcribe.transcription.httpx.post")

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "999", "--target", "5551234567", "--call-db", str(call_db)]
    )

    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "999" in stderr
    mock_post.assert_not_called()
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.exists()
    frontmatter = _read_frontmatter(output_file)
    assert frontmatter["ref"] is None
    assert "999" in frontmatter["error"]


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_failure_on_non_2xx_response(mocker, tmp_path, capsys, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    _mock_response(mocker, {"error": "unauthorized"}, status_code=401)

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    assert exit_code == 1
    assert "401" in capsys.readouterr().err
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.exists()
    frontmatter = _read_frontmatter(output_file)
    assert "401" in frontmatter["error"]
    assert frontmatter["ref"] == "123"


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_failure_on_network_error(mocker, tmp_path, capsys, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    mocker.patch("transcribe.transcription.httpx.post", side_effect=httpx.ConnectError("connection refused"))

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    assert exit_code == 1
    assert capsys.readouterr().err
    assert (tmp_path / "audio-transcript.txt").exists()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_transcription_timeout(mocker, tmp_path, capsys, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    mocker.patch("transcribe.transcription.httpx.post", side_effect=httpx.ReadTimeout("timed out"))

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    assert exit_code == 1
    assert "audio.mp3" in capsys.readouterr().err
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.exists()
    assert "audio.mp3" in _read_frontmatter(output_file)["error"]


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_reports_empty_transcript(mocker, tmp_path, capsys, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    _mock_response(mocker, {"durationMilliseconds": 0, "phrases": []})

    exit_code = main(
        ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    )

    assert exit_code == 1
    assert capsys.readouterr().err
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.exists()
    assert "no usable transcript" in _read_frontmatter(output_file)["error"]


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_skips_file_with_existing_successful_transcript(mocker, tmp_path, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    args = ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    mock_post = _mock_response(mocker, _VALID_RESULT)
    assert main(args) == 0
    mock_post.reset_mock()

    exit_code = main(args)

    assert exit_code == 0
    mock_post.assert_not_called()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_clobber_reprocesses_file_with_existing_successful_transcript(mocker, tmp_path, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    args = ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    mock_post = _mock_response(mocker, _VALID_RESULT)
    assert main(args) == 0
    mock_post.reset_mock()

    exit_code = main([*args, "--clobber"])

    assert exit_code == 0
    mock_post.assert_called_once()


@pytest.mark.unit
@pytest.mark.usefixtures("valid_credentials_env")
def test_main_retries_file_with_existing_error_output_without_clobber(mocker, tmp_path, make_call_db):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"fake-audio-bytes")
    call_db = make_call_db([_CALL_ROW])
    args = ["--audiopath", str(audio_file), "--ref", "123", "--target", "5551234567", "--call-db", str(call_db)]
    mock_post = _mock_response(mocker, {"durationMilliseconds": 0, "phrases": []})
    assert main(args) == 1
    mock_post.reset_mock()
    mock_post.return_value = httpx.Response(
        200, json=_VALID_RESULT, request=httpx.Request("POST", "https://example.com")
    )

    exit_code = main(args)

    assert exit_code == 0
    mock_post.assert_called_once()
    output_file = tmp_path / "audio-transcript.txt"
    assert output_file.read_text(encoding="utf-8").endswith("[0.0-2.5] Hello world")
