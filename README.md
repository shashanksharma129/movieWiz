# movieWiz

An AI-powered tool that turns your WhatsApp movie group chat into an interactive analytics dashboard. Upload a chat export, and movieWiz extracts every movie discussed, infers sentiments from Hinglish conversations, generates per-person opinion summaries, fetches posters and metadata from TMDB, and visualizes it all across a five-tab dashboard.

---

## Features

- **Hinglish-aware extraction** — understands "mast tha", "bakwaas tha", "must watch bhai" and similar expressions using Claude Sonnet 4.6
- **AI opinion summaries** — synthesizes each person's quotes and sentiment into a 1–2 sentence natural-language opinion per movie
- **PII protection** — phone numbers used as WhatsApp sender names are detected and replaced with stable aliases ("Contact 1", "Contact 2") before reaching any LLM or UI
- **Per-person attribution** — tracks who said what about which movie, with explicit rating capture (e.g. "8/10")
- **TMDB enrichment** — auto-fetches posters, genres, release year, and TMDB score for every identified movie (concurrent requests)
- **Sentiment analysis** — positive / mixed / negative classification per movie and per person
- **Recommendation signals** — identifies "must watch" vs "avoid karo" signals
- **Named sessions** — save analyses by name (e.g. "Friends group chat") and reload them instantly without re-uploading or re-running the pipeline
- **Versioned cache** — results cached locally; cache version string invalidates stale entries when the pipeline changes
- **Five-tab Streamlit dashboard**: Overview, Movie Explorer, Sentiment Deep Dive, Timeline, Actors & Directors

---

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/) (Claude Sonnet 4.6)
- A [TMDB API key](https://www.themoviedb.org/settings/api) (free)

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url> && cd movieWiz

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. Configure API keys
cp .env.example .env
# Edit .env and fill in ANTHROPIC_API_KEY and TMDB_API_KEY

# 5. Run the app
streamlit run app.py
```

You can also enter API keys directly in the Streamlit sidebar — no `.env` file required.

---

## How to Export Your WhatsApp Chat

**Android:**
Open the group chat → ⋮ (three dots) → More → Export chat → Without media → Save/share the `.txt` file

**iOS:**
Open the group chat → Tap the group name → Export Chat → Without Media → Save/share the `.txt` file

---

## Usage

1. Open the app at `http://localhost:8501`
2. Upload your `.txt` chat export using the sidebar file uploader
3. (Optional) Enter a session name, e.g. "Friends group chat"
4. Click **Analyze Chat**
5. Wait ~1–3 minutes for the first run (LLM extraction + summaries + TMDB lookups)
6. On return visits, pick a saved session from the sidebar and click **Load** — instant, no LLM costs

---

## Pipeline

```
Upload .txt
    │
    ▼
parser.py       Parse messages, detect + alias phone-number senders, filter system events
    │
    ▼
cache.py        Version-aware MD5 check — skip LLM on cache hit
    │ (miss)
    ▼
extractor.py    Claude Sonnet 4.6, chunked in batches of 100 messages
                Prompt caching on system prompt reduces cost on repeat runs
    │
    ▼
aggregator.py   Fuzzy-dedup titles, merge per-person data, compute group sentiment
                (TMDB data not yet attached — canonical titles finalized here)
    │
    ├── canonical titles ──► enricher.py    Concurrent TMDB Search + Details per movie
    │                                        {title: tmdb_data, ...}
    │                              │
    │                              ▼
    │                       aggregator.attach_tmdb()
    │
    ▼
summarizer.py   One Claude call per movie — synthesizes per-person opinion summaries
    │
    ▼
cache.py        Save result (including alias_map + summaries) to .cache/<hash>.json
    │
    ▼
sessions.py     Register under user-provided name in .cache/sessions.json (if named)
    │
    ▼
app.py          Render 5-tab Streamlit dashboard
```

---

## Project Structure

```
movieWiz/
├── app.py              Main Streamlit dashboard (5 tabs + session sidebar)
├── parser.py           WhatsApp .txt parser (Android + iOS formats, PII aliasing)
├── extractor.py        LLM entity extraction via Anthropic SDK
├── enricher.py         Concurrent TMDB API enrichment
├── aggregator.py       Data aggregation and fuzzy title deduplication
├── summarizer.py       Per-person opinion summarization via Claude
├── cache.py            Versioned MD5-keyed local JSON cache
├── sessions.py         Named session registry (.cache/sessions.json)
├── pyproject.toml
├── .env.example        API key template
├── .gitignore
├── docs/
│   ├── architecture.md     Detailed module and data flow documentation
│   ├── data-model.md       JSON schema of the aggregated output
│   └── api-keys.md         Guide to obtaining required API keys
└── .cache/             Auto-created, gitignored — stores analysis results + session index
```

---

## Tech Stack

| Component | Library |
|---|---|
| LLM extraction + summaries | `anthropic` — Claude Sonnet 4.6 |
| Dashboard | `streamlit` |
| Charts | `plotly` |
| Data wrangling | `pandas` |
| Movie metadata | TMDB API via `requests` |
| Fuzzy title matching | `thefuzz` |
| Config | `python-dotenv` |

---

## Cost Estimate

A typical <50 KB chat (~2,000 messages, ~20 unique movies) costs roughly **$0.10–$0.25** per fresh analysis with Claude Sonnet 4.6:

- **Extraction:** ~$0.05–$0.15 (chunked message processing; prompt caching reduces repeat-run cost ~90%)
- **Summarization:** ~$0.02–$0.05 (one call per movie)

The versioned local cache means you only pay LLM costs once per unique chat file per cache version. Named sessions let you reload past analyses with zero LLM cost.

---

## Docs

- [Architecture](docs/architecture.md) — module design, data flow, and key design decisions
- [Data Model](docs/data-model.md) — full JSON schema of the aggregated output
- [API Keys](docs/api-keys.md) — step-by-step guide to getting your Anthropic and TMDB keys

---

## Roadmap

- [ ] Retry / backoff on Anthropic and TMDB transient failures
- [ ] Parallel summarizer calls (currently sequential per movie)
- [ ] Upload size guard with user-visible warning
- [ ] Unit tests for `parser.py` (regex-heavy, easy to regress)
- [ ] Genre-based filtering in Movie Explorer
- [ ] Multiple chat files — merge analysis across different groups
- [ ] Media export support — process shared movie clip thumbnails
- [ ] Public deployment with authentication layer
