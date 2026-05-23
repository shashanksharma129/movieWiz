from enricher import _empty_tmdb
from thefuzz import process as fuzz_process

_SENTIMENT_SCORES = {"positive": 1.0, "mixed": 0.5, "neutral": 0.5, "negative": 0.0}
_FUZZY_THRESHOLD = 80


def _normalize_titles(raw_movies: list[dict]) -> dict[str, list[dict]]:
    """Group movie mentions by fuzzy-matched title."""
    canonical: dict[str, list[dict]] = {}

    for mention in raw_movies:
        title = mention.get("title", "").strip()
        if not title:
            continue

        if not canonical:
            canonical[title] = [mention]
            continue

        match, score = fuzz_process.extractOne(title, list(canonical.keys()))
        if score >= _FUZZY_THRESHOLD:
            canonical[match].append(mention)
        else:
            canonical[title] = [mention]

    return canonical


def build(raw_extraction: dict) -> dict:
    """
    Build the final aggregated data model from raw LLM extraction.
    TMDB metadata is not attached here — call attach_tmdb() after enrichment.
    Returns {"movies": [...], "people": {...}, "actors_directors": [...]}.
    """
    raw_movies = raw_extraction.get("movies", [])
    raw_actors = raw_extraction.get("actors_directors", [])

    grouped = _normalize_titles(raw_movies)

    movies = []
    for canonical_title, mentions in grouped.items():
        per_person: dict[str, dict] = {}
        sentiment_scores = []
        recommendation_count = 0
        avoid_count = 0
        explicit_ratings = []
        timeline = []

        for m in mentions:
            sender = m.get("mentioned_by", "Unknown")
            sentiment = m.get("sentiment", "neutral")
            score = float(m.get("sentiment_score") or _SENTIMENT_SCORES.get(sentiment, 0.5))
            sentiment_scores.append(score)

            rec = m.get("recommendation_signal", "neutral")
            if rec == "recommended":
                recommendation_count += 1
            elif rec == "avoid":
                avoid_count += 1

            rating = m.get("explicit_rating")
            if rating:
                explicit_ratings.append(rating)

            if sender not in per_person:
                per_person[sender] = {"sentiment": sentiment, "quotes": [], "rating": None}

            quote = m.get("raw_quote", "")
            if quote:
                per_person[sender]["quotes"].append(quote)
            if rating and per_person[sender]["rating"] is None:
                per_person[sender]["rating"] = rating

            timeline.append({
                "timestamp": m.get("timestamp"),
                "sender": sender,
                "sentiment": sentiment,
            })

        avg_score = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.5
        if avg_score >= 0.65:
            group_sentiment = "positive"
        elif avg_score <= 0.35:
            group_sentiment = "negative"
        else:
            group_sentiment = "mixed"

        timeline.sort(key=lambda x: str(x["timestamp"]) if x["timestamp"] else "")

        movies.append({
            "title": canonical_title,
            "tmdb": {},
            "group_sentiment": group_sentiment,
            "group_sentiment_score": round(avg_score, 2),
            "mention_count": len(mentions),
            "recommendations": recommendation_count,
            "avoid_signals": avoid_count,
            "explicit_ratings": explicit_ratings,
            "per_person": per_person,
            "first_mentioned_at": timeline[0]["timestamp"] if timeline else None,
            "timeline": timeline,
        })

    movies.sort(key=lambda x: x["mention_count"], reverse=True)

    # Build people summary from grouped mentions (populates recommendation_count and sentiment_scores)
    people: dict[str, dict] = {}
    for canonical_title, mentions in grouped.items():
        for m in mentions:
            sender = m.get("mentioned_by", "Unknown")
            if sender not in people:
                people[sender] = {
                    "total_movie_messages": 0,
                    "movies_mentioned": [],
                    "recommendation_count": 0,
                    "sentiment_scores": [],
                }
            people[sender]["total_movie_messages"] += 1
            if canonical_title not in people[sender]["movies_mentioned"]:
                people[sender]["movies_mentioned"].append(canonical_title)
            if m.get("recommendation_signal") == "recommended":
                people[sender]["recommendation_count"] += 1
            score = float(m.get("sentiment_score") or _SENTIMENT_SCORES.get(m.get("sentiment", "neutral"), 0.5))
            people[sender]["sentiment_scores"].append(score)

    # Deduplicate and merge actors/directors
    seen_names: dict[str, dict] = {}
    for a in raw_actors:
        name = a.get("name", "").strip()
        if not name:
            continue
        if name not in seen_names:
            seen_names[name] = {
                "name": name,
                "role": a.get("role", "unknown"),
                "mentioned_by": [],
                "contexts": [],
                "associated_movies": [],
            }
        entry = seen_names[name]
        sender = a.get("mentioned_by", "")
        if sender and sender not in entry["mentioned_by"]:
            entry["mentioned_by"].append(sender)
        ctx = a.get("context", "")
        if ctx:
            entry["contexts"].append(ctx)
        movie = a.get("associated_movie", "")
        if movie and movie not in entry["associated_movies"]:
            entry["associated_movies"].append(movie)

    actors = list(seen_names.values())

    return {"movies": movies, "people": people, "actors_directors": actors}


def attach_tmdb(movies: list[dict], tmdb_data: dict) -> None:
    """Attach TMDB metadata to each movie in-place, keyed by canonical title."""
    for movie in movies:
        movie["tmdb"] = tmdb_data.get(movie["title"], _empty_tmdb())
