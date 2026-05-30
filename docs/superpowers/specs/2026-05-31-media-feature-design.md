# Media Feature Design

**Date:** 2026-05-31
**Status:** Approved

## Summary

Add ZIP file upload support to movieWiz. Users can now upload a WhatsApp export ZIP (containing the chat `.txt` and media files). The app extracts images, runs a two-pass Claude vision analysis alongside the existing text pipeline, and surfaces media in four updated/new visualizations.

Audio and video files are explicitly excluded — only images are processed, keeping token costs low. Audio transcription is a future follow-up.

---

## Scope

**In scope:**
- ZIP file upload (alongside existing `.txt` support — no regression)
- Image extraction from ZIP (JPEG, PNG, WebP, GIF only; all other file types discarded)
- Linking extracted images to chat messages by filename
- Two-pass Claude vision analysis: movie identification + emotion labeling
- Four visualization changes (one new tab, three enhanced existing tabs)
- Cache version bump to `v3`

**Out of scope:**
- Audio transcription (`.opus`, `.mp3`) — deferred
- Video analysis (`.mp4`, `.3gp`) — deferred
- ZIP files larger than 50MB (explicitly unsupported; enforce with an error)

---

## Architecture

### Pipeline (updated)

```
ZIP upload → zip_extractor.py → {chat.txt bytes, image_map {filename → bytes}}
                                      ↓
                    existing pipeline unchanged:
                    parser → extractor → aggregator → enricher → summarizer
                                      ↓
                         image_analyzer.py (two-pass Claude vision)
                                      ↓
                         aggregator.attach_images() → enriched data model
                                      ↓
                              cache v3 (.cache/<hash>.json)
```

`.txt` uploads bypass `zip_extractor.py` entirely and run the existing pipeline unchanged.

### New / Changed Files

| File | Change |
|------|--------|
| `zip_extractor.py` | New. Unzips, finds `_chat.txt`, whitelists images, returns `{filename → bytes}` map |
| `image_analyzer.py` | New. Two-pass Claude vision analysis |
| `parser.py` | Minor update: tag messages that reference a media filename |
| `aggregator.py` | Add `attach_images()` method |
| `cache.py` | Bump version string from `"v2"` to `"v3"` |
| `app.py` | Accept `.zip` uploads, wire new modules, new visualizations |

---

## Module Designs

### `zip_extractor.py`

**Responsibility:** Unzip the WhatsApp export and produce a clean `{filename → bytes}` image map.

**Contract:**
```python
def extract(zip_bytes: bytes) -> tuple[bytes, dict[str, bytes]]:
    """
    Returns (chat_txt_bytes, image_map).
    Raises ValueError if no chat .txt found or ZIP > 50MB.
    Silently discards non-image files (audio, video, documents).
    """
```

**Allowed image extensions:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`

**ZIP size limit:** 50MB enforced before extraction begins.

**Chat file detection:** Looks for `_chat.txt` first, then any `.txt` file in the ZIP root. Raises `ValueError` if none found.

---

### `image_analyzer.py`

**Responsibility:** Two-pass Claude vision analysis of extracted images.

**Pass 1 — Movie identification:**
- Images batched in groups of 5
- Each batch sent to `claude-sonnet-4-6` with the message context (sender + text) for linked messages
- Prompt asks: does any image show a movie poster, title card, or recognizable film scene?
- Returns `{filename → movie_title | None}`

**Pass 2 — Emotion labeling:**
- Each image sent individually with its message context
- Returns one label from: `positive`, `neutral`, `negative`, `funny/meme`, `informational`
- Uses the same batching approach (5 per call) for efficiency

**`ImageAnalysisResult` type:**
```python
class ImageAnalysisResult(TypedDict):
    filename: str
    movie_title: str | None      # None if no movie detected
    emotion_label: str           # positive | neutral | negative | funny/meme | informational
    sender: str | None
    timestamp: str | None
    message_context: str | None
```

**Contract:**
```python
def analyze(
    image_map: dict[str, bytes],
    message_links: dict[str, dict],  # {filename → {sender, text, timestamp}}
) -> dict[str, ImageAnalysisResult]:
    """
    Returns per-filename analysis results.
    Skips images that fail silently (same pattern as extractor.py).
    """
```

**Token budget (500 images worst case):**
- Pass 1: 100 batches × ~5500 tokens = ~550K tokens
- Pass 2: 100 batches × ~5500 tokens = ~550K tokens
- Total: ~1.1M tokens — cached after first run

---

### `parser.py` update

When a message body matches the pattern `\S+\.(jpg|jpeg|png|webp|gif|mp4|opus|pdf)\s*(\(file attached\))?`, tag the parsed message with `media_filename: str`. This enables `zip_extractor` and `image_analyzer` to join images to messages by filename.

---

### `aggregator.py` — `attach_images()`

New method merges image analysis results into the existing movie data:

```python
def attach_images(
    data: dict,
    analysis: dict[str, ImageAnalysisResult],
    image_map: dict[str, bytes],
) -> dict:
    """
    For each image linked to a movie, appends a SharedImage entry
    to data["movies"][title]["shared_images"].
    Images with no movie link go into data["unlinked_images"].
    Thumbnails resized to 200px width before base64 encoding.
    """
```

---

## Data Model (cache v3)

New fields added to the existing cache JSON:

```json
{
  "movies": {
    "Dune: Part Two": {
      "...existing fields...",
      "shared_images": [
        {
          "filename": "IMG-20240115-WA0001.jpg",
          "sender": "Rahul",
          "timestamp": "2024-01-15T10:30:00",
          "message_context": "ekdum zabardast tha",
          "emotion_label": "positive",
          "base64_thumbnail": "<200px-width resized JPEG as base64>"
        }
      ]
    }
  },
  "image_analysis": {
    "total_images": 147,
    "linked": 89,
    "unlinked": 58
  },
  "unlinked_images": [
    {
      "filename": "IMG-20240117-WA0012.jpg",
      "sender": "Amit",
      "timestamp": "2024-01-17T14:22:00",
      "message_context": "haha dekho",
      "emotion_label": "funny/meme",
      "base64_thumbnail": "..."
    }
  ]
}
```

**Cache version:** `"v3"` — invalidates all existing `v2` caches on upgrade (expected, by design).

---

## Upload UX

The sidebar `st.file_uploader` accepts both `.txt` and `.zip`:

```python
st.file_uploader("Upload WhatsApp export", type=["txt", "zip"])
```

- **`.txt` uploaded:** existing pipeline runs unchanged (no regression)
- **`.zip` uploaded:** full media pipeline runs; a `st.progress` bar shows the additional image analysis step
- **ZIP > 50MB:** error shown immediately, pipeline aborted
- **ZIP with no chat `.txt`:** error shown, pipeline aborted

---

## Visualizations

### Tab 1 — Overview (updated)
Add a 5th KPI metric card: **"Images Shared"** showing `image_analysis.total_images`. Only shown when a ZIP was uploaded; hidden for `.txt` uploads.

### Tab 2 — Movie Explorer (updated)
Each movie card gains a **"Group Shared"** section below the existing per-person opinions expander. Shows a horizontal thumbnail strip of up to 6 images linked to that movie, with sender name and message snippet. Only rendered if `shared_images` is non-empty.

### Tab 4 — Timeline (updated)
The existing scatter plot gains a second marker type: camera emoji (📷) at the timestamp of each image share, colored by `emotion_label`. Hover tooltip shows sender name and emotion label (Plotly does not support image thumbnails in tooltips). Degrades gracefully if no images present.

### Tab 5 — Media Gallery (new tab)
New tab inserted after Timeline, before Actors & Directors (which becomes Tab 6).

**Layout:**
- Filter pill row: "All Movies" + one pill per movie that has linked images + "Unlinked"
- Masonry-style 3-column grid of image cards
- Each card: thumbnail, movie badge (or "Unlinked"), sender name, date, message snippet
- Clicking a card expands it to full-size image with full message context

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| ZIP > 50MB | Immediate error, pipeline aborted |
| No `.txt` in ZIP | Error shown, pipeline aborted |
| Image fails to decode | Silently skipped, counted in a `skipped_images` field |
| Claude vision call fails | Image skipped (same pattern as `extractor.py` chunk failures) |
| TMDB lookup fails for image-discovered movie | Falls back to `empty_tmdb()` (same as existing) |

---

## Dependencies

No new external dependencies required. Thumbnail resizing uses Python's built-in `PIL`/`Pillow` (already available in most Python environments — add to `pyproject.toml` if not present). ZIP handling uses Python's built-in `zipfile` module.

Optional future dependency: `faster-whisper` for audio transcription (deferred).
