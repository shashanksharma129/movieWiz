import re
from datetime import datetime
from typing import Optional

# Android: "DD/MM/YYYY, HH:MM - Name: message"
_ANDROID_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?)\s-\s([^:]+?):\s(.+)$"
)
# iOS: "[DD/MM/YYYY, HH:MM:SS] Name: message"
_IOS_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}:\d{2}(?:\s?[AP]M)?)\]\s([^:]+?):\s(.+)$"
)

_SYSTEM_PATTERNS = [
    r"Messages and calls are end-to-end encrypted",
    r".+ added .+",
    r".+ removed .+",
    r".+ left",
    r".+ joined using this group's invite link",
    r".+ changed the (subject|icon|description)",
    r".+ was added",
    r"You were added",
    r"<Media omitted>",
    r"This message was deleted",
    r".+ changed their phone number",
    r".+ created group",
]
_SYSTEM_RE = re.compile("|".join(_SYSTEM_PATTERNS), re.IGNORECASE)


def _parse_timestamp(date_str: str, time_str: str) -> Optional[datetime]:
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


def parse(file_bytes: bytes) -> list[dict]:
    """Parse WhatsApp .txt export bytes into a list of message dicts."""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("utf-8", errors="replace")

    lines = text.splitlines()
    messages = []
    current: Optional[dict] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = _ANDROID_RE.match(line) or _IOS_RE.match(line)
        if match:
            date_str, time_str, sender, text_part = match.groups()
            sender = sender.strip()

            if _SYSTEM_RE.search(text_part) or _SYSTEM_RE.search(sender):
                current = None
                continue

            ts = _parse_timestamp(date_str, time_str)
            current = {"timestamp": ts, "sender": sender, "text": text_part}
            messages.append(current)
        else:
            # Continuation line of previous message
            if current is not None:
                current["text"] += "\n" + line

    return messages
