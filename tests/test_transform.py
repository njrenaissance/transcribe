import json

import pytest

from transcribe.errors import EmptyTranscriptionResultError, OutputWriteError
from transcribe.transform import transform_result, write_transcript_json


@pytest.mark.unit
def test_transform_result_maps_all_fields_from_valid_result(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 2500,
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 2500, "text": "Hello world", "locale": "en-US"}],
    }

    output = transform_result(result, source_path)

    assert output == {
        "source_file": "audio.mp3",
        "language": "en-US",
        "duration_seconds": 2.5,
        "segments": [{"start": 0.0, "end": 2.5, "text": "Hello world"}],
    }


@pytest.mark.unit
def test_transform_result_produces_one_segment_per_phrase(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {
        "durationMilliseconds": 5000,
        "phrases": [
            {"offsetMilliseconds": 0, "durationMilliseconds": 2000, "text": "First", "locale": "en-US"},
            {"offsetMilliseconds": 2000, "durationMilliseconds": 3000, "text": "Second", "locale": "en-US"},
        ],
    }

    output = transform_result(result, source_path)

    assert output["segments"] == [
        {"start": 0.0, "end": 2.0, "text": "First"},
        {"start": 2.0, "end": 5.0, "text": "Second"},
    ]


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

    output = transform_result(result, source_path)

    assert [segment["text"] for segment in output["segments"]] == ["First", "Second"]
    assert [segment["start"] for segment in output["segments"]] == sorted(
        segment["start"] for segment in output["segments"]
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "first_phrase",
    [
        pytest.param({"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "Hi"}, id="locale_key_missing"),
        pytest.param(
            {"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "Hi", "locale": ""}, id="locale_empty"
        ),
    ],
)
def test_transform_result_falls_back_to_requested_locale(tmp_path, first_phrase):
    source_path = tmp_path / "audio.mp3"
    result = {"durationMilliseconds": 1000, "phrases": [first_phrase]}

    output = transform_result(result, source_path, requested_locale="fr-FR")

    assert output["language"] == "fr-FR"


@pytest.mark.unit
def test_transform_result_raises_empty_transcription_result_error_when_phrases_empty(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {"durationMilliseconds": 0, "phrases": []}

    with pytest.raises(EmptyTranscriptionResultError, match="audio.mp3"):
        transform_result(result, source_path)


@pytest.mark.unit
def test_transform_result_raises_empty_transcription_result_error_when_phrases_key_missing(tmp_path):
    source_path = tmp_path / "audio.mp3"
    result = {"durationMilliseconds": 0}

    with pytest.raises(EmptyTranscriptionResultError, match="audio.mp3"):
        transform_result(result, source_path)


@pytest.mark.unit
def test_write_transcript_json_creates_sibling_file_with_correct_content(tmp_path):
    source_path = tmp_path / "audio.mp3"
    output = {
        "source_file": "audio.mp3",
        "language": "en-US",
        "duration_seconds": 2.5,
        "segments": [{"start": 0.0, "end": 2.5, "text": "Hello world"}],
    }

    destination = write_transcript_json(output, source_path)

    assert destination == tmp_path / "audio.mp3.json"
    assert json.loads(destination.read_text(encoding="utf-8")) == output


@pytest.mark.unit
def test_write_transcript_json_leaves_no_partial_file_on_replace_failure(mocker, tmp_path):
    source_path = tmp_path / "audio.mp3"
    output = {"source_file": "audio.mp3", "language": "en-US", "duration_seconds": 1.0, "segments": []}
    mocker.patch("transcribe.transform.os.replace", side_effect=OSError("disk full"))

    with pytest.raises(OutputWriteError):
        write_transcript_json(output, source_path)

    assert not (tmp_path / "audio.mp3.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []
