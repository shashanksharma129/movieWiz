# Architecture

## Overview

movieWiz is a linear pipeline: each module has a single responsibility and a clean input/output contract. The Streamlit app (`app.py`) orchestrates the pipeline and owns all user interaction. All other modules are pure functions with no Streamlit dependency.

```
app.py
  ├── parser.py        bytes → (list[message], alias_map)
  ├── cache.py         bytes → cached result (or miss)
  ├── extractor.py     list[message] → raw extraction dict
  ├── aggregator.py    raw extraction → data model (no TMDB yet)
  ├── enricher.py      list[canonical_title] → TMDB metadata dict
  ├── aggregator.py    attach_tmdb() — merge TMDB into data model
  ├── summarizer.py    data["movies"] → per_person summaries in-place
  ├── cache.py         data model → .cache/<hash>.json
  └── sessions.py      named session registry → .cache/sessions.json
```

---

## Module Descriptions

### `parser.py`

Converts raw WhatsApp `.txt` bytes into a list of structured message dicts and a phone-number alias map.

**Handles:**
- Android format: `DD/MM/YYYY, HH:MM - Name: message`
- iOS format: `[DD/MM/YYYY, HH:MM:SS] Name: message`
- 12-hour (AM/PM) and 24-hour timestamp formats
- 2-digit and 4-digit years
- Multi-line messages (continuation lines without a timestamp header)
- System messages (two separate regexes):
  - `_SYSTEM_TEXT_RE` — exact phrases matched against message text: `<Media omitted>`, deleted messages, encryption notice
  - `_SYSTEM_SENDER_RE` — membership/event patterns matched against sender only: join/leave events, group changes. Kept separate to avoid false-positives on user messages like "I added Dune to my watchlist"
- **PII aliasing** — sender names matching `_PHONE_RE` (`^\+?[0-9][\d\s\-(). ]{6,}$`) are replaced with stable labels ("Contact 1", "Contact 2") in first-appearance order. The original number → label mapping is returned as `alias_map`

**Return type:**
```python
def parse(file_bytes: bytes) -> tuple[list[dict], dict[str, str]]:
    # list[dict]: [{"timestamp": datetime | None, "sender": str, "text": str}, ...]
    # dict[str, str]: {"+91 98765 43210": "Contact 1", ...}
```

**Design note:** File decoded as UTF-8 (with `errors="replace"` fallback), never written to disk.

---

### `cache.py`

Versioned MD5-keyed JSON cache to avoid re-running the pipeline on the same chat file.

- **Key:** `MD5(file_bytes + _CACHE_VERSION.encode())` — mixing in the version string means bumping `_CACHE_VERSION` invalidates all prior entries without deleting files
- **Storage:** `.cache/<hash>.json` relative to the module's directory (`Path(__file__).parent`)
- **Hit:** Returns the full aggregated data dict; pipeline short-circuits
- **Miss:** Returns `None`; pipeline runs, then calls `cache.save()`
- **Corruption handling:** `(json.JSONDecodeError, OSError)` → delete corrupt file, return miss
- **`load_by_key(key)`** — loads by known key directly (used by `sessions.py` without needing the original file bytes)
- **Serialization:** `json.dump(default=str)` handles `datetime` objects by converting to ISO strings

**Current version:** `_CACHE_VERSION = "v2"` (bump this on any breaking pipeline change)

---

### `extractor.py`

Sends chat messages to Claude Sonnet 4.6 in batches and extracts structured movie data.

**Chunking strategy:** Messages split into chunks of 100. Each chunk is one API call. Balances token limits against conversational context.

**Prompt caching:** System prompt marked with `cache_control: {type: "ephemeral"}`. Since the prompt is identical across all chunks in a run, chunks 2–N hit the cache. Reduces input token cost ~90% on the cached portion.

**System prompt design:** Explicitly lists Hinglish slang mappings:
- Positive: "mast tha", "solid hai", "ekdum zabardast", "paisa vasool"
- Negative: "bakwaas tha", "bekar hai", "faltu"
- Recommend: "must watch bhai", "dekh le yaar"
- Avoid: "mat dekh", "skip kar", "waste hai"

**Error handling:** Each chunk is wrapped in try/except — a failing chunk logs a warning and returns empty results rather than aborting the pipeline.

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

---

### `enricher.py`

Fetches movie metadata from the TMDB API for each unique canonical title.

**Concurrency:** Uses `ThreadPoolExecutor(max_workers=5)` — all TMDB calls run concurrently. For 20 movies (40 requests total), this reduces wall time from ~20s to ~5s.

**Per title, two TMDB calls:**
1. `GET /search/movie?query=<title>` — best match, basic data
2. `GET /movie/<id>` — genre list (not returned by search)

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

**Graceful degradation:** Missing TMDB key or unfound title → `_empty_tmdb()` dict with all-null fields. Dashboard shows "No poster" placeholder — never crashes on missing data.

---

### `aggregator.py`

Two-phase module: `build()` finalizes the data model from raw LLM extraction; `attach_tmdb()` merges TMDB data in-place after enrichment. The split ensures TMDB is always queried against canonical titles (post-dedup), not raw LLM titles.

**Title deduplication (fuzzy matching):** Same movie as "Dune Part Two", "Dune 2", "dune part 2" → grouped under one canonical title via `thefuzz` with similarity threshold ≥ 80. First occurrence wins as canonical.

**Sentiment aggregation:** Average of all mention `sentiment_score` values:
- ≥ 0.65 → `"positive"`
- ≤ 0.35 → `"negative"`
- Otherwise → `"mixed"`

**Per-person data:** Each sender ends up with dominant sentiment, up to N raw quotes, and any explicit rating.

**`attach_tmdb(movies, tmdb_data)`:** Iterates the already-built movies list and sets `movie["tmdb"]` from the TMDB result dict. Falls back to `_empty_tmdb()` for any title not in the TMDB result.

---

### `summarizer.py`

Generates a 1–2 sentence natural-language opinion summary for each person who discussed each movie. Adds `per_person[sender]["summary"]` to each movie in-place.

**One LLM call per movie.** User message format:
```
Movie: "Dune: Part Two"

Rahul | sentiment: positive | rating: 9/10 | quotes: ["ekdum zabardast tha", "must watch bhai"]
Priya | sentiment: mixed | rating: null | quotes: ["first half slow tha but second half mast tha"]
```

**Response:** `{"Rahul": "Rahul loved Dune: Part Two…", "Priya": "Priya had mixed feelings…"}`

**System prompt** uses `cache_control: ephemeral` — cached across all movie calls in a single run.

**Skips** movies where all `per_person` entries have empty quotes and neutral/null sentiment (nothing meaningful to summarize).

**Error handling:** Per-movie try/except — a failure leaves `summary: None` for that movie's people and logs a warning.

---

### `sessions.py`

Manages a named session registry at `.cache/sessions.json`. Enables returning users to reload a past analysis without re-uploading or re-running the pipeline.

**Registry format:**
```json
{
  "sessions": [
    {
      "name": "Friends group chat",
      "cache_key": "abc123...",
      "created_at": "2025-01-15T10:30:00",
      "movie_count": 12
    }
  ]
}
```

**Public API:**
- `list_sessions()` → all sessions, newest first
- `register(name, cache_key, movie_count)` → add/overwrite by name
- `load_by_name(name)` → reads the full data dict via `cache.load_by_key()`; returns `None` if cache file is missing
- `delete(name)` → removes registry entry (cache file stays on disk)

---

### `app.py`

Streamlit entry point. Orchestrates the pipeline and renders the dashboard.

**Sidebar structure:**
1. **Saved Sessions** (shown only if sessions exist) — selectbox + Load/Delete buttons
2. **New Analysis** — file uploader, API key inputs, optional session name, Analyze button, Clear-all-caches button

**Session load path:** `sessions.load_by_name()` → sets `st.session_state["data"]` and `st.session_state["alias_map"]` → `st.rerun()`

**Pipeline path (cache miss):** `parser.parse` → `extractor.extract` → `aggregator.build` → `enricher.enrich` + `aggregator.attach_tmdb` → `summarizer.summarize` → embed `alias_map` in data → `cache.save` → optional `sessions.register`

**Tab summary:**

| Tab | What it shows |
|---|---|
| Overview | KPI metrics, top movies bar chart, phone-number alias expander |
| Movie Explorer | Card grid with TMDB poster, AI opinion summary per person, raw quotes (collapsed) |
| Sentiment Deep Dive | Stacked bar chart per movie + sortable summary table |
| Timeline | Scatter plot and daily density line chart of movie discussions |
| Actors & Directors | Table of mentioned actors/directors + context quote expanders |

---

## Data Flow Diagram

```
User uploads chat.txt (in-memory bytes)
         │
         ▼
  MD5(bytes + version) ──── cache hit? ──► load .cache/<hash>.json ──► Dashboard
         │                                                                   ▲
         │ miss                                                              │
         ▼                                                                   │
  parser.parse()                                                             │
  ([messages...], alias_map)                                                 │
         │                                                                   │
         ▼                                                                   │
  extractor.extract()  (N chunks × 1 Claude API call)                       │
  {"movies": [...], "actors_directors": [...]}                               │
         │                                                                   │
         ▼                                                                   │
  aggregator.build()                                                         │
  {"movies": [...tmdb:{}...], "people": {...}, "actors_directors": [...]}    │
         │                                                                   │
         ├─── canonical titles ──► enricher.enrich()  [ThreadPoolExecutor]  │
         │                          {title: tmdb_data, ...}                 │
         │                                  │                               │
         │                                  ▼                               │
         │                         aggregator.attach_tmdb()                 │
         │                                                                   │
         ▼                                                                   │
  summarizer.summarize()  (1 Claude call per movie)                         │
  [adds per_person[*]["summary"] in-place]                                  │
         │                                                                   │
         ▼                                                                   │
  data["alias_map"] = alias_map                                              │
  cache.save()  →  .cache/<hash>.json ──────────────────────────────────────┘
         │
         ▼
  sessions.register()  (if user gave a session name)
  →  .cache/sessions.json
```

---

## Design Decisions

**Why Claude Sonnet 4.6 and not Haiku?**
Hinglish entity extraction requires strong multilingual understanding — Haiku is too weak for reliable extraction from transliterated Hindi. Sonnet 4.6 delivers the right quality at reasonable cost. The same model is used for summarization for consistency.

**Why not use the Anthropic structured outputs API?**
Prompt-based JSON with the `{...}` fallback parser is already highly reliable with Sonnet 4.6 and adds no latency overhead. Structured outputs would guarantee schema compliance but add per-request overhead in a pipeline that's already chunked. Worth revisiting if JSON parse failures become frequent.

**Why MD5 and not SHA256 for cache keys?**
MD5 is fast and collision probability is negligible for a local file cache keying on ~50 KB files. This is not a security use case.

**Why split `aggregator.build()` from `aggregator.attach_tmdb()`?**
TMDB enrichment takes canonical titles as input. If TMDB was called before aggregation, it would receive raw LLM titles (e.g. "Dune 2", "dune part two") and miss the canonical key ("Dune: Part Two"). Splitting ensures enrichment always runs against the deduplicated canonical titles.

**Why concurrent TMDB calls?**
With 20 movies requiring 40 requests, sequential calls take ~20s. `ThreadPoolExecutor(max_workers=5)` reduces this to ~5s with no complexity tradeoff for a read-only API.

**Why store `alias_map` inside the cached data dict?**
`alias_map` is needed by the UI to show the "N phone numbers anonymised" expander. Without embedding it in the cache, it would be lost on session reload or cache hit. Storing it as `data["alias_map"]` means it travels with the data transparently — `json.dump(default=str)` handles it for free.
