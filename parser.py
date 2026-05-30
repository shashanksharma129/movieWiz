import re
from datetime import datetime

_PHONE_RE = re.compile(r'^\+?[0-9][\d\s\-(). ]{6,}$')

# Android: "DD/MM/YYYY, HH:MM - Name: message"
_ANDROID_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?)\s-\s([^:]+?):\s(.+)$"
)
# iOS: "[DD/MM/YYYY, HH:MM:SS] Name: message"
_IOS_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}:\d{2}(?:\s?[AP]M)?)\]\s([^:]+?):\s(.+)$"
)

# Exact phrases matched against message text (text_part)
_SYSTEM_TEXT_RE = re.compile(
    r"|".join([
        r"Messages and calls are end-to-end encrypted",
        r"<Media omitted>",
        r"This message was deleted",
        r"You deleted this message",
    ]),
    re.IGNORECASE,
)

# Membership/event patterns matched against sender name only — broad patterns
# that would false-positive on user messages like "I added Dune to my watchlist"
_SYSTEM_SENDER_RE = re.compile(
    r"|".join([
        r".+ added .+",
        r".+ removed .+",
        r".+ left",
        r".+ joined using this group's invite link",
        r".+ changed the (?:subject|icon|description)",
        r".+ was added",
        r"You were added",
        r".+ changed their phone number",
        r".+ created group",
    ]),
    re.IGNORECASE,
)

_MEDIA_IMAGE_RE = re.compile(
    r"^(\S+\.(jpg|jpeg|png|webp|gif))\s*(\(file attached\))?$",
    re.IGNORECASE,
)


def _parse_timestamp(date_str: str, time_str: str) -> datetime | None:
    time_str = time_str.strip()
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%y %H:%M:%S",
        "%d/%m/%y %H:%M",
        "%d/%m/%y %I:%M:%S %p",
        "%d/%m/%y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
    ]
    combined = f"{date_str} {time_str}"
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def parse(file_bytes: bytes) -> tuple[list[dict], dict[str, str]]:
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("utf-8", errors="replace")

    lines = text.splitlines()
    messages = []
    current: dict | None = None
    aliases: dict[str, str] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = _ANDROID_RE.match(line) or _IOS_RE.match(line)
        if match:
            date_str, time_str, sender, text_part = match.groups()
            sender = sender.strip()

            if _PHONE_RE.match(sender) and sender not in aliases:
                aliases[sender] = f"Contact {len(aliases) + 1}"
            sender = aliases.get(sender, sender)

            if _SYSTEM_TEXT_RE.search(text_part) or _SYSTEM_SENDER_RE.search(sender):
                current = None
                continue

            ts = _parse_timestamp(date_str, time_str)
            current = {"timestamp": ts, "sender": sender, "text": text_part}
            media_match = _MEDIA_IMAGE_RE.match(text_part.strip())
            if media_match:
                current["media_filename"] = media_match.group(1)
            messages.append(current)
        else:
            if current is not None:
                current["text"] += "\n" + line

    return messages, aliases
