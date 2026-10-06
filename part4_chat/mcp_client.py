"""Small MCP HTTP/SSE client used by the JuprisX web builder."""
from __future__ import annotations

import json
import threading
from typing import Any, Optional
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None
    HAS_REQUESTS = False

PROTOCOL_VERSION = "2024-11-05"


class McpClient:
    HTTP_PATHS = ("/", "/mcp", "/rpc", "/jsonrpc")
    SSE_PATHS = ("/sse", "/mcp/sse", "/events", "/")

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg; self.transport = ""; self.last_error = ""; self.attempts=[]
        self._path=None; self._session=None; self._next_id=0
        self._sse_url=""; self._endpoint=None; self._endpoint_evt=threading.Event(); self._cond=threading.Condition(); self._responses={}; self._alive=False; self._resp=None

    @property
    def connected(self): return self.transport == "streamable" or (self.transport == "sse" and self._alive and bool(self._endpoint))

    def close(self):
        if self._resp:
            try: self._resp.close()
            except Exception: pass
        self._resp=None; self._alive=False; self._endpoint=None; self.transport=""; self._session=None

    def connect(self, timeout=6.0):
        self.close(); self.attempts=[]; self.last_error=""
        if not HAS_REQUESTS: self.last_error="requests package missing"; return False
        if not self._base(): self.last_error="mcp_url is empty"; return False
        for path in self.HTTP_PATHS:
            try:
                payload={"jsonrpc":"2.0","id":self._rid(),"method":"initialize","params":{"protocolVersion":PROTOCOL_VERSION,"capabilities":{},"clientInfo":{"name":"juprisx-web-builder","version":"2.0"}}}
                r=requests.post(self._base()+("/" if path=="/" else path),json=payload,headers=self._headers(),timeout=timeout)
                self.attempts.append(f"POST {path}={r.status_code}")
                if r.status_code in (401,403): self.last_error=f"MCP auth failed: HTTP {r.status_code}"; return False
                data=self._decode(r)
                if r.status_code==200 and isinstance(data,dict) and ("result" in data or "error" in data):
                    self._path=path; self.transport="streamable"; self._session=r.headers.get("Mcp-Session-Id"); return True
            except Exception as exc: self.last_error=str(exc); return False
        self.last_error="No streamable MCP endpoint found"; return False

    def request(self, method: str, params: dict, timeout: float=30.0) -> Optional[dict]:
        if not self.connected and not self.connect(min(timeout,10)): return None
        try:
            payload={"jsonrpc":"2.0","id":self._rid(),"method":method,"params":params}
            r=requests.post(self._base()+("/" if self._path=="/" else (self._path or "/")),json=payload,headers=self._headers(),timeout=timeout)
            if r.status_code!=200: self.last_error=f"HTTP {r.status_code} for {method}"; return None
            return self._decode(r)
        except Exception as exc: self.last_error=str(exc); return None

    def call_tool(self, tool_name: str, arguments: dict, timeout: float=90.0) -> Optional[dict]:
        return self.request("tools/call", {"name": tool_name, "arguments": arguments}, timeout)

    def describe(self):
        return [f"- URL: {self._base() or '(empty)'}", f"- requests: {'yes' if HAS_REQUESTS else 'NO'}", f"- MCP: {'ONLINE' if self.connected else 'OFFLINE'}", *( [f"- Error: {self.last_error}"] if self.last_error else [])]

    def _base(self): return (self.cfg.get("mcp_url") or "").rstrip("/")
    def _rid(self): self._next_id += 1; return str(self._next_id)
    def _headers(self):
        h={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
        if self.cfg.get("mcp_api_key"): h["X-API-Key"]=self.cfg["mcp_api_key"]
        if self._session: h["Mcp-Session-Id"]=self._session
        return h
    @staticmethod
    def _decode(r):
        try: return r.json()
        except Exception:
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    try: return json.loads(line[5:].strip())
                    except Exception: pass
        return None
