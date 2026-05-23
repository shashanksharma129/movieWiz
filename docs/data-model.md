# Data Model

This document describes the JSON structure stored in `.cache/<hash>.json` and held in `st.session_state["data"]` at runtime.

The top-level object has four keys: `movies`, `people`, `actors_directors`, and `alias_map`.

---

## Top-Level Structure

```json
{
  "movies": [ ... ],
  "people": { ... },
  "actors_directors": [ ... ],
  "alias_map": { ... }
}
```

---

## `movies` — list of movie objects

Each entry represents one canonical movie (after fuzzy title deduplication).

```json
{
  "title": "Dune: Part Two",

  "tmdb": {
    "tmdb_id": 693134,
    "poster_url": "https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nxl1X.jpg",
    "genres": ["Science Fiction", "Adventure"],
    "year": "2024",
    "tmdb_score": 8.1,
    "overview": "Follow the mythic journey of Paul Atreides..."
  },

  "group_sentiment": "positive",
  "group_sentiment_score": 0.82,

  "mention_count": 14,
  "recommendations": 5,
  "avoid_signals": 0,
  "explicit_ratings": ["9/10", "8/10"],

  "per_person": {
    "Rahul": {
      "sentiment": "positive",
      "quotes": ["bhai dune 2 dekh lia? ekdum zabardast tha"],
      "rating": "9/10",
      "summary": "Rahul loved Dune: Part Two, calling it 'ekdum zabardast' and strongly recommending it with a 9/10 rating."
    },
    "Priya": {
      "sentiment": "mixed",
      "quotes": ["first half slow tha but second half mast tha"],
      "rating": null,
      "summary": "Priya had mixed feelings — she found the first half slow but thoroughly enjoyed the second half."
    }
  },

  "first_mentioned_at": "2024-03-10T14:22:00",

  "timeline": [
    {
      "timestamp": "2024-03-10T14:22:00",
      "sender": "Rahul",
      "sentiment": "positive"
    }
  ]
}
```

### Field reference

| Field | Type | Description |
|---|---|---|
| `title` | string | Canonical movie title (first occurrence after fuzzy dedup) |
| `tmdb` | object | TMDB metadata; all fields may be `null` if not found |
| `tmdb.tmdb_id` | int \| null | TMDB movie ID |
| `tmdb.poster_url` | string \| null | Full TMDB poster URL at w500 resolution |
| `tmdb.genres` | list[string] | Genre names from TMDB |
| `tmdb.year` | string \| null | 4-digit release year |
| `tmdb.tmdb_score` | float \| null | TMDB vote average (0–10) |
| `tmdb.overview` | string | Plot summary from TMDB |
| `group_sentiment` | "positive" \| "mixed" \| "negative" | Aggregate group opinion |
| `group_sentiment_score` | float 0–1 | Average sentiment score across all mentions |
| `mention_count` | int | Total number of times this movie was mentioned |
| `recommendations` | int | Count of "must watch" / recommended signals |
| `avoid_signals` | int | Count of "skip karo" / avoid signals |
| `explicit_ratings` | list[string] | All explicit ratings found (e.g. "8/10", "4 stars") |
| `per_person` | dict[str, PersonData] | Per-sender opinion data |
| `per_person[].sentiment` | string | Dominant sentiment for this person's mentions |
| `per_person[].quotes` | list[string] | Raw message snippets |
| `per_person[].rating` | string \| null | First explicit rating this person gave |
| `per_person[].summary` | string \| null | AI-generated 1–2 sentence opinion (null if skipped or failed) |
| `first_mentioned_at` | string \| null | ISO timestamp of the earliest mention |
| `timeline` | list[TimelineEvent] | All mentions in chronological order |
| `timeline[].timestamp` | string \| null | ISO timestamp |
| `timeline[].sender` | string | Sender name |
| `timeline[].sentiment` | string | Sentiment for that mention |

---

## `people` — dict of person summaries

Keyed by sender name as it appears in the chat (phone numbers are aliased to "Contact N" before this point).

```json
{
  "Rahul": {
    "total_movie_messages": 23,
    "movies_mentioned": ["Dune: Part Two", "RRR", "Oppenheimer"],
    "recommendation_count": 4,
    "sentiment_scores": [1.0, 0.9, 0.5, 1.0]
  }
}
```

### Field reference

| Field | Type | Description |
|---|---|---|
| `total_movie_messages` | int | Total movie-related messages this person sent |
| `movies_mentioned` | list[string] | Canonical titles this person discussed |
| `recommendation_count` | int | Number of "recommended" signals from this person |
| `sentiment_scores` | list[float] | Per-mention sentiment scores (0=negative, 1=positive) |

---

## `actors_directors` — list of person entities

People mentioned in the chat in the context of movies (not chat participants). Rendered in the Actors & Directors tab.

```json
[
  {
    "name": "Denis Villeneuve",
    "role": "director",
    "mentioned_by": ["Rahul", "Priya"],
    "contexts": ["bhai Villeneuve ka direction ekdum perfect hai"],
    "associated_movies": ["Dune: Part Two"]
  }
]
```

### Field reference

| Field | Type | Description |
|---|---|---|
| `name` | string | Actor or director's name |
| `role` | "actor" \| "director" \| "unknown" | Inferred role |
| `mentioned_by` | list[string] | Chat senders who mentioned this person |
| `contexts` | list[string] | Message snippets providing context |
| `associated_movies` | list[string] | Movies linked to this person in the chat |

---

## `alias_map` — phone number anonymisation map

Present when the chat contained phone numbers as sender names (contacts not saved in the uploader's address book).

```json
{
  "+91 98765 43210": "Contact 1",
  "+61 413 937 111": "Contact 2"
}
```

Keys are original phone number strings exactly as they appeared in the WhatsApp export. Values are the stable aliases used everywhere else in the data model — in `per_person` keys, `people` keys, and `timeline` sender fields. This map is stored in the cache so the Overview tab can render the "N phone numbers anonymised" expander on session reload.

---

## Notes

- All timestamps in the cache are serialized as ISO 8601 strings (e.g. `"2024-03-10T14:22:00"`). The app uses `pd.to_datetime(errors="coerce")` when rendering charts.
- `alias_map` may be an empty dict `{}` if no phone numbers were detected.
- `per_person[].summary` is `null` when the summarizer was skipped (no quotes + neutral sentiment) or encountered an API error for that movie.
