import csv
from pathlib import Path

import pytest

from transcribe.cli import ManifestEntry, parse_args, read_manifest, validate_file
from transcribe.errors import ManifestError, MissingFileError, UnsupportedFileTypeError

EXIT_CODE_USAGE_ERROR = 2
_DUMMY_CALL_DB = "calls.db"


def _write_manifest(
    path: Path,
    rows: list[tuple[str, str, str]],
    columns: tuple[str, ...] = ("ref", "target", "audio_path"),
) -> None:
    with path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)


@pytest.mark.unit
def test_parse_args_builds_single_entry_from_audiopath_ref_target():
    parsed = parse_args(["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567", "--call-db", _DUMMY_CALL_DB])

    assert parsed.entries == [ManifestEntry(ref="123", target="5551234567", audio_path="a.mp3")]
    assert parsed.clobber is False
    assert parsed.call_db == Path(_DUMMY_CALL_DB)


@pytest.mark.unit
def test_parse_args_exits_with_usage_when_no_arguments_given(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args([])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "usage" in capsys.readouterr().err.lower()


@pytest.mark.unit
def test_parse_args_exits_when_manifest_combined_with_audiopath(tmp_path, capsys):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [("123", "5551234567", "a.mp3")])

    with pytest.raises(SystemExit) as exc_info:
        parse_args(
            [
                "--manifest",
                str(manifest),
                "--audiopath",
                "a.mp3",
                "--ref",
                "123",
                "--target",
                "5551234567",
                "--call-db",
                _DUMMY_CALL_DB,
            ]
        )

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "--manifest" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize(
    "given",
    [
        pytest.param(["--audiopath", "a.mp3"], id="only_audiopath"),
        pytest.param(["--ref", "123"], id="only_ref"),
        pytest.param(["--audiopath", "a.mp3", "--ref", "123"], id="missing_target"),
    ],
)
def test_parse_args_exits_when_only_some_of_audiopath_ref_target_given(capsys, given):
    with pytest.raises(SystemExit) as exc_info:
        parse_args([*given, "--call-db", _DUMMY_CALL_DB])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "--audiopath" in capsys.readouterr().err


@pytest.mark.unit
def test_parse_args_exits_when_call_db_missing(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567"])

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "--call-db" in capsys.readouterr().err


@pytest.mark.unit
def test_parse_args_resolves_call_db_from_env_var(monkeypatch):
    monkeypatch.setenv("CALL_DB_PATH", "env-calls.db")

    parsed = parse_args(["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567"])

    assert parsed.call_db == Path("env-calls.db")


@pytest.mark.unit
def test_parse_args_flag_overrides_call_db_env_var(monkeypatch):
    monkeypatch.setenv("CALL_DB_PATH", "env-calls.db")

    parsed = parse_args(
        ["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567", "--call-db", "flag-calls.db"]
    )

    assert parsed.call_db == Path("flag-calls.db")


@pytest.mark.unit
def test_parse_args_reads_entries_from_manifest(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [("123", "5551234567", "a.mp3"), ("456", "5559876543", "b.wav")])

    parsed = parse_args(["--manifest", str(manifest), "--call-db", _DUMMY_CALL_DB])

    assert parsed.entries == [
        ManifestEntry(ref="123", target="5551234567", audio_path="a.mp3"),
        ManifestEntry(ref="456", target="5559876543", audio_path="b.wav"),
    ]


@pytest.mark.unit
def test_parse_args_sets_clobber_when_flag_given():
    parsed = parse_args(
        ["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567", "--call-db", _DUMMY_CALL_DB, "--clobber"]
    )

    assert parsed.clobber is True


@pytest.mark.unit
def test_parse_args_defaults_destination_to_none():
    parsed = parse_args(["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567", "--call-db", _DUMMY_CALL_DB])

    assert parsed.destination is None


@pytest.mark.unit
def test_parse_args_sets_destination_when_given():
    parsed = parse_args(
        [
            "--audiopath",
            "a.mp3",
            "--ref",
            "123",
            "--target",
            "5551234567",
            "--call-db",
            _DUMMY_CALL_DB,
            "--destination",
            "out",
        ]
    )

    assert parsed.destination == Path("out")


@pytest.mark.unit
def test_parse_args_defaults_timestamp_format():
    parsed = parse_args(["--audiopath", "a.mp3", "--ref", "123", "--target", "5551234567", "--call-db", _DUMMY_CALL_DB])

    assert parsed.timestamp_format == "%H:%M:%S"


@pytest.mark.unit
def test_parse_args_sets_custom_timestamp_format():
    parsed = parse_args(
        [
            "--audiopath",
            "a.mp3",
            "--ref",
            "123",
            "--target",
            "5551234567",
            "--call-db",
            _DUMMY_CALL_DB,
            "--timestamp-format",
            "%M:%S",
        ]
    )

    assert parsed.timestamp_format == "%M:%S"


@pytest.mark.unit
def test_parse_args_exits_when_timestamp_format_is_invalid(capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args(
            [
                "--audiopath",
                "a.mp3",
                "--ref",
                "123",
                "--target",
                "5551234567",
                "--call-db",
                _DUMMY_CALL_DB,
                "--timestamp-format",
                "%Q",
            ]
        )

    assert exc_info.value.code == EXIT_CODE_USAGE_ERROR
    assert "--timestamp-format" in capsys.readouterr().err


@pytest.mark.unit
def test_read_manifest_returns_entries(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [("123", "5551234567", "a.mp3"), ("456", "5559876543", "b.wav")])

    assert read_manifest(manifest) == [
        ManifestEntry(ref="123", target="5551234567", audio_path="a.mp3"),
        ManifestEntry(ref="456", target="5559876543", audio_path="b.wav"),
    ]


@pytest.mark.unit
def test_read_manifest_strips_byte_order_mark_from_header(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_bytes("﻿ref,target,audio_path\r\n123,5551234567,a.mp3\r\n".encode())

    assert read_manifest(manifest) == [ManifestEntry(ref="123", target="5551234567", audio_path="a.mp3")]


@pytest.mark.unit
def test_read_manifest_raises_when_file_missing(tmp_path):
    missing = tmp_path / "missing.csv"

    with pytest.raises(ManifestError, match="missing.csv"):
        read_manifest(missing)


@pytest.mark.unit
@pytest.mark.parametrize("missing_column", ["ref", "target", "audio_path"])
def test_read_manifest_raises_when_a_required_column_missing(tmp_path, missing_column):
    manifest = tmp_path / "manifest.csv"
    columns = tuple(column for column in ("ref", "target", "audio_path") if column != missing_column)
    with manifest.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(columns)
        writer.writerow(["placeholder"] * len(columns))

    with pytest.raises(ManifestError, match=missing_column):
        read_manifest(manifest)


@pytest.mark.unit
@pytest.mark.parametrize("empty_column_index", [0, 1, 2], ids=["ref", "target", "audio_path"])
def test_read_manifest_raises_when_a_row_has_an_empty_value(tmp_path, empty_column_index):
    manifest = tmp_path / "manifest.csv"
    row = ["123", "5551234567", "a.mp3"]
    row[empty_column_index] = ""
    _write_manifest(manifest, [tuple(row)])

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
