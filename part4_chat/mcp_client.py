"""Minimal MCP client with streamable HTTP and classic HTTP+SSE transports."""
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
        self.cfg = cfg; self.transport=""; self.last_error=""; self.attempts=[]; self._path=None; self._session=None; self._next_id=0
        self._sse_url=""; self._endpoint=None; self._endpoint_evt=threading.Event(); self._cond=threading.Condition(); self._responses={}; self._alive=False; self._resp=None; self._stream_error=""

    @property
    def connected(self): return self.transport=="streamable" or (self.transport=="sse" and self._alive and bool(self._endpoint))

    def close(self):
        if self._resp:
            try: self._resp.close()
            except Exception: pass
        self._resp=None; self._alive=False; self._endpoint=None; self.transport=""; self._session=None; self._endpoint_evt.clear(); self._responses.clear()

    def connect(self, timeout=6.0):
        self.close(); self.attempts=[]; self.last_error=""
        if not HAS_REQUESTS: self.last_error="requests package missing"; return False
        if not self._base(): self.last_error="mcp_url is empty"; return False
        outcome=self._try_streamable(timeout)
        if outcome=="ok": return True
        if outcome=="fatal": return False
        return self._try_sse(timeout)

    def request(self, method: str, params: dict, timeout: float=30.0) -> Optional[dict]:
        if not self.connected and not self.connect(min(timeout,10)): return None
        return self._request_streamable(method,params,timeout) if self.transport=="streamable" else self._request_sse(method,params,timeout)

    def call_tool(self, tool_name: str, arguments: dict, timeout: float=90.0) -> Optional[dict]:
        return self.request("tools/call", {"name":tool_name,"arguments":arguments}, timeout)

    def describe(self):
        return [f"- URL: {self._base() or '(empty)'}", f"- requests: {'yes' if HAS_REQUESTS else 'NO'}", f"- MCP: {'ONLINE' if self.connected else 'OFFLINE'}", *( [f"- Error: {self.last_error}"] if self.last_error else [])]

    def _base(self): return (self.cfg.get("mcp_url") or "").rstrip("/")
    def _rid(self): self._next_id+=1; return str(self._next_id)
    def _headers(self,sse=False):
        h={"Accept":"text/event-stream" if sse else "application/json, text/event-stream"}
        if not sse: h["Content-Type"]="application/json"
        if self.cfg.get("mcp_api_key"): h["X-API-Key"]=self.cfg["mcp_api_key"]
        if self._session and not sse: h["Mcp-Session-Id"]=self._session
        return h
    @staticmethod
    def _decode(r):
        text=r.text
        try: return r.json()
        except Exception: pass
        for line in text.splitlines():
            if line.startswith("data:"):
                try: return json.loads(line[5:].strip())
                except Exception: pass
        return None

    def _try_streamable(self,timeout):
        for path in self.HTTP_PATHS:
            try:
                payload={"jsonrpc":"2.0","id":self._rid(),"method":"initialize","params":{"protocolVersion":PROTOCOL_VERSION,"capabilities":{},"clientInfo":{"name":"juprisx-web-builder","version":"2.0"}}}
                r=requests.post(self._base()+("/" if path=="/" else path),json=payload,headers=self._headers(),timeout=timeout); self.attempts.append(f"POST {path}={r.status_code}")
                if r.status_code in (401,403): self.last_error=f"MCP auth failed HTTP {r.status_code}"; return "fatal"
                data=self._decode(r)
                if r.status_code==200 and isinstance(data,dict) and ("result" in data or "error" in data):
                    self._path=path; self.transport="streamable"; self._session=r.headers.get("Mcp-Session-Id"); return "ok"
            except Exception as exc: self.last_error=str(exc); return "fatal"
        return "nomatch"

    def _request_streamable(self,method,params,timeout):
        try:
            payload={"jsonrpc":"2.0","id":self._rid(),"method":method,"params":params}; r=requests.post(self._base()+("/" if self._path=="/" else self._path),json=payload,headers=self._headers(),timeout=timeout)
            if r.status_code!=200: self.last_error=f"HTTP {r.status_code} for {method}"; return None
            return self._decode(r)
        except Exception as exc: self.last_error=str(exc); return None

    def _try_sse(self,timeout):
        for path in self.SSE_PATHS:
            url=self._base()+("/" if path=="/" else path)
            try: resp=requests.get(url,headers=self._headers(True),stream=True,timeout=(timeout,120))
            except Exception as exc: self.last_error=str(exc); continue
            ctype=resp.headers.get("Content-Type",""); self.attempts.append(f"GET {path}={resp.status_code}")
            if resp.status_code in (401,403): self.last_error=f"MCP auth failed HTTP {resp.status_code}"; resp.close(); return False
            if resp.status_code!=200 or "text/event-stream" not in ctype: resp.close(); continue
            self._sse_url,self._resp,self._alive=url,resp,True; self._endpoint_evt.clear(); self._stream_error=""
            threading.Thread(target=self._reader,args=(resp,),daemon=True).start()
            if not self._endpoint_evt.wait(timeout): self.last_error="SSE endpoint event timeout"; self.close(); continue
            self.transport="sse"
            if self._request_sse("initialize",{"protocolVersion":PROTOCOL_VERSION,"capabilities":{},"clientInfo":{"name":"juprisx-web-builder","version":"2.0"}},max(timeout,8)) is None: self.close(); continue
            self._post_sse({"jsonrpc":"2.0","method":"notifications/initialized"}); return True
        return False

    def _reader(self,resp):
        event=None
        try:
            for raw in resp.iter_lines(chunk_size=1,decode_unicode=True):
                line=raw or ""
                if line=="": event=None; continue
                if line.startswith("event:"): event=line[6:].strip(); continue
                if not line.startswith("data:"): continue
                data=line[5:].strip()
                if event=="endpoint": self._endpoint=urljoin(self._sse_url,data); self._endpoint_evt.set(); continue
                try: obj=json.loads(data)
                except Exception:
                    if data.startswith(("/","http")): self._endpoint=urljoin(self._sse_url,data); self._endpoint_evt.set()
                    continue
                if isinstance(obj,dict):
                    with self._cond: self._responses[obj.get("id")]=obj; self._cond.notify_all()
        except Exception as exc: self._stream_error=str(exc)
        finally:
            self._alive=False
            with self._cond: self._cond.notify_all()

    def _post_sse(self,payload):
        try: return requests.post(self._endpoint,json=payload,headers=self._headers(),timeout=15)
        except Exception as exc: self.last_error=str(exc); return None

    def _request_sse(self,method,params,timeout):
        rid=self._rid(); r=self._post_sse({"jsonrpc":"2.0","id":rid,"method":method,"params":params})
        if r is None or r.status_code not in (200,202,204): self.last_error=f"SSE HTTP {(r.status_code if r else 'error')} for {method}"; return None
        if r.status_code==200:
            inline=self._decode(r)
            if isinstance(inline,dict) and inline.get("id")==rid: return inline
        with self._cond: self._cond.wait_for(lambda: rid in self._responses or not self._alive,timeout)
        if rid in self._responses: return self._responses.pop(rid)
        self.last_error=self._stream_error or f"SSE timeout waiting for {method}"; return None
