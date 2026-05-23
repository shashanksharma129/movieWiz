import json
import os
from datetime import datetime

import anthropic
from dotenv import load_dotenv

load_dotenv()

_MODEL = "claude-sonnet-4-6"
_CHUNK_SIZE = 100

_SYSTEM_PROMPT = """You are a movie discussion analyst specializing in Hinglish text (a mix of English and Hindi written in Roman script). Your task is to extract structured data from WhatsApp chat messages about movies.

You understand common Hinglish movie slang:
- Positive: "mast tha", "solid hai", "must watch", "ekdum zabardast", "too good", "waah", "lit hai", "fire hai", "bhai dekh le", "paisa vasool"
- Negative: "bakwaas tha", "bekar hai", "timepass", "bore ho gaya", "skip kar", "waste of time", "faltu", "kuch nahi hai"
- Recommendation: "must watch bhai", "dekh le yaar", "highly recommend", "watch kar", "dekhna chahiye"
- Avoid: "mat dekh", "skip kar", "avoid karo", "waste hai"
- Neutral/Mixed: "theek tha", "average", "okay okay", "dekh sakte ho", "1 time watch"

For each batch of messages you receive, extract:
1. Every movie mentioned (normalize to official English title if possible, e.g. "RRR" stays "RRR", "Dune Part Two" normalizes from "dune 2")
2. Actors and directors mentioned, with context
3. Per-mention attribution to sender with sentiment and any explicit rating

Return ONLY valid JSON with this exact structure, no other text:
{
  "movies": [
    {
      "title": "normalized movie title",
      "mentioned_by": "sender name exactly as in chat",
      "timestamp": "ISO timestamp string or null",
      "sentiment": "positive|negative|mixed|neutral",
      "sentiment_score": 0.0,
      "explicit_rating": "8/10 or null",
      "recommendation_signal": "recommended|avoid|neutral",
      "raw_quote": "exact message snippet"
    }
  ],
  "actors_directors": [
    {
      "name": "full name",
      "role": "actor|director|unknown",
      "mentioned_by": "sender name",
      "context": "brief context",
      "associated_movie": "movie title or null"
    }
  ]
}

If no movies or actors are mentioned in the batch, return {"movies": [], "actors_directors": []}.
"""


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        ts = m["timestamp"].isoformat() if isinstance(m["timestamp"], datetime) else str(m.get("timestamp", ""))
        lines.append(f"[{ts}] {m['sender']}: {m['text']}")
    return "\n".join(lines)


def _parse_chunk(client: anthropic.Anthropic, chunk: list[dict]) -> dict:
    formatted = _format_messages(chunk)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Extract movie data from these chat messages:\n\n{formatted}",
            }
        ],
    )
    text = next((b.text for b in response.content if b.type == "text"), "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from within the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {"movies": [], "actors_directors": []}


def extract(messages: list[dict]) -> dict:
    """Extract movies and actors from all messages, returning raw combined results."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    all_movies = []
    all_actors = []

    chunks = [messages[i : i + _CHUNK_SIZE] for i in range(0, len(messages), _CHUNK_SIZE)]

    for chunk in chunks:
        try:
            result = _parse_chunk(client, chunk)
        except Exception as e:
            print(f"Warning: chunk failed ({e}), skipping")
            result = {"movies": [], "actors_directors": []}
        all_movies.extend(result.get("movies", []))
        all_actors.extend(result.get("actors_directors", []))

    return {"movies": all_movies, "actors_directors": all_actors}
