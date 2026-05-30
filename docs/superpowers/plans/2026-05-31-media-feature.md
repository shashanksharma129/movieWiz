# Media Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ZIP file upload support so users can upload a WhatsApp export containing images, run a two-pass Claude vision analysis to identify movies and emotion labels from shared images, and surface this data in four visualization updates.

**Architecture:** The existing text pipeline is untouched — a new `zip_extractor.py` pulls the chat `.txt` and whitelisted images from the ZIP, `image_analyzer.py` runs a two-pass Claude vision analysis after the text pipeline, and `aggregator.attach_images()` merges results into the existing data model. `.txt` uploads bypass all new code entirely.

**Tech Stack:** Python `zipfile` (stdlib), `Pillow` (thumbnail resizing), `anthropic` SDK (Claude Sonnet 4.6 vision), `streamlit`, `plotly`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `zip_extractor.py` | Create | Unzip, find chat `.txt`, whitelist images, return `(chat_bytes, image_map)` |
| `image_analyzer.py` | Create | Two-pass Claude vision: movie ID + emotion label per image |
| `parser.py` | Modify (line 94–100) | Tag messages that reference a media filename |
| `aggregator.py` | Modify (add method) | `attach_images()` merges image analysis into movie entries, generates thumbnails |
| `cache.py` | Modify (line 6) | Bump `_CACHE_VERSION` from `"v2"` to `"v3"` |
| `pyproject.toml` | Modify | Add `Pillow>=10.0.0` dependency |
| `app.py` | Modify | ZIP upload routing, progress bar, five visualization changes |
| `tests/test_zip_extractor.py` | Create | Unit tests for extraction, size limits, file detection |
| `tests/test_parser_media.py` | Create | Tests for `media_filename` tagging |
| `tests/test_image_analyzer.py` | Create | Tests with mocked anthropic client |
| `tests/test_aggregator_images.py` | Create | Tests for `attach_images()` |

---

## Task 1: Add Pillow dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Pillow to pyproject.toml**

Open `pyproject.toml` and add `"Pillow>=10.0.0"` to the `dependencies` list:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "Pillow>=10.0.0",
    "streamlit>=1.35.0",
    "plotly>=5.20.0",
    "pandas>=2.0.0",
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
    "thefuzz[speedup]>=0.20.0",
]
```

- [ ] **Step 2: Install the dependency**

```bash
uv sync
```

Expected: Pillow installs successfully, lockfile updates.

- [ ] **Step 3: Verify import works**

```bash
python -c "from PIL import Image; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add Pillow dependency for image thumbnail generation"
```

---

## Task 2: Create `zip_extractor.py`

**Files:**
- Create: `zip_extractor.py`
- Create: `tests/test_zip_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_zip_extractor.py`:

```python
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
    # Build a ZIP that reports > 50MB when we fake the size check.
    # We patch len() indirectly by passing oversized bytes.
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
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
pytest tests/test_zip_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'zip_extractor'`

- [ ] **Step 3: Implement `zip_extractor.py`**

Create `zip_extractor.py`:

```python
import io
import zipfile
from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_ZIP_BYTES = 50 * 1024 * 1024


def extract(zip_bytes: bytes) -> tuple[bytes, dict[str, bytes]]:
    """
    Returns (chat_txt_bytes, image_map {filename -> bytes}).
    Raises ValueError if ZIP > 50MB or no chat .txt found.
    Non-image files are silently discarded.
    """
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise ValueError(
            f"ZIP file is {len(zip_bytes) / 1024 / 1024:.1f} MB — limit is 50 MB."
        )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

        # {basename -> arcname} for lookup
        basename_map: dict[str, str] = {}
        for n in names:
            basename_map[Path(n).name] = n

        chat_arcname = basename_map.get("_chat.txt")
        if chat_arcname is None:
            chat_arcname = next(
                (arc for base, arc in basename_map.items() if base.endswith(".txt")),
                None,
            )
        if chat_arcname is None:
            raise ValueError("No WhatsApp chat .txt file found in ZIP.")

        chat_bytes = zf.read(chat_arcname)

        image_map: dict[str, bytes] = {}
        for arc in names:
            base = Path(arc).name
            if Path(base).suffix.lower() in _IMAGE_EXTS:
                image_map[base] = zf.read(arc)

        return chat_bytes, image_map
```

- [ ] **Step 4: Run tests to confirm they all pass**

```bash
pytest tests/test_zip_extractor.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zip_extractor.py tests/test_zip_extractor.py
git commit -m "feat: add zip_extractor module with image whitelisting"
```

---

## Task 3: Update `parser.py` to tag media filenames

**Files:**
- Modify: `parser.py` (lines 1–3 and 98–100)
- Create: `tests/test_parser_media.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_parser_media.py`:

```python
from parser import parse


def test_jpg_message_tagged_with_media_filename():
    chat = b"15/03/2024, 10:30 - Rahul: IMG-20240115-WA0001.jpg (file attached)"
    messages, _ = parse(chat)
    assert len(messages) == 1
    assert messages[0]["media_filename"] == "IMG-20240115-WA0001.jpg"


def test_png_message_tagged():
    chat = b"15/03/2024, 10:30 - Rahul: PHOTO-001.png (file attached)"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "PHOTO-001.png"


def test_media_filename_without_file_attached_suffix():
    chat = b"15/03/2024, 10:30 - Rahul: IMG-001.jpg"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "IMG-001.jpg"


def test_non_media_message_has_no_media_filename():
    chat = b"15/03/2024, 10:30 - Rahul: bhai dune dekha?"
    messages, _ = parse(chat)
    assert "media_filename" not in messages[0]


def test_audio_file_not_tagged_as_image():
    chat = b"15/03/2024, 10:30 - Rahul: PTT-001.opus (file attached)"
    messages, _ = parse(chat)
    # Opus messages are included as regular messages (not filtered, not tagged)
    assert "media_filename" not in messages[0]


def test_webp_tagged():
    chat = b"15/03/2024, 10:30 - Rahul: STICKER-001.webp (file attached)"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "STICKER-001.webp"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_parser_media.py -v
```

Expected: all FAIL (no `media_filename` key in messages)

- [ ] **Step 3: Add `_MEDIA_IMAGE_RE` and update `parse()`**

Add after the `_SYSTEM_SENDER_RE` block (after line 41 in `parser.py`):

```python
_MEDIA_IMAGE_RE = re.compile(
    r"^(\S+\.(jpg|jpeg|png|webp|gif))\s*(\(file attached\))?$",
    re.IGNORECASE,
)
```

Then in the `parse()` function, after `current = {"timestamp": ts, "sender": sender, "text": text_part}` (line 99), add:

```python
            media_match = _MEDIA_IMAGE_RE.match(text_part.strip())
            if media_match:
                current["media_filename"] = media_match.group(1)
```

The full updated block in `parse()` should look like:

```python
            ts = _parse_timestamp(date_str, time_str)
            current = {"timestamp": ts, "sender": sender, "text": text_part}
            media_match = _MEDIA_IMAGE_RE.match(text_part.strip())
            if media_match:
                current["media_filename"] = media_match.group(1)
            messages.append(current)
```

- [ ] **Step 4: Run all parser tests**

```bash
pytest tests/test_parser.py tests/test_parser_media.py -v
```

Expected: all 19 tests PASS (13 existing + 6 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py tests/test_parser_media.py
git commit -m "feat: tag messages with media_filename for image linking"
```

---

## Task 4: Create `image_analyzer.py`

**Files:**
- Create: `image_analyzer.py`
- Create: `tests/test_image_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_analyzer.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_image_analyzer.py -v
```

Expected: `ModuleNotFoundError: No module named 'image_analyzer'`

- [ ] **Step 3: Implement `image_analyzer.py`**

Create `image_analyzer.py`:

```python
import base64
import json
import os
from pathlib import Path
from typing import TypedDict

import anthropic
from dotenv import load_dotenv

from utils import with_retry

load_dotenv()

_MODEL = "claude-sonnet-4-6"
_BATCH_SIZE = 5

_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class ImageAnalysisResult(TypedDict):
    filename: str
    movie_title: str | None
    emotion_label: str
    sender: str | None
    timestamp: str | None
    message_context: str | None


def _b64(img_bytes: bytes) -> str:
    return base64.standard_b64encode(img_bytes).decode()


def _mime(filename: str) -> str:
    return _MIME_TYPES.get(Path(filename).suffix.lower(), "image/jpeg")


def _image_block(filename: str, img_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _mime(filename),
            "data": _b64(img_bytes),
        },
    }


def _context_line(filename: str, message_links: dict[str, dict]) -> str:
    link = message_links.get(filename, {})
    sender = link.get("sender", "unknown")
    text = link.get("text", "")
    return f"[{filename}] sent by {sender}: {text}"


def _run_pass1(
    client: anthropic.Anthropic,
    batch: list[tuple[str, bytes]],
    message_links: dict[str, dict],
) -> dict[str, str | None]:
    """Returns {filename -> movie_title | None} for a batch."""
    content = [_image_block(fname, fbytes) for fname, fbytes in batch]
    context = "\n".join(_context_line(fname, message_links) for fname, _ in batch)
    filenames = [fname for fname, _ in batch]
    content.append({
        "type": "text",
        "text": (
            f"These {len(batch)} images were shared in a WhatsApp movie discussion group.\n"
            f"Message context:\n{context}\n\n"
            "For each image (in order), identify if it shows a movie poster, title card, "
            "or recognizable film scene. Return ONLY valid JSON with this structure, no other text:\n"
            '{"results": [{"filename": "IMG-001.jpg", "movie_title": "Dune: Part Two or null if not a movie"}]}\n'
            f"Filenames in order: {filenames}"
        ),
    })
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        parsed = json.loads(text[start:end]) if start >= 0 and end > start else {"results": []}

    return {r["filename"]: r.get("movie_title") for r in parsed.get("results", [])}


def _run_pass2(
    client: anthropic.Anthropic,
    batch: list[tuple[str, bytes]],
    message_links: dict[str, dict],
) -> dict[str, str]:
    """Returns {filename -> emotion_label} for a batch."""
    content = [_image_block(fname, fbytes) for fname, fbytes in batch]
    context = "\n".join(_context_line(fname, message_links) for fname, _ in batch)
    filenames = [fname for fname, _ in batch]
    content.append({
        "type": "text",
        "text": (
            f"These {len(batch)} images were shared in a WhatsApp movie discussion group.\n"
            f"Message context:\n{context}\n\n"
            "For each image (in order), assign one emotion label that best describes the reaction "
            "the sender is expressing. Labels: positive, neutral, negative, funny/meme, informational.\n"
            "Return ONLY valid JSON, no other text:\n"
            '{"results": [{"filename": "IMG-001.jpg", "emotion_label": "positive"}]}\n'
            f"Filenames in order: {filenames}"
        ),
    })
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        parsed = json.loads(text[start:end]) if start >= 0 and end > start else {"results": []}

    return {r["filename"]: r.get("emotion_label", "neutral") for r in parsed.get("results", [])}


def analyze(
    image_map: dict[str, bytes],
    message_links: dict[str, dict],
) -> dict[str, ImageAnalysisResult]:
    """
    Returns per-filename analysis results.
    Images that fail are silently skipped.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    items = list(image_map.items())
    batches = [items[i: i + _BATCH_SIZE] for i in range(0, len(items), _BATCH_SIZE)]

    movie_titles: dict[str, str | None] = {}
    emotion_labels: dict[str, str] = {}

    for batch in batches:
        try:
            movie_titles.update(with_retry(_run_pass1, client, batch, message_links))
        except Exception as e:
            print(f"Warning: image pass1 batch failed ({e}), skipping")

        try:
            emotion_labels.update(with_retry(_run_pass2, client, batch, message_links))
        except Exception as e:
            print(f"Warning: image pass2 batch failed ({e}), skipping")

    results: dict[str, ImageAnalysisResult] = {}
    for filename in image_map:
        if filename not in movie_titles and filename not in emotion_labels:
            continue
        link = message_links.get(filename, {})
        results[filename] = ImageAnalysisResult(
            filename=filename,
            movie_title=movie_titles.get(filename),
            emotion_label=emotion_labels.get(filename, "neutral"),
            sender=link.get("sender"),
            timestamp=link.get("timestamp"),
            message_context=link.get("text"),
        )

    return results
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_image_analyzer.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add image_analyzer.py tests/test_image_analyzer.py
git commit -m "feat: add image_analyzer with two-pass Claude vision analysis"
```

---

## Task 5: Add `attach_images()` to `aggregator.py`

**Files:**
- Modify: `aggregator.py`
- Create: `tests/test_aggregator_images.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_aggregator_images.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_aggregator_images.py -v
```

Expected: `ImportError: cannot import name 'attach_images' from 'aggregator'`

- [ ] **Step 3: Add `attach_images()` to `aggregator.py`**

Add these imports at the top of `aggregator.py` (after the existing `from enricher import empty_tmdb`):

```python
import base64
import io

from PIL import Image
```

Add this function at the bottom of `aggregator.py` (after `attach_tmdb()`):

```python
def _make_thumbnail(img_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


def attach_images(
    data: dict,
    analysis: dict,
    image_map: dict[str, bytes],
) -> None:
    """
    Merges image analysis results into data in-place.
    Adds shared_images to matched movies, unlinked_images for unmatched.
    Populates data["image_analysis"] summary.
    """
    movie_index = {m["title"]: m for m in data.get("movies", [])}
    for m in data.get("movies", []):
        m.setdefault("shared_images", [])
    data.setdefault("unlinked_images", [])

    linked = 0
    unlinked = 0

    for filename, result in analysis.items():
        try:
            thumbnail = _make_thumbnail(image_map[filename])
        except Exception:
            continue

        entry = {
            "filename": filename,
            "sender": result.get("sender"),
            "timestamp": result.get("timestamp"),
            "message_context": result.get("message_context"),
            "emotion_label": result.get("emotion_label", "neutral"),
            "base64_thumbnail": thumbnail,
        }

        movie_title = result.get("movie_title")
        if movie_title and movie_title in movie_index:
            movie_index[movie_title]["shared_images"].append(entry)
            linked += 1
        else:
            data["unlinked_images"].append(entry)
            unlinked += 1

    data["image_analysis"] = {
        "total_images": linked + unlinked,
        "linked": linked,
        "unlinked": unlinked,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_aggregator_images.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
pytest -v
```

Expected: all tests PASS (parser, zip_extractor, image_analyzer, aggregator_images)

- [ ] **Step 6: Commit**

```bash
git add aggregator.py tests/test_aggregator_images.py
git commit -m "feat: add attach_images() to aggregator with thumbnail generation"
```

---

## Task 6: Bump cache version to v3

**Files:**
- Modify: `cache.py` (line 6)

- [ ] **Step 1: Update the cache version string**

In `cache.py`, change line 6 from:

```python
_CACHE_VERSION = "v2"
```

to:

```python
_CACHE_VERSION = "v3"
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add cache.py
git commit -m "feat: bump cache version to v3 for media feature"
```

---

## Task 7: Update `app.py` — ZIP upload routing and pipeline wiring

**Files:**
- Modify: `app.py` (lines 14–18, 81, 143–192)

- [ ] **Step 1: Add imports for new modules**

At the top of `app.py`, after the existing module imports (line 17, after `import summarizer`), add:

```python
import base64
import image_analyzer
import zip_extractor
```

- [ ] **Step 2: Update the file uploader to accept `.zip`**

Change line 81 from:

```python
    uploaded_file = st.file_uploader("Upload WhatsApp chat export (.txt)", type=["txt"])
```

to:

```python
    uploaded_file = st.file_uploader(
        "Upload WhatsApp export (.txt or .zip with media)", type=["txt", "zip"]
    )
```

- [ ] **Step 3: Replace the pipeline block with ZIP-aware routing**

Replace the entire `if analyze_btn:` block (lines 137–192) with:

```python
if analyze_btn:
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if tmdb_key:
        os.environ["TMDB_API_KEY"] = tmdb_key

    file_bytes = uploaded_file.read()
    is_zip = uploaded_file.name.lower().endswith(".zip")

    # ── ZIP extraction ────────────────────────────────────────────────────────
    image_map: dict[str, bytes] = {}
    if is_zip:
        _MAX_ZIP_BYTES = 50 * 1024 * 1024
        if len(file_bytes) > _MAX_ZIP_BYTES:
            st.error(
                f"ZIP file is {len(file_bytes) / 1024 / 1024:.1f} MB — limit is 50 MB. "
                "Export a smaller date range from WhatsApp."
            )
            st.stop()
        try:
            with st.spinner("Extracting chat and images from ZIP…"):
                chat_bytes, image_map = zip_extractor.extract(file_bytes)
        except ValueError as e:
            st.error(str(e))
            st.stop()
        cache_bytes = file_bytes  # cache key uses original ZIP bytes
    else:
        _MAX_TXT_BYTES = 5 * 1024 * 1024
        if len(file_bytes) > _MAX_TXT_BYTES:
            st.error(
                f"File is {len(file_bytes) / 1024 / 1024:.1f} MB — limit is 5 MB. "
                "Export a smaller date range from WhatsApp."
            )
            st.stop()
        chat_bytes = file_bytes
        cache_bytes = file_bytes

    try:
        cached_data, cache_key = cache.load(cache_bytes)
    except Exception as e:
        st.warning(f"Cache error: {e}. Running fresh analysis.")
        cached_data, cache_key = None, cache._key(cache_bytes)

    if cached_data:
        st.session_state["data"] = cached_data
        st.session_state["alias_map"] = cached_data.get("alias_map", {})
        st.session_state["cache_status"] = "Using cached analysis"
    else:
        st.session_state["cache_status"] = "Running fresh analysis…"
        with st.spinner("Parsing chat…"):
            messages, alias_map = parser.parse(chat_bytes)
            st.session_state["alias_map"] = alias_map

        with st.spinner(f"Analyzing {len(messages)} messages with AI (may take a minute)…"):
            try:
                raw = extractor.extract(messages)
            except ValueError as e:
                st.error(str(e))
                st.stop()

        with st.spinner("Building dashboard…"):
            data = aggregator.build(raw)

        with st.spinner("Fetching movie data from TMDB…"):
            canonical_titles = [m["title"] for m in data["movies"]]
            tmdb_data = enricher.enrich(canonical_titles)
            aggregator.attach_tmdb(data["movies"], tmdb_data)

        with st.spinner("Generating opinion summaries…"):
            summarizer.summarize(data["movies"])

        if image_map:
            with st.spinner(f"Analyzing {len(image_map)} images with AI…"):
                message_links = {
                    m["media_filename"]: {
                        "sender": m["sender"],
                        "text": m["text"],
                        "timestamp": str(m["timestamp"]) if m.get("timestamp") else None,
                    }
                    for m in messages
                    if m.get("media_filename")
                }
                try:
                    img_analysis = image_analyzer.analyze(image_map, message_links)

                    # Enrich any new movies discovered from images that aren't in the text extraction
                    existing_titles = {m["title"] for m in data["movies"]}
                    new_titles = [
                        t for t in {r["movie_title"] for r in img_analysis.values() if r.get("movie_title")}
                        if t and t not in existing_titles
                    ]
                    if new_titles:
                        new_tmdb = enricher.enrich(new_titles)
                        for title in new_titles:
                            data["movies"].append({
                                "title": title,
                                "tmdb": new_tmdb.get(title, enricher.empty_tmdb()),
                                "group_sentiment": "neutral",
                                "group_sentiment_score": 0.5,
                                "mention_count": 0,
                                "recommendations": 0,
                                "avoid_signals": 0,
                                "explicit_ratings": [],
                                "per_person": {},
                                "first_mentioned_at": None,
                                "timeline": [],
                                "shared_images": [],
                            })

                    aggregator.attach_images(data, img_analysis, image_map)
                except Exception as e:
                    st.warning(f"Image analysis failed: {e}. Continuing without media.")
                    data.setdefault("image_analysis", {"total_images": 0, "linked": 0, "unlinked": 0})
                    for m in data["movies"]:
                        m.setdefault("shared_images", [])
                    data.setdefault("unlinked_images", [])
        else:
            data["image_analysis"] = {"total_images": 0, "linked": 0, "unlinked": 0}
            for m in data["movies"]:
                m.setdefault("shared_images", [])
            data.setdefault("unlinked_images", [])

        data["alias_map"] = alias_map
        cache.save(cache_key, data)
        if name := session_name_input.strip():
            sessions.register(name, cache_key, len(data["movies"]), user_id)
        st.session_state["data"] = data
        st.session_state["cache_status"] = "Fresh analysis complete — cached for next time"
```

- [ ] **Step 4: Smoke test the app starts without errors**

```bash
streamlit run app.py --server.headless true &
sleep 3
curl -s http://localhost:8501 | grep -c "movieWiz" || true
kill %1
```

Expected: app starts, curl returns content containing "movieWiz"

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: wire ZIP upload routing and image analysis pipeline in app.py"
```

---

## Task 8: Add visualizations

**Files:**
- Modify: `app.py` (dashboard section — lines 212–423)

- [ ] **Step 1: Update the tab definition to add Media Gallery**

Change the `st.tabs` call (currently line 212) from:

```python
tab1, tab2, tab4, tab5, tab6 = st.tabs(
    ["Overview", "Movie Explorer", "Sentiment Deep Dive", "Timeline", "Actors & Directors"]
)
```

to:

```python
tab1, tab2, tab4, tab5, tab_media, tab6 = st.tabs(
    ["Overview", "Movie Explorer", "Sentiment Deep Dive", "Timeline", "Media Gallery", "Actors & Directors"]
)
```

- [ ] **Step 2: Add "Images Shared" KPI to Overview tab**

In the Overview tab block, change:

```python
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Movies Discussed", len(movies))
    col2.metric("People in Chat", len(people))
    col3.metric("Most Discussed", top_movie)
    col4.metric("Most Active", top_person)
```

to:

```python
    img_stats = data.get("image_analysis", {})
    total_images = img_stats.get("total_images", 0)

    if total_images > 0:
        col1, col2, col3, col4, col5 = st.columns(5)
        col5.metric("Images Shared", total_images)
    else:
        col1, col2, col3, col4 = st.columns(4)
    col1.metric("Movies Discussed", len(movies))
    col2.metric("People in Chat", len(people))
    col3.metric("Most Discussed", top_movie)
    col4.metric("Most Active", top_person)
```

- [ ] **Step 3: Add "Group Shared" image strip to Movie Explorer cards**

In the Movie Explorer tab, inside the `for i, movie in enumerate(movies):` loop, add the image strip after the `st.divider()` at the bottom of each card (before the closing `with cols[i % 3]:` block). Replace the `st.divider()` line with:

```python
            shared = movie.get("shared_images", [])
            if shared:
                with st.expander(f"📸 Group Shared ({len(shared)} images)"):
                    img_cols = st.columns(min(len(shared), 3))
                    for j, img_entry in enumerate(shared[:6]):
                        with img_cols[j % 3]:
                            b64 = img_entry.get("base64_thumbnail", "")
                            if b64:
                                                st.image(base64.b64decode(b64), use_container_width=True)
                            st.caption(
                                f"{img_entry.get('sender', '')} · "
                                f"{img_entry.get('emotion_label', '')}"
                            )
                            if ctx := img_entry.get("message_context"):
                                st.caption(f"*{ctx[:60]}*")

            st.divider()
```

- [ ] **Step 4: Add camera markers to the Timeline scatter plot**

In the Timeline tab, after the `df_timeline` DataFrame is built and before `fig5 = px.scatter(...)`, add image event rows. Replace the existing `fig5` scatter block with:

```python
        fig5 = px.scatter(
            df_timeline,
            x="timestamp",
            y="Movie",
            color="Movie",
            hover_data=["Sender", "Sentiment"],
            title="When Each Movie Was Discussed",
            height=max(400, len(movies) * 30),
        )
        fig5.update_traces(marker_size=10)

        # Overlay image share markers
        image_events = []
        for movie in movies:
            for img_entry in movie.get("shared_images", []):
                if img_entry.get("timestamp"):
                    image_events.append({
                        "timestamp": img_entry["timestamp"],
                        "Movie": movie["title"],
                        "Sender": img_entry.get("sender", ""),
                        "Emotion": img_entry.get("emotion_label", ""),
                    })
        for img_entry in data.get("unlinked_images", []):
            if img_entry.get("timestamp"):
                image_events.append({
                    "timestamp": img_entry["timestamp"],
                    "Movie": "Unlinked",
                    "Sender": img_entry.get("sender", ""),
                    "Emotion": img_entry.get("emotion_label", ""),
                })

        if image_events:
            df_imgs = pd.DataFrame(image_events)
            df_imgs["timestamp"] = pd.to_datetime(df_imgs["timestamp"], errors="coerce")
            df_imgs = df_imgs.dropna(subset=["timestamp"])
            if not df_imgs.empty:
                fig5.add_trace(
                    go.Scatter(
                        x=df_imgs["timestamp"],
                        y=df_imgs["Movie"],
                        mode="markers+text",
                        marker=dict(symbol="circle", size=14, color="white", line=dict(width=1, color="gray")),
                        text=["📷"] * len(df_imgs),
                        textposition="middle center",
                        hovertemplate="<b>Image shared</b><br>Sender: %{customdata[0]}<br>Emotion: %{customdata[1]}<extra></extra>",
                        customdata=df_imgs[["Sender", "Emotion"]].values,
                        name="Image shared",
                        showlegend=True,
                    )
                )

        st.plotly_chart(fig5, use_container_width=True)
```

- [ ] **Step 5: Implement the Media Gallery tab**

Add the following block after the Timeline tab and before the Actors & Directors tab:

```python
# ── Tab 5: Media Gallery ──────────────────────────────────────────────────────

with tab_media:
    st.header("Media Gallery")

    all_shared = []
    for movie in movies:
        for img_entry in movie.get("shared_images", []):
            all_shared.append({**img_entry, "_movie": movie["title"]})
    for img_entry in data.get("unlinked_images", []):
        all_shared.append({**img_entry, "_movie": None})

    if not all_shared:
        st.info("No images found. Upload a WhatsApp export ZIP with media to see images here.")
    else:
        # Filter pills
        movie_names_with_images = sorted(
            {e["_movie"] for e in all_shared if e["_movie"]},
            key=lambda t: sum(1 for e in all_shared if e["_movie"] == t),
            reverse=True,
        )
        filter_options = ["All"] + movie_names_with_images
        has_unlinked = any(e["_movie"] is None for e in all_shared)
        if has_unlinked:
            filter_options.append("Unlinked")

        selected_filter = st.selectbox(
            "Filter by movie",
            filter_options,
            label_visibility="collapsed",
        )

        if selected_filter == "All":
            filtered = all_shared
        elif selected_filter == "Unlinked":
            filtered = [e for e in all_shared if e["_movie"] is None]
        else:
            filtered = [e for e in all_shared if e["_movie"] == selected_filter]

        st.caption(f"Showing {len(filtered)} image(s)")

        cols = st.columns(3)
        for idx, img_entry in enumerate(filtered):
            with cols[idx % 3]:
                b64 = img_entry.get("base64_thumbnail", "")
                if b64:
                    st.image(base64.b64decode(b64), use_container_width=True)
                else:
                    st.markdown("🖼️ *No preview*")

                movie_label = img_entry["_movie"] or "Unlinked"
                st.caption(f"**{movie_label}**")
                if img_entry.get("sender"):
                    st.caption(f"{img_entry['sender']} · {img_entry.get('emotion_label', '')}")
                if ctx := img_entry.get("message_context"):
                    st.caption(f"*{ctx[:80]}*")
                st.divider()
```

- [ ] **Step 6: Run the full test suite one final time**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat: add media visualizations — Gallery tab, image strips, timeline markers, KPI"
```

---

## Final Verification Checklist

After all tasks complete, manually verify:

- [ ] Upload a plain `.txt` file → existing behavior unchanged, no media tab shown
- [ ] Upload a `.zip` with `_chat.txt` and images → image analysis runs, Media Gallery tab populated
- [ ] Upload a `.zip` > 50MB → error shown immediately
- [ ] Upload a `.zip` with no `.txt` → error shown
- [ ] Overview shows "Images Shared" KPI only when ZIP was uploaded
- [ ] Movie Explorer shows "Group Shared" expander only for movies with linked images
- [ ] Timeline shows 📷 markers for image share events
- [ ] Media Gallery filter pills work correctly
