from pathlib import Path

import pytest
import yaml

from transcribe.call_lookup import CallRecord
from transcribe.errors import EmptyTranscriptionResultError, MissingFileError, OutputWriteError
from transcribe.transform import (
    ErrorOutput,
    build_error_output,
    has_existing_transcript,
    output_path,
    transform_result,
    validate_timestamp_format,
    write_transcript_txt,
)

_VALID_RESULT = {
    "durationMilliseconds": 2500,
    "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}],
}

_REF = "123"
_TARGET = "5551234567"

_CALL_RECORD = CallRecord(
    ref=_REF,
    target=_TARGET,
    associate="5559876543",
    direction="incoming",
    call_start="2026-08-29 23:05:17",
    duration="00:00:35",
    end_time="2026-08-29 23:05:52",
    classification="pertinent",
    call_progress="complete",
    language="English",
    monitor=None,
    text_message=None,
)

_FRONTMATTER_KEY_ORDER = [
    "source_file",
    "ref",
    "target",
    "associate",
    "direction",
    "call_start",
    "duration",
    "end_time",
    "classification",
    "call_progress",
    "language",
    "monitor",
    "text_message",
    "audio_duration",
    "detected_locales",
]


@pytest.mark.unit
def test_transform_result_builds_frontmatter_from_call_record(tmp_path):
    source_path = tmp_path / "audio.mp3"

    output = transform_result(_VALID_RESULT, source_path, _CALL_RECORD)

    assert output.frontmatter == {
        "source_file": "audio.mp3",
        "ref": "123",
        "target": "5551234567",
        "associate": "5559876543",
        "direction": "incoming",
        "call_start": "2026-08-29 23:05:17",
        "duration": "00:00:35",
        "end_time": "2026-08-29 23:05:52",
        "classification": "pertinent",
        "call_progress": "complete",
        "language": "English",
        "monitor": None,
        "text_message": None,
        "audio_duration": 2500,
        "detected_locales": ["en-US"],
    }


@pytest.mark.unit
def test_transform_result_frontmatter_key_order_is_fixed(tmp_path):
    source_path = tmp_path / "audio.mp3"

    output = transform_result(_VALID_RESULT, source_path, _CALL_RECORD)

    assert list(output.frontmatter.keys()) == _FRONTMATTER_KEY_ORDER


@pytest.mark.unit
def test_transform_result_renders_one_body_line_per_segment(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "First", "locale": "en-US"},
            {"offsetMilliseconds": 2000, "durationMilliseconds": 3000, "text": "Second", "locale": "en-US"},
        ],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.body == "00:00:00 - 00:00:02 First\n00:00:02 - 00:00:05 Second"


@pytest.mark.unit
def test_transform_result_sorts_segments_by_start_when_input_is_unordered(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 2000, "durationMilliseconds": 3000, "text": "Second", "locale": "en-US"},
            {"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "First", "locale": "en-US"},
        ],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.body == "00:00:00 - 00:00:02 First\n00:00:02 - 00:00:05 Second"


@pytest.mark.unit
def test_transform_result_uses_custom_timestamp_format(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 2000,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "Hello"}],
    }

    output = transform_result(result, source_path, _CALL_RECORD, timestamp_format="%M:%S")

    assert output.body == "00:00 - 00:02 Hello"


@pytest.mark.unit
def test_validate_timestamp_format_raises_on_an_invalid_directive():
    with pytest.raises(ValueError):
        validate_timestamp_format("%Q")


@pytest.mark.unit
def test_validate_timestamp_format_accepts_a_valid_format():
    validate_timestamp_format("%H:%M:%S")


@pytest.mark.unit
def test_transform_result_renders_speaker_label_when_phrase_has_a_speaker(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "Hi there", "speaker": 1},
            {"offsetMilliseconds": 2000, "durationMilliseconds": 3000, "text": "Hello back", "speaker": 2},
        ],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.body == "00:00:00 - 00:00:02 Speaker 1: Hi there\n00:00:02 - 00:00:05 Speaker 2: Hello back"


@pytest.mark.unit
def test_transform_result_omits_speaker_label_when_phrase_has_no_speaker(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 2000,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "Hello"}],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.body == "00:00:00 - 00:00:02 Hello"


@pytest.mark.unit
def test_transform_result_detected_locales_lists_distinct_locales_across_phrases(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "Hello", "locale": "en-US"},
            {"offsetMilliseconds": 2000, "durationMilliseconds": 3000, "text": "Hola", "locale": "es-US"},
            {"offsetMilliseconds": 5000, "durationMilliseconds": 1000, "text": "again", "locale": "en-US"},
        ],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.frontmatter["detected_locales"] == ["en-US", "es-US"]


@pytest.mark.unit
def test_transform_result_detected_locales_empty_when_no_phrase_reports_locale(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 2000,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "Hello"}],
    }

    output = transform_result(result, source_path, _CALL_RECORD)

    assert output.frontmatter["detected_locales"] == []


@pytest.mark.unit
def test_transform_result_raises_empty_transcription_result_error_when_phrases_empty(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {"durationMilliseconds": 0, "phrases": []}

    with pytest.raises(EmptyTranscriptionResultError, match="audio.mp3"):
        transform_result(result, source_path, _CALL_RECORD)


@pytest.mark.unit
def test_transform_result_raises_empty_transcription_result_error_when_phrases_key_missing(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {"durationMilliseconds": 0}

    with pytest.raises(EmptyTranscriptionResultError, match="audio.mp3"):
        transform_result(result, source_path, _CALL_RECORD)


@pytest.mark.unit
def test_write_transcript_txt_creates_sibling_file_with_correct_content(tmp_path):
    source_path = tmp_path / "audio.mp3"
    output = transform_result(_VALID_RESULT, source_path, _CALL_RECORD)

    destination = write_transcript_txt(output, source_path, _REF, _TARGET)

    assert destination == tmp_path / "audio-transcript.txt"
    text = destination.read_text(encoding="utf-8")
    frontmatter_text, body = text.split("---\n", 2)[1:]
    assert yaml.safe_load(frontmatter_text) == output.frontmatter
    assert body == output.body


@pytest.mark.unit
def test_write_transcript_txt_writes_to_destination_directory_when_given(tmp_path):
    source_path = tmp_path / "source" / "audio.mp3"
    destination_dir = tmp_path / "out"
    output = transform_result(_VALID_RESULT, source_path, _CALL_RECORD)

    destination = write_transcript_txt(output, source_path, _REF, _TARGET, destination_dir)

    assert destination == destination_dir / f"{_REF}-{_TARGET}-audio-transcript.txt"
    assert destination.exists()


@pytest.mark.unit
def test_write_transcript_txt_leaves_no_partial_file_on_replace_failure(mocker, tmp_path):
    source_path = tmp_path / "audio.mp3"
    output = transform_result(_VALID_RESULT, source_path, _CALL_RECORD)
    mocker.patch("transcribe.transform.os.replace", side_effect=OSError("disk full"))

    with pytest.raises(OutputWriteError):
        write_transcript_txt(output, source_path, _REF, _TARGET)

    assert not (tmp_path / "audio-transcript.txt").exists()
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.unit
def test_write_transcript_txt_accepts_error_output(tmp_path):
    source_path = tmp_path / "audio.mp3"
    output = build_error_output(source_path, MissingFileError(source_path))

    destination = write_transcript_txt(output, source_path, _REF, _TARGET)

    text = destination.read_text(encoding="utf-8")
    frontmatter_text = text.split("---\n", 2)[1]
    frontmatter = yaml.safe_load(frontmatter_text)
    assert frontmatter["source_file"] == "audio.mp3"
    assert frontmatter["error"] == f"file not found: {source_path}"
    assert frontmatter["ref"] is None


@pytest.mark.unit
def test_build_error_output_uses_source_file_name_and_error_message_with_no_call_record(tmp_path):
    source_path = tmp_path / "audio.mp3"

    output = build_error_output(source_path, MissingFileError(source_path))

    assert output == ErrorOutput(
        frontmatter={
            "source_file": "audio.mp3",
            "ref": None,
            "target": None,
            "associate": None,
            "direction": None,
            "call_start": None,
            "duration": None,
            "end_time": None,
            "classification": None,
            "call_progress": None,
            "language": None,
            "monitor": None,
            "text_message": None,
            "error": f"file not found: {source_path}",
        }
    )


@pytest.mark.unit
def test_build_error_output_carries_partial_call_record(tmp_path):
    source_path = tmp_path / "audio.mp3"

    output = build_error_output(source_path, MissingFileError(source_path), _CALL_RECORD)

    assert output.frontmatter["ref"] == "123"
    assert output.frontmatter["target"] == "5551234567"
    assert output.frontmatter["error"] == f"file not found: {source_path}"


@pytest.mark.unit
def test_output_path_returns_sibling_transcript_txt_path_by_default():
    assert output_path(Path("dir/audio.mp3"), _REF, _TARGET) == Path("dir/audio-transcript.txt")


@pytest.mark.unit
def test_output_path_uses_ref_target_stem_naming_when_destination_given():
    destination = Path("out")
    expected = destination / "123-5551234567-audio-transcript.txt"
    assert output_path(Path("dir/audio.mp3"), _REF, _TARGET, destination) == expected


@pytest.mark.unit
def test_has_existing_transcript_false_when_no_output_file(tmp_path):
    assert has_existing_transcript(tmp_path / "audio.mp3", _REF, _TARGET) is False


@pytest.mark.unit
def test_has_existing_transcript_true_for_successful_output(tmp_path):
    source_path = tmp_path / "audio.mp3"
    write_transcript_txt(transform_result(_VALID_RESULT, source_path, _CALL_RECORD), source_path, _REF, _TARGET)

    assert has_existing_transcript(source_path, _REF, _TARGET) is True


@pytest.mark.unit
def test_has_existing_transcript_true_for_successful_output_in_destination_directory(tmp_path):
    source_path = tmp_path / "source" / "audio.mp3"
    destination_dir = tmp_path / "out"
    write_transcript_txt(
        transform_result(_VALID_RESULT, source_path, _CALL_RECORD), source_path, _REF, _TARGET, destination_dir
    )

    assert has_existing_transcript(source_path, _REF, _TARGET, destination_dir) is True


@pytest.mark.unit
def test_has_existing_transcript_false_for_error_output(tmp_path):
    source_path = tmp_path / "audio.mp3"
    write_transcript_txt(build_error_output(source_path, MissingFileError(source_path)), source_path, _REF, _TARGET)

    assert has_existing_transcript(source_path, _REF, _TARGET) is False


@pytest.mark.unit
def test_has_existing_transcript_false_for_file_with_no_frontmatter_block(tmp_path):
    source_path = tmp_path / "audio.mp3"
    output_path(source_path, _REF, _TARGET).write_text("not frontmatter at all", encoding="utf-8")

    assert has_existing_transcript(source_path, _REF, _TARGET) is False


@pytest.mark.unit
def test_has_existing_transcript_false_for_malformed_yaml(tmp_path):
    source_path = tmp_path / "audio.mp3"
    output_path(source_path, _REF, _TARGET).write_text("---\nkey: [unterminated\n---\nbody", encoding="utf-8")

    assert has_existing_transcript(source_path, _REF, _TARGET) is False


@pytest.mark.unit
def test_write_transcript_txt_renders_multiline_text_message_as_block_literal(tmp_path):
    source_path = tmp_path / "audio.mp3"
    call_record = _CALL_RECORD._replace(text_message="line one\nline two")
    output = transform_result(_VALID_RESULT, source_path, call_record)

    destination = write_transcript_txt(output, source_path, _REF, _TARGET)

    text = destination.read_text(encoding="utf-8")
    assert "text_message: |-\n" in text or "text_message: |\n" in text
    frontmatter_text = text.split("---\n", 2)[1]
    assert yaml.safe_load(frontmatter_text)["text_message"] == "line one\nline two"
