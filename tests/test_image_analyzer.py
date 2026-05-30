import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from image_analyzer import ImageAnalysisResult, analyze

# Minimal 1x1 JPEG bytes
_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00"
    b"\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00"
    b"\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9"
)


def _mock_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def test_returns_result_for_each_image():
    image_map = {"a.jpg": _JPEG, "b.jpg": _JPEG}
    message_links = {
        "a.jpg": {"sender": "Rahul", "text": "dune poster", "timestamp": "2024-01-15T10:30:00"},
        "b.jpg": {"sender": "Priya", "text": "mast tha", "timestamp": "2024-01-15T10:31:00"},
    }

    pass1_resp = json.dumps({
        "results": [
            {"filename": "a.jpg", "movie_title": "Dune: Part Two"},
            {"filename": "b.jpg", "movie_title": None},
        ]
    })
    pass2_resp = json.dumps({
        "results": [
            {"filename": "a.jpg", "emotion_label": "informational"},
            {"filename": "b.jpg", "emotion_label": "positive"},
        ]
    })

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _mock_response(pass1_resp),
        _mock_response(pass2_resp),
    ]

    with patch("image_analyzer.anthropic.Anthropic", return_value=mock_client):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            results = analyze(image_map, message_links)

    assert "a.jpg" in results
    assert results["a.jpg"]["movie_title"] == "Dune: Part Two"
    assert results["a.jpg"]["emotion_label"] == "informational"
    assert results["b.jpg"]["movie_title"] is None
    assert results["b.jpg"]["emotion_label"] == "positive"


def test_skips_image_on_api_failure():
    image_map = {"a.jpg": _JPEG}
    message_links = {}

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("image_analyzer.anthropic.Anthropic", return_value=mock_client):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            results = analyze(image_map, message_links)

    assert results == {}


def test_raises_if_no_api_key():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            analyze({"a.jpg": _JPEG}, {})


def test_result_has_required_fields():
    image_map = {"a.jpg": _JPEG}
    message_links = {"a.jpg": {"sender": "Rahul", "text": "nice", "timestamp": "2024-01-15"}}

    pass1_resp = json.dumps({"results": [{"filename": "a.jpg", "movie_title": "Dune"}]})
    pass2_resp = json.dumps({"results": [{"filename": "a.jpg", "emotion_label": "positive"}]})

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _mock_response(pass1_resp),
        _mock_response(pass2_resp),
    ]

    with patch("image_analyzer.anthropic.Anthropic", return_value=mock_client):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            results = analyze(image_map, message_links)

    result = results["a.jpg"]
    assert "movie_title" in result
    assert "emotion_label" in result
    assert "sender" in result
    assert "timestamp" in result
    assert "message_context" in result
