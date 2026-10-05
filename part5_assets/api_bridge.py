"""
Custom API bridge for image generation (spec 5.1).

Pure logic: no tkinter / customtkinter import, so it works headless and in tests.
URL and key come from config.json (assets_api_url / assets_api_key) or the
environment (JUPRISX_ASSETS_URL / JUPRISX_ASSETS_KEY).
"""
from __future__ import annotations

import base64
import io
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _load() -> tuple[str, str, float]:
    cfg = {}
    try:
        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    url = os.environ.get("JUPRISX_ASSETS_URL", cfg.get("assets_api_url", ""))
    key = os.environ.get("JUPRISX_ASSETS_KEY", cfg.get("assets_api_key", ""))
    return url.rstrip("/"), key, float(cfg.get("assets_timeout", 120))


API_URL, API_KEY, API_TIMEOUT = _load()


class ImageAPIError(RuntimeError):
    """Readable error for the UI (network, HTTP, empty payload, bad image)."""


def generate_image(prompt: str, timeout: float | None = None):
    """Request an image and return a PIL.Image. Raises ImageAPIError."""
    import requests
    from PIL import Image

    if not prompt or not prompt.strip():
        raise ImageAPIError("Prompt kosong.")
    if not API_URL:
        raise ImageAPIError("assets_api_url belum diisi di config.json.")

    try:
        resp = requests.post(
            f"{API_URL}/generate_image",
            json={"prompt": prompt},
            headers={"x-internal-key": API_KEY},
            timeout=timeout or API_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout as exc:
        raise ImageAPIError("Server gambar timeout.") from exc
    except requests.RequestException as exc:
        raise ImageAPIError(f"Server gambar tidak bisa dihubungi: {exc}") from exc
    except ValueError as exc:
        raise ImageAPIError("Respons server bukan JSON.") from exc

    b64 = data.get("image_base64", "") if isinstance(data, dict) else ""
    if not b64:
        raise ImageAPIError("Payload base64 kosong dari server.")
    if b64.startswith("data:") and "," in b64:      # data URI
        b64 = b64.split(",", 1)[1]
    try:
        image = Image.open(io.BytesIO(base64.b64decode(b64)))
        image.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageAPIError(f"Data gambar rusak: {exc}") from exc
    return image


def generate_image_thread(prompt: str,
                          on_done: Callable[[object], None],
                          on_error: Callable[[str], None]) -> threading.Thread:
    """Run generate_image in a worker thread. The callbacks run in that worker
    thread, so UI code must hand results over via a queue (AssetsPanel does)."""
    def work():
        try:
            image = generate_image(prompt)
        except ImageAPIError as exc:
            on_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            on_error(f"Error: {exc}")
        else:
            on_done(image)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    return t
