import hashlib
import json
from pathlib import Path

_CACHE_DIR = Path(__file__).parent / ".cache"


def _key(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


def load(file_bytes: bytes) -> tuple[dict | None, str]:
    """Return (cached_data, cache_key). cached_data is None on miss."""
    _CACHE_DIR.mkdir(exist_ok=True)
    key = _key(file_bytes)
    path = _CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f), key
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            return None, key
    return None, key


def save(key: str, data: dict) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    path = _CACHE_DIR / f"{key}.json"
    with open(path, "w") as f:
        json.dump(data, f, default=str, indent=2)
