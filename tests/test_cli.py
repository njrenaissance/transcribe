import csv
from pathlib import Path

import pytest

from transcribe.cli import parse_args, read_manifest, validate_file
from transcribe.errors import ManifestError, MissingFileError, UnsupportedFileTypeError

EXIT_CODE_USAGE_ERROR = 2


def _write_manifest(path: Path, urls: list[str], column: str = "url") -> None:
    with path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(["filename", column, "destination"])
        for url in urls:
            writer.writerow([Path(url).name, url, str(Path(url).parent)])


@pytest.mark.unit
def test_parse_args_returns_paths_for_each_argument():
    parsed = parse_args(["a.mp3", "b.wav"])

    assert parsed.paths == [Path("a.mp3"), Path("b.wav")]
    assert parsed.clobber is False


@pytest.mark.unit
def test_parse_args_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
def test_parse_args_reads_paths_from_manifest(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["a.mp3", "b.wav"])

    assert parse_args(["--manifest", str(manifest)]).paths == [Path("a.mp3"), Path("b.wav")]


@pytest.mark.unit
def test_parse_args_combines_positional_files_and_manifest(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["b.wav"])

    assert parse_args(["a.mp3", "--manifest", str(manifest)]).paths == [Path("a.mp3"), Path("b.wav")]


@pytest.mark.unit
def test_parse_args_sets_clobber_when_flag_given():
    assert parse_args(["a.mp3", "--clobber"]).clobber is True


@pytest.mark.unit
def test_read_manifest_returns_url_column_as_paths(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["a.mp3", "b.wav"])

    assert read_manifest(manifest) == [Path("a.mp3"), Path("b.wav")]


@pytest.mark.unit
def test_read_manifest_strips_byte_order_mark_from_header(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_bytes("﻿url\r\na.mp3\r\n".encode())

    assert read_manifest(manifest) == [Path("a.mp3")]


@pytest.mark.unit
def test_read_manifest_raises_when_file_missing(tmp_path):
    missing = tmp_path / "missing.csv"

    with pytest.raises(ManifestError, match="missing.csv"):
        read_manifest(missing)


@pytest.mark.unit
def test_read_manifest_raises_when_url_column_missing(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["a.mp3"], column="path")

    with pytest.raises(ManifestError, match="url"):
        read_manifest(manifest)


@pytest.mark.unit
def test_read_manifest_raises_when_a_row_has_empty_url(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["a.mp3", ""])

    with pytest.raises(ManifestError, match="empty"):
        read_manifest(manifest)


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
