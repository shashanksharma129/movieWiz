import io
import zipfile
from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_ZIP_BYTES = 50 * 1024 * 1024


def extract(zip_bytes: bytes) -> tuple[bytes, dict[str, bytes]]:
    """
    Returns (chat_txt_bytes, image_map {filename -> bytes}).
    Raises ValueError if ZIP > 50MB or no chat .txt found.
    Non-image files are silently discarded.
    """
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise ValueError(
            f"ZIP file is {len(zip_bytes) / 1024 / 1024:.1f} MB — limit is 50 MB."
        )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

        # {basename -> arcname} for lookup
        basename_map: dict[str, str] = {}
        for n in names:
            basename_map[Path(n).name] = n

        chat_arcname = basename_map.get("_chat.txt")
        if chat_arcname is None:
            chat_arcname = next(
                (arc for base, arc in basename_map.items() if base.endswith(".txt")),
                None,
            )
        if chat_arcname is None:
            raise ValueError("No WhatsApp chat .txt file found in ZIP.")

        chat_bytes = zf.read(chat_arcname)

        image_map: dict[str, bytes] = {}
        for arc in names:
            base = Path(arc).name
            if Path(base).suffix.lower() in _IMAGE_EXTS:
                image_map[base] = zf.read(arc)

        return chat_bytes, image_map
