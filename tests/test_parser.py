from datetime import datetime

import pytest

from parser import parse

# ── Fixture chat snippets ─────────────────────────────────────────────────────

ANDROID_BASIC = (
    "15/03/2024, 10:30 - Rahul: bhai dune dekha?\n"
    "15/03/2024, 10:31 - Priya: haan yaar mast tha"
).encode()

IOS_BASIC = (
    "[15/03/2024, 10:30:00] Rahul: bhai dune dekha?\n"
    "[15/03/2024, 10:31:00] Priya: haan yaar mast tha"
).encode()

AMPM_TIMESTAMPS = (
    "15/03/2024, 10:30 AM - Rahul: good morning\n"
    "15/03/2024, 02:15 PM - Priya: afternoon everyone"
).encode()

MULTILINE = (
    "15/03/2024, 10:30 - Rahul: dune dekha?\n"
    "ekdum zabardast tha yaar\n"
    "must watch"
).encode()

SYSTEM_MESSAGES = (
    "15/03/2024, 10:00 - Messages and calls are end-to-end encrypted. No one outside of this chat, not even WhatsApp, can read or listen to them.\n"
    "15/03/2024, 10:01 - Rahul added Priya\n"
    "15/03/2024, 10:02 - Rahul: okay let's go\n"
    "15/03/2024, 10:03 - Rahul: <Media omitted>\n"
    "15/03/2024, 10:04 - Priya: this message was deleted"
).encode()

PHONE_NUMBERS = (
    "15/03/2024, 10:30 - +91 98765 43210: kya scene hai\n"
    "15/03/2024, 10:31 - +91 98765 43210: dune dekha?\n"
    "15/03/2024, 10:32 - +61 413 937 111: haven't seen it yet\n"
    "15/03/2024, 10:33 - Rahul: bhai dekh le"
).encode()

REAL_NAME_NOT_ALIASED = (
    "15/03/2024, 10:30 - Rahul Sharma: mast tha"
).encode()

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_android_format_parses_sender_and_text():
    messages, _ = parse(ANDROID_BASIC)
    assert len(messages) == 2
    assert messages[0]["sender"] == "Rahul"
    assert messages[0]["text"] == "bhai dune dekha?"
    assert messages[1]["sender"] == "Priya"


def test_ios_format_parses_sender_and_text():
    messages, _ = parse(IOS_BASIC)
    assert len(messages) == 2
    assert messages[0]["sender"] == "Rahul"
    assert messages[0]["text"] == "bhai dune dekha?"


def test_android_timestamp_parsed():
    messages, _ = parse(ANDROID_BASIC)
    ts = messages[0]["timestamp"]
    assert isinstance(ts, datetime)
    assert ts.day == 15
    assert ts.month == 3
    assert ts.year == 2024
    assert ts.hour == 10
    assert ts.minute == 30


def test_ampm_timestamp_parsed():
    messages, _ = parse(AMPM_TIMESTAMPS)
    assert len(messages) == 2
    assert messages[1]["timestamp"].hour == 14  # 2 PM → 14


def test_multiline_message_concatenated():
    messages, _ = parse(MULTILINE)
    assert len(messages) == 1
    assert "ekdum zabardast tha yaar" in messages[0]["text"]
    assert "must watch" in messages[0]["text"]


def test_system_messages_filtered():
    messages, _ = parse(SYSTEM_MESSAGES)
    # Only "okay let's go" survives — encryption notice, join event, media, deleted are filtered
    assert len(messages) == 1
    assert messages[0]["text"] == "okay let's go"


def test_phone_number_aliased():
    messages, alias_map = parse(PHONE_NUMBERS)
    assert "+91 98765 43210" in alias_map
    assert alias_map["+91 98765 43210"] == "Contact 1"
    assert "+61 413 937 111" in alias_map
    assert alias_map["+61 413 937 111"] == "Contact 2"


def test_phone_number_alias_stable_across_messages():
    messages, alias_map = parse(PHONE_NUMBERS)
    phone_senders = [m["sender"] for m in messages if m["sender"].startswith("Contact")]
    # Both messages from +91 98765 43210 should map to "Contact 1"
    assert all(s == "Contact 1" for s in phone_senders[:2])


def test_phone_number_replaced_in_messages():
    messages, _ = parse(PHONE_NUMBERS)
    raw_phones = [m for m in messages if m["sender"].startswith("+")]
    assert raw_phones == [], "Raw phone numbers must not appear in message senders"


def test_real_name_not_aliased():
    messages, alias_map = parse(REAL_NAME_NOT_ALIASED)
    assert alias_map == {}
    assert messages[0]["sender"] == "Rahul Sharma"


def test_alias_map_empty_for_clean_chat():
    messages, alias_map = parse(ANDROID_BASIC)
    assert alias_map == {}


def test_returns_tuple():
    result = parse(ANDROID_BASIC)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_empty_input():
    messages, alias_map = parse(b"")
    assert messages == []
    assert alias_map == {}


def test_utf8_with_emoji():
    chat = "15/03/2024, 10:30 - Rahul: 🔥 ekdum fire tha yaar".encode("utf-8")
    messages, _ = parse(chat)
    assert len(messages) == 1
    assert "🔥" in messages[0]["text"]
