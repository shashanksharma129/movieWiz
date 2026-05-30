from parser import parse


def test_jpg_message_tagged_with_media_filename():
    chat = b"15/03/2024, 10:30 - Rahul: IMG-20240115-WA0001.jpg (file attached)"
    messages, _ = parse(chat)
    assert len(messages) == 1
    assert messages[0]["media_filename"] == "IMG-20240115-WA0001.jpg"


def test_png_message_tagged():
    chat = b"15/03/2024, 10:30 - Rahul: PHOTO-001.png (file attached)"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "PHOTO-001.png"


def test_media_filename_without_file_attached_suffix():
    chat = b"15/03/2024, 10:30 - Rahul: IMG-001.jpg"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "IMG-001.jpg"


def test_non_media_message_has_no_media_filename():
    chat = b"15/03/2024, 10:30 - Rahul: bhai dune dekha?"
    messages, _ = parse(chat)
    assert "media_filename" not in messages[0]


def test_audio_file_not_tagged_as_image():
    chat = b"15/03/2024, 10:30 - Rahul: PTT-001.opus (file attached)"
    messages, _ = parse(chat)
    # Opus messages are included as regular messages (not filtered, not tagged)
    assert "media_filename" not in messages[0]


def test_webp_tagged():
    chat = b"15/03/2024, 10:30 - Rahul: STICKER-001.webp (file attached)"
    messages, _ = parse(chat)
    assert messages[0]["media_filename"] == "STICKER-001.webp"
