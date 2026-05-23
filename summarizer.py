import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
from dotenv import load_dotenv

from utils import with_retry

load_dotenv()

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You summarize movie opinions from a Hinglish WhatsApp chat (English + Hindi in Roman script).

Given a movie title and per-person data (quotes, sentiment, explicit rating), write a 1–2 sentence natural-language summary of each person's opinion. Common Hinglish: "mast tha"=loved it, "bakwaas"=hated it, "timepass"=okay, "must watch"=recommending, "theek tha"=decent, "solid hai"=great, "paisa vasool"=worth it.

Return ONLY valid JSON: {"PersonName": "Summary sentence(s).", ...}
If a person has very short or contextless quotes, rely on their sentiment label and rating."""


def _build_user_message(movie: dict) -> str:
    lines = [f'Movie: "{movie["title"]}"', ""]
    for person, pdata in movie["per_person"].items():
        rating = pdata.get("rating") or "null"
        sentiment = pdata.get("sentiment", "neutral")
        quotes = pdata.get("quotes", [])
        quote_str = json.dumps(quotes[:5])
        lines.append(f"{person} | sentiment: {sentiment} | rating: {rating} | quotes: {quote_str}")
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}


def _summarize_one(client: anthropic.Anthropic, movie: dict) -> tuple[dict, dict]:
    """Returns (movie, summaries_dict). Raises on failure so caller can retry."""
    response = with_retry(
        client.messages.create,
        model=_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": _build_user_message(movie)}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "{}")
    return movie, _parse_response(text)


def summarize(movies: list[dict]) -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    client = anthropic.Anthropic(api_key=api_key)

    eligible = [
        m for m in movies
        if m.get("per_person") and any(
            pdata.get("quotes") or pdata.get("sentiment") not in (None, "neutral")
            for pdata in m["per_person"].values()
        )
    ]

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_summarize_one, client, movie): movie for movie in eligible}
        for future in as_completed(futures):
            movie = futures[future]
            try:
                _, summaries = future.result()
            except Exception as e:
                print(f"Warning: summarizer failed for '{movie['title']}' ({e})")
                summaries = {}
            for person, pdata in movie["per_person"].items():
                pdata["summary"] = summaries.get(person)
