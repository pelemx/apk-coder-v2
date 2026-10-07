"""
Client for the Python bridge's /chat endpoint (same server as /generate_image, port 4333).

    POST {url}/chat   headers: x-internal-key
         body: {"chat_id": str, "prompt": str, "model": str (optional)}

The OpenAPI file does not describe the response body, so the text is extracted
defensively (see extract_text). The raw reply of the last call is kept in
`last_raw` so `cek api` in the chat can show exactly what the server returned.

Config (config.json, all optional):
    chat_api_url   default: assets_api_url
    chat_api_key   default: assets_api_key
    chat_model     default: server default
    chat_timeout   default: mcp_timeout_generate
Environment: JUPRISX_CHAT_URL / JUPRISX_CHAT_KEY
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

_TEXT_KEYS = ("response", "text", "reply", "answer", "message", "content", "output", "result", "data")
_PENDING = {"pending", "processing", "queued", "running", "in_progress", "waiting"}


def extract_text(obj: Any, depth: int = 0) -> str:
    """Pull the assistant text out of an unknown JSON shape."""
    if depth > 5 or obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:          # OpenAI-like
            t = extract_text(choices[0], depth + 1)
            if t:
                return t
        for key in _TEXT_KEYS:
            if key in obj:
                t = extract_text(obj[key], depth + 1)
                if t:
                    return t
        return ""
    if isinstance(obj, list):
        parts = [extract_text(x, depth + 1) for x in obj]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _is_pending(obj: Any) -> bool:
    if isinstance(obj, dict):
        status = str(obj.get("status", "")).lower()
        return status in _PENDING
    return False


class ChatApiClient:
    def __init__(self, cfg: dict[str, Any]):
        self.url = (os.environ.get("JUPRISX_CHAT_URL") or cfg.get("chat_api_url")
                    or cfg.get("assets_api_url") or "").rstrip("/")
        self.key = (os.environ.get("JUPRISX_CHAT_KEY") or cfg.get("chat_api_key")
                    or cfg.get("assets_api_key") or "")
        self.model = str(cfg.get("chat_model") or "")
        self.timeout = float(cfg.get("chat_timeout") or cfg.get("mcp_timeout_generate") or 190)
        self.last_error = ""
        self.last_raw = ""
        self.last_status: Optional[int] = None

    @property
    def configured(self) -> bool:
        return bool(self.url and requests is not None)

    def _headers(self) -> dict[str, str]:
        return {"x-internal-key": self.key} if self.key else {}

    @staticmethod
    def new_chat_id() -> str:
        return "juprisx-" + uuid.uuid4().hex[:12]

    # ------------------------------------------------------------------
    def models(self, timeout: float = 8.0) -> tuple[bool, str]:
        """GET /models -> (ok, raw text snippet)."""
        if not self.configured:
            return False, "chat_api_url / assets_api_url belum diisi di config.json."
        try:
            r = requests.get(f"{self.url}/models", headers=self._headers(), timeout=timeout)
            return r.ok, f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as exc:
            return False, self._explain(exc)

    def ping(self, timeout: float = 4.0) -> bool:
        ok, raw = self.models(timeout)
        self.last_error = "" if ok else raw
        return ok

    # ------------------------------------------------------------------
    def ask(self, prompt: str, timeout: float | None = None, chat_id: str | None = None) -> Optional[str]:
        """Send one prompt. Returns the reply text, or None (see last_error)."""
        self.last_error = ""
        self.last_raw = ""
        self.last_status = None
        if not self.configured:
            self.last_error = "Chat API belum dikonfigurasi (assets_api_url di config.json)."
            return None
        cid = chat_id or self.new_chat_id()
        budget = float(timeout or self.timeout)
        deadline = time.monotonic() + budget
        payload: dict[str, Any] = {"chat_id": cid, "prompt": prompt}
        if self.model:
            payload["model"] = self.model
        try:
            r = requests.post(f"{self.url}/chat", json=payload, headers=self._headers(), timeout=budget)
        except requests.Timeout:
            self.last_error = f"Chat API timeout setelah {int(budget)} detik."
            return None
        except requests.RequestException as exc:
            self.last_error = self._explain(exc)
            return None

        self.last_status = r.status_code
        self.last_raw = r.text or ""
        if not r.ok:
            self.last_error = f"Chat API HTTP {r.status_code}: {self.last_raw[:200]}"
            return None
        try:
            data: Any = r.json()
        except ValueError:
            data = None
        text = extract_text(data) if data is not None else self.last_raw.strip()

        # Some bridges answer asynchronously: poll until the text shows up.
        if not text and (_is_pending(data) or data is not None):
            text = self._poll(cid, deadline)
        if not text:
            self.last_error = "Chat API menjawab tapi tanpa teks. Raw: " + self.last_raw[:200]
            return None
        return text

    def _poll(self, chat_id: str, deadline: float) -> str:
        while time.monotonic() < deadline:
            time.sleep(2.0)
            try:
                r = requests.post(f"{self.url}/poll", json={"chat_id": chat_id},
                                  headers=self._headers(), timeout=15)
            except requests.RequestException:
                return ""
            if not r.ok:
                return ""
            try:
                data = r.json()
            except ValueError:
                data = None
            self.last_raw = r.text or self.last_raw
            text = extract_text(data) if data is not None else ""
            if text and not _is_pending(data):
                return text
            if data is not None and not _is_pending(data) and not text:
                return ""
        return ""

    # ------------------------------------------------------------------
    @staticmethod
    def _explain(exc: Exception) -> str:
        name = type(exc).__name__
        if "Connection" in name:
            return f"Chat API tidak bisa dihubungi ({name}). Cek URL/port dan Tailscale."
        return f"Chat API error: {name}: {exc}"
