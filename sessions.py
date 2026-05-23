import json
from datetime import datetime

import cache as _cache

_INDEX = _cache.CACHE_DIR / "sessions.json"


def _read() -> list[dict]:
    if not _INDEX.exists():
        return []
    try:
        with open(_INDEX) as f:
            return json.load(f).get("sessions", [])
    except (json.JSONDecodeError, OSError):
        return []


def _write(sessions: list[dict]) -> None:
    _cache.CACHE_DIR.mkdir(exist_ok=True)
    with open(_INDEX, "w") as f:
        json.dump({"sessions": sessions}, f, indent=2)


def list_sessions(user_id: str) -> list[dict]:
    return sorted(
        [s for s in _read() if s.get("user_id") == user_id],
        key=lambda s: s.get("created_at", ""),
        reverse=True,
    )


def register(name: str, cache_key: str, movie_count: int, user_id: str) -> None:
    sessions = [s for s in _read() if not (s["name"] == name and s.get("user_id") == user_id)]
    sessions.append({
        "name": name,
        "cache_key": cache_key,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "movie_count": movie_count,
        "user_id": user_id,
    })
    _write(sessions)


def load_by_name(name: str, user_id: str) -> dict | None:
    for s in _read():
        if s["name"] == name and s.get("user_id") == user_id:
            data, _ = _cache.load_by_key(s["cache_key"])
            return data
    return None


def delete(name: str, user_id: str) -> None:
    _write([s for s in _read() if not (s["name"] == name and s.get("user_id") == user_id)])
