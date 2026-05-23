import os
import requests
from dotenv import load_dotenv

load_dotenv()

_TMDB_BASE = "https://api.themoviedb.org/3"
_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _search_movie(title: str, api_key: str) -> dict | None:
    try:
        r = requests.get(
            f"{_TMDB_BASE}/search/movie",
            params={"api_key": api_key, "query": title, "language": "en-US"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def _get_details(tmdb_id: int, api_key: str) -> dict:
    try:
        r = requests.get(
            f"{_TMDB_BASE}/movie/{tmdb_id}",
            params={"api_key": api_key, "language": "en-US"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def enrich(movie_titles: list[str]) -> dict[str, dict]:
    """Return a dict mapping movie title → TMDB metadata."""
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return {t: _empty_tmdb() for t in movie_titles}

    result = {}
    for title in movie_titles:
        hit = _search_movie(title, api_key)
        if not hit:
            result[title] = _empty_tmdb()
            continue

        details = _get_details(hit["id"], api_key)
        poster_path = hit.get("poster_path") or details.get("poster_path")
        genres = [g["name"] for g in details.get("genres", [])]

        result[title] = {
            "tmdb_id": hit["id"],
            "poster_url": f"{_IMAGE_BASE}{poster_path}" if poster_path else None,
            "genres": genres,
            "year": (hit.get("release_date") or "")[:4] or None,
            "tmdb_score": round(hit.get("vote_average", 0), 1),
            "overview": details.get("overview") or hit.get("overview", ""),
        }

    return result


def _empty_tmdb() -> dict:
    return {
        "tmdb_id": None,
        "poster_url": None,
        "genres": [],
        "year": None,
        "tmdb_score": None,
        "overview": "",
    }
