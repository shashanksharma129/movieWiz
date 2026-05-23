# movieWiz

An AI-powered tool that turns your WhatsApp movie group chat into an interactive analytics dashboard. Upload a chat export, and movieWiz extracts every movie discussed, infers sentiments from Hinglish conversations, fetches posters and metadata from TMDB, and visualizes it all across five tabs.

---

## Features

- **Hinglish-aware extraction** — understands "mast tha", "bakwaas tha", "must watch bhai" and similar expressions using Claude Sonnet 4.6
- **Per-person attribution** — tracks who said what about which movie
- **TMDB enrichment** — auto-fetches posters, genres, release year, and TMDB score for every identified movie
- **Sentiment analysis** — positive / mixed / negative classification per movie and per person, with explicit rating capture (e.g. "8/10")
- **Recommendation signals** — identifies "must watch" vs "avoid karo" signals
- **MD5 caching** — results are cached locally so re-opening the same chat skips all LLM calls
- **Five-tab Streamlit dashboard**: Overview, Movie Explorer, Who Talks Most, Sentiment Deep Dive, Timeline

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
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and fill in ANTHROPIC_API_KEY and TMDB_API_KEY

# 5. Run the app
streamlit run app.py
```

You can also enter API keys directly in the Streamlit sidebar without a `.env` file.

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
3. Click **Analyze Chat**
4. Wait ~1–2 minutes for the first run (LLM extraction + TMDB lookups)
5. Subsequent runs on the same file are instant (local cache hit)

---

## Pipeline

```
Upload .txt
    │
    ▼
parser.py       Parse messages, filter system events, handle multi-line
    │
    ▼
cache.py        MD5 check — skip LLM on cache hit
    │ (miss)
    ▼
extractor.py    Claude Sonnet 4.6, chunked in batches of 50 messages
                Prompt caching on system prompt reduces cost on repeat runs
    │
    ▼
aggregator.py   Fuzzy-dedup titles, merge per-person data, compute group sentiment
    │
    ▼
enricher.py     TMDB Search + Details API per unique movie
    │
    ▼
cache.py        Save result to .cache/<md5>.json
    │
    ▼
app.py          Render 5-tab Streamlit dashboard
```

---

## Project Structure

```
movieWiz/
├── app.py              Main Streamlit dashboard (5 tabs)
├── parser.py           WhatsApp .txt parser (Android + iOS formats)
├── extractor.py        LLM entity extraction via Anthropic SDK
├── enricher.py         TMDB API enrichment
├── aggregator.py       Data aggregation and fuzzy title deduplication
├── cache.py            MD5-keyed local JSON cache
├── requirements.txt
├── .env.example        API key template
├── .gitignore
├── docs/
│   ├── architecture.md     Detailed module and data flow documentation
│   ├── data-model.md       JSON schema of the aggregated output
│   └── api-keys.md         Guide to obtaining required API keys
└── .cache/             Auto-created, gitignored — stores analysis results
```

---

## Tech Stack

| Component | Library |
|---|---|
| LLM extraction | `anthropic` — Claude Sonnet 4.6 |
| Dashboard | `streamlit` |
| Charts | `plotly` |
| Data wrangling | `pandas` |
| Movie metadata | TMDB API via `requests` |
| Fuzzy title matching | `thefuzz` |
| Config | `python-dotenv` |

---

## Cost Estimate

A typical <50 KB chat (~2,000 messages → ~40 chunks) costs roughly **$0.05–$0.15** per fresh analysis with Claude Sonnet 4.6. The LLM prompt caching on the system prompt further reduces cost on repeat runs against the same model version. The local MD5 cache means you only pay LLM costs once per unique chat file.

---

## Docs

- [Architecture](docs/architecture.md) — module design, data flow, and key design decisions
- [Data Model](docs/data-model.md) — full JSON schema of the aggregated output
- [API Keys](docs/api-keys.md) — step-by-step guide to getting your Anthropic and TMDB keys

---

## Roadmap (v2)

- [ ] Media export support — process shared movie clip thumbnails
- [ ] Multiple chat files — merge analysis across different groups
- [ ] Genre-based filtering in Movie Explorer
- [ ] Actors / directors tab in the dashboard (data already extracted, not yet visualized)
- [ ] Public deployment with authentication layer
