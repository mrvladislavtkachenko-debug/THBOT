"""Tests for AI JSON extraction and PostAnalysisResult validation."""

import pytest
from pydantic import ValidationError

from app.ai.json_extractor import InvalidJSONError, extract_json, find_json_array
from app.schemas import PostAnalysisResult


def test_extract_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced():
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_with_prose():
    text = 'Here is the result: {"topic": "AI", "post_type": "news"} thanks'
    assert extract_json(text) == {"topic": "AI", "post_type": "news"}


def test_extract_no_json_raises():
    with pytest.raises(InvalidJSONError):
        extract_json("no json here")


def test_extract_empty_raises():
    with pytest.raises(InvalidJSONError):
        extract_json("")


def test_find_array():
    assert find_json_array('[1,2,3]') == [1, 2, 3]


def test_valid_result():
    data = {
        "topic": "AI", "subtopic": "models", "post_type": "news", "language": "ru",
        "quality_score": 8, "originality_score": 7, "factual_support": 7,
        "source_quality": "strong", "advertising_score": 1, "manipulation_score": 2,
        "scam_signals": [], "summary": "s", "why_valuable": "w",
    }
    r = PostAnalysisResult.model_validate(data)
    assert r.quality_score == 8


def test_wrong_types():
    data = {"quality_score": "not-a-number"}
    with pytest.raises(ValidationError):
        PostAnalysisResult.model_validate(data)


def test_missing_optional_fields_default():
    r = PostAnalysisResult.model_validate({})
    assert r.post_type == "other"
    assert r.scam_signals == []


def test_clamped_scores():
    r = PostAnalysisResult(quality_score=999, manipulation_score=-5)
    norm = r.normalized()
    assert norm["quality_score"] == 10.0
    assert norm["manipulation_score"] == 0.0
