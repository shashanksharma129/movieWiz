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
