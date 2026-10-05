"""Small MCP client supporting both HTTP transports:

* Streamable HTTP: POST JSON-RPC to one endpoint, reply comes in the response (JSON or SSE body).
* Classic HTTP+SSE: GET /sse opens a stream, server announces an `endpoint` event, requests are
  POSTed there and replies arrive on the stream.

connect() tries streamable first, then SSE, and records every probe so failures are explainable.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Optional
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]
    HAS_REQUESTS = False

PROTOCOL_VERSION = "2024-11-05"


class McpClient:
    HTTP_PATHS = ("/", "/mcp", "/rpc", "/jsonrpc")
    SSE_PATHS = ("/sse", "/mcp/sse", "/events", "/")

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg  # live reference: edits to the dict apply on next connect()
        self.transport: str = ""
        self.last_error: str = ""
        self.attempts: list[str] = []
        self._path: Optional[str] = None
        self._session: Optional[str] = None
        self._next_id = 0
        # SSE state
        self._sse_url = ""
        self._endpoint: Optional[str] = None
        self._endpoint_evt = threading.Event()
        self._cond = threading.Condition()
        self._responses: dict[Any, Any] = {}
        self._alive = False
        self._resp = None
        self._stream_error = ""

    # ------------------------------------------------------------------ public
    @property
    def connected(self) -> bool:
        if self.transport == "streamable":
            return True
        return self.transport == "sse" and self._alive and bool(self._endpoint)

    def close(self):
        resp, self._resp = self._resp, None
        self._alive = False
        self._endpoint = None
        self._endpoint_evt.clear()
        self._responses.clear()
        if resp is not None:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        self.transport = ""
        self._session = None

    def connect(self, timeout: float = 6.0) -> bool:
        self.close()
        self.attempts = []
        self.last_error = ""
        if not HAS_REQUESTS:
            self.last_error = "Library 'requests' belum terpasang. Jalankan: pip install requests"
            return False
        if not self._base():
            self.last_error = "mcp_url kosong di config.json."
            return False

        outcome = self._try_streamable(timeout)
        if outcome == "ok":
            return True
        if outcome == "fatal":
            return False
        if self._try_sse(timeout):
            return True
        if not self.last_error:
            self.last_error = ("Server terjangkau tapi tidak ada endpoint MCP yang cocok. Hasil probe: "
                               + "; ".join(self.attempts))
        return False

    def request(self, method: str, params: dict, timeout: float) -> Optional[dict]:
        """JSON-RPC request. Returns the decoded response object, or None (see last_error)."""
        if not self.connected and not self.connect(min(timeout, 10.0)):
            return None
        self.last_error = ""
        if self.transport == "streamable":
            return self._request_streamable(method, params, timeout)
        return self._request_sse(method, params, timeout)

    def describe(self) -> list[str]:
        lines = [f"- URL: {self._base() or '(kosong)'}",
                 f"- requests terpasang: {'ya' if HAS_REQUESTS else 'TIDAK (pip install requests)'}",
                 f"- API key diisi: {'ya' if self.cfg.get('mcp_api_key') else 'tidak'}"]
        if self.connected:
            where = self._path if self.transport == "streamable" else self._sse_url.replace(self._base(), "") or "/"
            lines.append(f"- Hasil: ONLINE (transport {self.transport}, endpoint {where})")
        else:
            lines.append(f"- Hasil: OFFLINE - {self.last_error}")
        if self.attempts:
            lines.append("- Probe: " + "; ".join(self.attempts))
        return lines

    # ------------------------------------------------------------------ helpers
    def _base(self) -> str:
        return (self.cfg.get("mcp_url") or "").rstrip("/")

    def _headers(self, sse: bool = False) -> dict[str, str]:
        h = {"Accept": "text/event-stream" if sse else "application/json, text/event-stream"}
        
        if self.cfg.get("mcp_api_key"):
            h["X-API-Key"] = self.cfg["mcp_api_key"]
            
        if not sse:
            h["Content-Type"] = "application/json"
            
        if self._session and not sse:
            h["Mcp-Session-Id"] = self._session
            
        return h

    def _rid(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def _explain(self, exc: Exception) -> str:
        name = type(exc).__name__
        url = self._base()
        if "Timeout" in name:
            return (f"Timeout menghubungi {url}. Cek Tailscale aktif di PC ini dan server berjalan.")
        if "Connection" in name:
            return (f"Tidak bisa terhubung ke {url} ({str(exc)[:100]}). Cek Tailscale, IP/port, dan server.")
        return f"{name}: {str(exc)[:160]}"

    @staticmethod
    def _decode_body(r) -> Optional[Any]:
        text = r.text
        if "text/event-stream" in r.headers.get("Content-Type", "") or text.lstrip().startswith(("event:", "data:")):
            for chunk in reversed([ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]):
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def _init_params(self) -> dict:
        return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "juprisx-agent", "version": "1.0"}}

    # ------------------------------------------------------------------ streamable HTTP
    def _post_url(self, path: str) -> str:
        return self._base() + ("/" if path == "/" else path)

    def _try_streamable(self, timeout: float) -> str:
        """Returns 'ok', 'fatal' (network/auth: stop probing) or 'nomatch' (try SSE)."""
        for path in self.HTTP_PATHS:
            payload = {"jsonrpc": "2.0", "id": self._rid(), "method": "initialize", "params": self._init_params()}
            try:
                r = requests.post(self._post_url(path), json=payload, headers=self._headers(), timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                self.last_error = self._explain(exc)
                self.attempts.append(f"POST {path}=error")
                return "fatal"
            self.attempts.append(f"POST {path}={r.status_code}")
            if r.status_code in (401, 403):
                self.last_error = f"Server menolak API key (HTTP {r.status_code}). Cek mcp_api_key di config.json."
                return "fatal"
            if r.status_code == 200:
                data = self._decode_body(r)
                if isinstance(data, dict) and ("result" in data or "error" in data):
                    self._path = path
                    self.transport = "streamable"
                    self._session = r.headers.get("Mcp-Session-Id")
                    self._notify_streamable("notifications/initialized")
                    return "ok"
        return "nomatch"

    def _notify_streamable(self, method: str):
        try:
            requests.post(self._post_url(self._path or "/"), headers=self._headers(),
                          json={"jsonrpc": "2.0", "method": method}, timeout=5)
        except Exception:  # noqa: BLE001
            pass

    def _request_streamable(self, method: str, params: dict, timeout: float) -> Optional[dict]:
        payload = {"jsonrpc": "2.0", "id": self._rid(), "method": method, "params": params}
        try:
            r = requests.post(self._post_url(self._path or "/"), json=payload,
                              headers=self._headers(), timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            self.last_error = self._explain(exc)
            self.transport = ""
            return None
        if r.status_code != 200:
            self.last_error = f"Server membalas HTTP {r.status_code} untuk {method}."
            if r.status_code in (400, 404):
                self.transport = ""  # session expired: reconnect next time
            return None
        data = self._decode_body(r)
        if data is None:
            self.last_error = "Server membalas 200 tapi bukan JSON/SSE yang valid."
        return data

    # ------------------------------------------------------------------ classic SSE
    def _try_sse(self, timeout: float) -> bool:
        for path in self.SSE_PATHS:
            url = self._base() + ("/" if path == "/" else path)
            try:
                resp = requests.get(url, headers=self._headers(sse=True), stream=True, timeout=(timeout, 120))
            except Exception as exc:  # noqa: BLE001
                self.last_error = self._explain(exc)
                self.attempts.append(f"GET {path}=error")
                return False
            ctype = resp.headers.get("Content-Type", "")
            self.attempts.append(f"GET {path}={resp.status_code}")
            if resp.status_code in (401, 403):
                self.last_error = f"Server menolak API key (HTTP {resp.status_code}) di {path}."
                resp.close()
                return False
            if resp.status_code != 200 or "text/event-stream" not in ctype:
                resp.close()
                continue

            self._sse_url, self._resp, self._alive = url, resp, True
            self._endpoint_evt.clear()
            self._stream_error = ""
            threading.Thread(target=self._reader, args=(resp,), daemon=True).start()
            if not self._endpoint_evt.wait(timeout):
                self.last_error = f"Stream {path} terbuka tapi server tidak mengirim 'endpoint' dalam {timeout:.0f}s."
                self.close()
                return False
            self.transport = "sse"
            init = self._request_sse("initialize", self._init_params(), max(timeout, 8.0))
            if init is None:
                self.close()
                return False
            self._post_sse({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return True
        return False

    def _reader(self, resp):
        event: Optional[str] = None
        try:
            # chunk_size=1: requests otherwise waits for 512 bytes, which stalls small SSE events.
            for line in resp.iter_lines(chunk_size=1, decode_unicode=False):
                if line is None:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", "replace")
                if line == "":
                    event = None
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if event == "endpoint":
                        self._endpoint = urljoin(self._sse_url, data)
                        self._endpoint_evt.set()
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        if event is None and data.startswith(("/", "http")):
                            self._endpoint = urljoin(self._sse_url, data)
                            self._endpoint_evt.set()
                        continue
                    if isinstance(obj, dict):
                        with self._cond:
                            self._responses[obj.get("id")] = obj
                            self._cond.notify_all()
        except Exception as exc:  # noqa: BLE001
            self._stream_error = self._explain(exc)
        finally:
            self._alive = False
            with self._cond:
                self._cond.notify_all()

    def _post_sse(self, payload: dict) -> Optional[Any]:
        try:
            return requests.post(self._endpoint, json=payload, headers=self._headers(), timeout=15)
        except Exception as exc:  # noqa: BLE001
            self.last_error = self._explain(exc)
            return None

    def _request_sse(self, method: str, params: dict, timeout: float) -> Optional[dict]:
        rid = self._rid()  # Sekarang rid adalah string
        r = self._post_sse({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if r is None:
            return None
        if r.status_code in (401, 403):
            self.last_error = f"Server menolak API key (HTTP {r.status_code}) saat mengirim {method}."
            return None
        if r.status_code not in (200, 202, 204):
            self.last_error = f"Endpoint pesan membalas HTTP {r.status_code} untuk {method}."
            return None
        if r.status_code == 200:  # some servers answer inline
            inline = self._decode_body(r)
            if isinstance(inline, dict) and inline.get("id") == rid:
                return inline
        with self._cond:
            ok = self._cond.wait_for(lambda: rid in self._responses or not self._alive, timeout)
            if rid in self._responses:
                return self._responses.pop(rid)
        if not self._alive:
            self.last_error = self._stream_error or "Koneksi SSE terputus sebelum jawaban datang."
            self.transport = ""
        else:
            self.last_error = f"Timeout {timeout:.0f}s menunggu jawaban {method} dari server."
        return None
