import pytest

from main import main

EXIT_CODE_USAGE_ERROR = 2


@pytest.mark.unit
def test_main_returns_zero_for_valid_files(tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    assert main([str(audio_file)]) == 0


@pytest.mark.unit
def test_main_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
def test_main_reports_missing_file(tmp_path, capsys):
    missing = tmp_path / "missing.mp3"

    exit_code = main([str(missing)])

    assert exit_code == 1
    assert "missing.mp3" in capsys.readouterr().err


@pytest.mark.unit
def test_main_reports_unsupported_extension(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.touch()

    exit_code = main([str(notes)])

    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "unsupported" in stderr.lower()
    assert ".txt" in stderr
