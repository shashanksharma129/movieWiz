# Architecture

## Overview

movieWiz is a linear pipeline: each module has a single responsibility and a clean input/output contract. The Streamlit app (`app.py`) orchestrates the pipeline and owns all user interaction. All other modules are pure functions with no Streamlit dependency.

```
app.py
  ├── parser.py       bytes → list[message]
  ├── cache.py        bytes → cached result (or miss)
  ├── extractor.py    list[message] → raw extraction dict
  ├── enricher.py     list[title] → TMDB metadata dict
  ├── aggregator.py   (raw extraction, TMDB data) → final data model
  └── cache.py        final data model → .cache/<md5>.json
```

---

## Module Descriptions

### `parser.py`

Converts raw WhatsApp `.txt` bytes into a list of structured message dicts.

**Handles:**
- Android format: `DD/MM/YYYY, HH:MM - Name: message`
- iOS format: `[DD/MM/YYYY, HH:MM:SS] Name: message`
- 12-hour (AM/PM) and 24-hour timestamp formats
- 2-digit and 4-digit years
- Multi-line messages (continuation lines without a timestamp header)
- System messages (filtered out): join/leave events, encryption notice, `<Media omitted>`, deleted messages

**Output per message:**
```python
{"timestamp": datetime | None, "sender": str, "text": str}
```

**Design note:** The file is decoded as UTF-8 (with `errors="replace"` fallback) and never written to disk — it stays in memory throughout the pipeline.

---

### `cache.py`

Provides a simple MD5-keyed JSON cache to avoid re-running expensive LLM calls on the same chat file.

- **Key:** MD5 hash of the raw file bytes (not the filename — the content)
- **Storage:** `.cache/<md5>.json` relative to the working directory
- **Hit:** Returns the full aggregated data dict; the pipeline short-circuits
- **Miss:** Returns `None`; pipeline runs normally, then calls `cache.save()`
- **Serialization:** `json.dump(default=str)` handles `datetime` objects by converting them to ISO strings

**Why MD5?** It's fast and collision-resistant enough for a local file cache. This is not a security use case.

---

### `extractor.py`

Sends chat messages to Claude Sonnet 4.6 in batches and extracts structured movie data.

**Chunking strategy:** Messages are split into chunks of 50. Each chunk is one API call. This balances:
- Staying well within token limits per request
- Giving Claude enough context to understand conversational references ("that movie", "the one you mentioned")

**Prompt caching:** The system prompt is marked with `cache_control: {type: "ephemeral"}`. Since the system prompt is large and identical across all chunks in a run, subsequent chunks hit the cache after the first. This reduces cost by ~90% on the cached portion.

**System prompt design:** The prompt explicitly lists Hinglish slang for positive, negative, recommendation, and avoid signals. This is necessary because standard sentiment models fail on transliterated Hindi. Example mappings:
- "bakwaas tha" → negative
- "mast tha" → positive
- "must watch bhai" → recommended
- "skip kar" → avoid

**Output schema (per chunk):**
```json
{
  "movies": [{
    "title": "normalized English title",
    "mentioned_by": "sender name",
    "timestamp": "ISO string or null",
    "sentiment": "positive|negative|mixed|neutral",
    "sentiment_score": 0.0–1.0,
    "explicit_rating": "8/10 or null",
    "recommendation_signal": "recommended|avoid|neutral",
    "raw_quote": "exact message snippet"
  }],
  "actors_directors": [{
    "name": "...", "role": "actor|director|unknown",
    "mentioned_by": "...", "context": "...", "associated_movie": "..."
  }]
}
```

**JSON parsing:** The response text is parsed with `json.loads()`. If that fails (model added preamble), a fallback locates the outermost `{...}` block. If both fail, the chunk returns empty results rather than crashing.

---

### `enricher.py`

Fetches movie metadata from the TMDB API for each unique title extracted.

**Per title, two TMDB calls:**
1. `GET /search/movie?query=<title>` — find the best match, get basic data
2. `GET /movie/<id>` — get genre list (not in search results)

**Returns per title:**
```python
{
  "tmdb_id": int,
  "poster_url": "https://image.tmdb.org/t/p/w500/...",
  "genres": ["Action", "Drama"],
  "year": "2024",
  "tmdb_score": 7.4,
  "overview": "...",
}
```

**Graceful degradation:** If the TMDB key is missing or a title isn't found, an `_empty_tmdb()` dict is returned. The dashboard shows "No poster" placeholders — it never crashes on missing data.

---

### `aggregator.py`

Merges the raw LLM extraction with TMDB metadata into the final data model.

**Title deduplication (fuzzy matching):** The same movie can appear as "Dune Part Two", "Dune 2", "dune part 2" across different messages and LLM normalizations. `thefuzz` is used to group titles with a similarity score ≥ 80 under a single canonical title (the first occurrence wins).

**Sentiment aggregation:** Each mention carries a `sentiment_score` (0.0–1.0). Group sentiment is computed as the average:
- ≥ 0.65 → positive
- ≤ 0.35 → negative
- Otherwise → mixed

**Per-person data:** For each canonical movie, all mentions are grouped by sender. Each person ends up with their dominant sentiment, up to 3 quotes, and any explicit rating they gave.

**Timeline:** All mentions with timestamps are collected into a chronological list for visualization.

---

### `app.py`

Streamlit entry point. Owns:
- File upload (in-memory only — never written to disk)
- API key inputs (sidebar, masked)
- Pipeline orchestration (spinner feedback at each stage)
- Session state for persisting analysis results across rerenders
- Five dashboard tabs

**Tab summary:**

| Tab | What it shows |
|---|---|
| Overview | KPI metrics + top movies by mention count (bar chart) |
| Movie Explorer | Card grid with TMDB poster, per-person opinions (expandable) |
| Who Talks Most | Bar charts: movie messages per person, unique movies per person |
| Sentiment Deep Dive | Stacked bar chart per movie + sortable summary table |
| Timeline | Scatter plot and daily density line chart of movie discussions |

---

## Data Flow Diagram

```
User uploads chat.txt (in-memory bytes)
         │
         ▼
  MD5 hash ──── cache hit? ───► load .cache/<hash>.json ──► Dashboard
         │                                                        ▲
         │ miss                                                   │
         ▼                                                        │
  parser.parse()                                                  │
  [{"timestamp": dt, "sender": str, "text": str}, ...]           │
         │                                                        │
         ▼                                                        │
  extractor.extract()  (N chunks × 1 Claude API call)            │
  {"movies": [...], "actors_directors": [...]}                    │
         │                                                        │
         ├─── unique titles ──► enricher.enrich()                │
         │                      {title: tmdb_data, ...}          │
         │                              │                         │
         ▼                              ▼                         │
  aggregator.build(raw, tmdb_data)                               │
  {"movies": [...], "people": {...}, "actors_directors": [...]}  │
         │                                                        │
         ▼                                                        │
  cache.save()  →  .cache/<hash>.json ───────────────────────────┘
```

---

## Design Decisions

**Why Claude Sonnet 4.6 and not Haiku?**
Hinglish entity extraction requires strong multilingual understanding and contextual reasoning — Haiku is too weak for reliable extraction. Sonnet 4.6 delivers the right quality at reasonable cost.

**Why not use the Anthropic structured outputs API?**
Structured outputs (`output_config.format`) would guarantee JSON schema compliance. We use prompt-based JSON instead because the system prompt + JSON schema instruction is already highly reliable with Sonnet 4.6, and structured outputs add latency overhead for a pipeline that's already chunked. This is a trade-off worth revisiting if JSON parse failures become frequent.

**Why MD5 and not SHA256 for cache keys?**
MD5 is fast and collision probability is negligible for a local cache keying on ~50 KB files. SHA256 would be marginally safer but adds no practical benefit here.

**Why sequential TMDB calls and not concurrent?**
Simplicity. For a personal tool analyzing one chat at a time with typically 10–30 unique movies, sequential requests complete in under 30 seconds. Concurrency adds complexity (thread safety, rate limit coordination) that isn't warranted yet.
