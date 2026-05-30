import io
import zipfile

import pytest

from zip_extractor import extract

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_zip(files: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP from {arcname: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


CHAT_TXT = b"15/03/2024, 10:30 - Rahul: bhai dune dekha?"
IMG_BYTES = b"\xff\xd8\xff"  # minimal JPEG magic bytes


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_extracts_chat_txt_and_images():
    z = _make_zip({
        "_chat.txt": CHAT_TXT,
        "IMG-001.jpg": IMG_BYTES,
        "IMG-002.png": IMG_BYTES,
    })
    chat, images = extract(z)
    assert chat == CHAT_TXT
    assert "IMG-001.jpg" in images
    assert "IMG-002.png" in images
    assert images["IMG-001.jpg"] == IMG_BYTES


def test_finds_chat_txt_in_nested_folder():
    z = _make_zip({
        "WhatsApp Chat with Friends/_chat.txt": CHAT_TXT,
        "WhatsApp Chat with Friends/IMG-001.jpg": IMG_BYTES,
    })
    chat, images = extract(z)
    assert chat == CHAT_TXT
    assert "IMG-001.jpg" in images


def test_discards_audio_and_video():
    z = _make_zip({
        "_chat.txt": CHAT_TXT,
        "PTT-001.opus": b"audio",
        "VID-001.mp4": b"video",
        "DOC-001.pdf": b"doc",
        "IMG-001.jpg": IMG_BYTES,
    })
    _, images = extract(z)
    assert "PTT-001.opus" not in images
    assert "VID-001.mp4" not in images
    assert "DOC-001.pdf" not in images
    assert "IMG-001.jpg" in images


def test_supports_all_image_extensions():
    z = _make_zip({
        "_chat.txt": CHAT_TXT,
        "a.jpg": IMG_BYTES,
        "b.jpeg": IMG_BYTES,
        "c.png": IMG_BYTES,
        "d.webp": IMG_BYTES,
        "e.gif": IMG_BYTES,
    })
    _, images = extract(z)
    assert set(images.keys()) == {"a.jpg", "b.jpeg", "c.png", "d.webp", "e.gif"}


def test_raises_if_no_chat_txt():
    z = _make_zip({"IMG-001.jpg": IMG_BYTES})
    with pytest.raises(ValueError, match="No WhatsApp chat"):
        extract(z)


def test_raises_if_zip_too_large():
    large = b"x" * (51 * 1024 * 1024)
    with pytest.raises(ValueError, match="50 MB"):
        extract(large)


def test_fallback_to_any_txt_when_no_chat_txt():
    z = _make_zip({"export.txt": CHAT_TXT, "IMG-001.jpg": IMG_BYTES})
    chat, _ = extract(z)
    assert chat == CHAT_TXT


def test_empty_image_map_when_no_images():
    z = _make_zip({"_chat.txt": CHAT_TXT})
    _, images = extract(z)
    assert images == {}
