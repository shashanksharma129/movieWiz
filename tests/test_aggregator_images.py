import io
import base64

import pytest
from PIL import Image

from aggregator import attach_images


def _tiny_jpeg() -> bytes:
    """Create a real 2x2 JPEG using Pillow."""
    img = Image.new("RGB", (2, 2), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _base_data() -> dict:
    return {
        "movies": [
            {
                "title": "Dune: Part Two",
                "shared_images": [],
            }
        ],
        "image_analysis": {},
        "unlinked_images": [],
    }


def test_links_image_to_matching_movie():
    data = _base_data()
    analysis = {
        "IMG-001.jpg": {
            "filename": "IMG-001.jpg",
            "movie_title": "Dune: Part Two",
            "emotion_label": "positive",
            "sender": "Rahul",
            "timestamp": "2024-01-15T10:30:00",
            "message_context": "ekdum zabardast",
        }
    }
    image_map = {"IMG-001.jpg": _tiny_jpeg()}
    attach_images(data, analysis, image_map)

    assert len(data["movies"][0]["shared_images"]) == 1
    img_entry = data["movies"][0]["shared_images"][0]
    assert img_entry["filename"] == "IMG-001.jpg"
    assert img_entry["sender"] == "Rahul"
    assert img_entry["emotion_label"] == "positive"
    assert img_entry["message_context"] == "ekdum zabardast"
    assert "base64_thumbnail" in img_entry


def test_unlinked_image_goes_to_unlinked_images():
    data = _base_data()
    analysis = {
        "IMG-002.jpg": {
            "filename": "IMG-002.jpg",
            "movie_title": None,
            "emotion_label": "funny/meme",
            "sender": "Priya",
            "timestamp": "2024-01-15T11:00:00",
            "message_context": "haha",
        }
    }
    image_map = {"IMG-002.jpg": _tiny_jpeg()}
    attach_images(data, analysis, image_map)

    assert len(data["unlinked_images"]) == 1
    assert data["unlinked_images"][0]["filename"] == "IMG-002.jpg"
    assert len(data["movies"][0]["shared_images"]) == 0


def test_image_analysis_summary_populated():
    data = _base_data()
    analysis = {
        "a.jpg": {
            "filename": "a.jpg", "movie_title": "Dune: Part Two",
            "emotion_label": "positive", "sender": "Rahul",
            "timestamp": None, "message_context": None,
        },
        "b.jpg": {
            "filename": "b.jpg", "movie_title": None,
            "emotion_label": "neutral", "sender": "Priya",
            "timestamp": None, "message_context": None,
        },
    }
    image_map = {"a.jpg": _tiny_jpeg(), "b.jpg": _tiny_jpeg()}
    attach_images(data, analysis, image_map)

    assert data["image_analysis"]["total_images"] == 2
    assert data["image_analysis"]["linked"] == 1
    assert data["image_analysis"]["unlinked"] == 1


def test_thumbnail_is_valid_base64_jpeg():
    data = _base_data()
    analysis = {
        "IMG-001.jpg": {
            "filename": "IMG-001.jpg", "movie_title": "Dune: Part Two",
            "emotion_label": "positive", "sender": "Rahul",
            "timestamp": None, "message_context": None,
        }
    }
    image_map = {"IMG-001.jpg": _tiny_jpeg()}
    attach_images(data, analysis, image_map)

    b64 = data["movies"][0]["shared_images"][0]["base64_thumbnail"]
    decoded = base64.b64decode(b64)
    img = Image.open(io.BytesIO(decoded))
    assert img.format == "JPEG"


def test_movie_with_no_linked_images_has_empty_list():
    data = _base_data()
    attach_images(data, {}, {})
    assert data["movies"][0]["shared_images"] == []


def test_corrupted_image_skipped_silently():
    data = _base_data()
    analysis = {
        "bad.jpg": {
            "filename": "bad.jpg", "movie_title": "Dune: Part Two",
            "emotion_label": "positive", "sender": "Rahul",
            "timestamp": None, "message_context": None,
        }
    }
    image_map = {"bad.jpg": b"not-an-image"}
    attach_images(data, analysis, image_map)  # must not raise
    assert len(data["movies"][0]["shared_images"]) == 0
