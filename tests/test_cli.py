from pathlib import Path

import pytest

from transcribe.cli import parse_args, validate_file
from transcribe.errors import MissingFileError, UnsupportedFileTypeError

EXIT_CODE_USAGE_ERROR = 2


@pytest.mark.unit
def test_parse_args_returns_paths_for_each_argument():
    assert parse_args(["a.mp3", "b.wav"]) == [Path("a.mp3"), Path("b.wav")]


@pytest.mark.unit
def test_parse_args_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
@pytest.mark.parametrize("extension", [".mp3", ".wav", ".MP3", ".WAV"], ids=str)
def test_validate_file_accepts_supported_extensions(tmp_path, extension):
    audio_file = tmp_path / f"audio{extension}"
    audio_file.touch()

    validate_file(audio_file)


@pytest.mark.unit
def test_validate_file_raises_when_file_missing(tmp_path):
    missing = tmp_path / "missing.mp3"

    with pytest.raises(MissingFileError, match="missing.mp3"):
        validate_file(missing)


@pytest.mark.unit
def test_validate_file_raises_when_extension_unsupported(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.touch()

    with pytest.raises(UnsupportedFileTypeError, match="unsupported"):
        validate_file(notes)
