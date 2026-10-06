"""Generic UI-free chat engine base for the HTML/JS Android builder."""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from .context_manager import ContextManager
from .mcp_client import McpClient

_CONFIG_PATH=Path(__file__).resolve().parent.parent/"config.json"
@dataclass
class Reply:
    text:str
    action:Optional[str]=None
    data:dict[str,Any]=field(default_factory=dict)

def load_config(path=_CONFIG_PATH):
    cfg={"mcp_url":"","mcp_api_key":"","mcp_timeout_chat":8,"mcp_timeout_generate":90}
    try: cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError,json.JSONDecodeError): pass
    cfg["mcp_url"]=os.environ.get("JUPRISX_MCP_URL",cfg["mcp_url"]); cfg["mcp_api_key"]=os.environ.get("JUPRISX_MCP_KEY",cfg["mcp_api_key"])
    return cfg

class HybridEngine:
    def __init__(self,context=None,config=None):
        self.ctx=context or ContextManager(); self.cfg=config or load_config(); self.mcp=McpClient(self.cfg); self.mcp_online=False; self.last_error=""
    def handle(self,prompt): return self._do_chat(prompt)
    def _do_chat(self,prompt):
        text=self._call_mcp(prompt,"ask_guidance",self.cfg.get("mcp_timeout_chat",8),self.ctx.mode=="Project Context")
        return Reply(text or "MCP offline.")
    def _call_mcp(self,prompt,intent,timeout,include_sources=False):
        try:
            result=self.mcp.call_tool("jupris_agentic_brain",{"prompt":prompt,"intent":intent,"include_sources":include_sources},timeout)
            if not result: return None
            payload=result.get("result",result)
            content=payload.get("content") if isinstance(payload,dict) else None
            if isinstance(content,list): return "\n".join(str(x.get("text",x)) if isinstance(x,dict) else str(x) for x in content)
            if isinstance(payload,dict): return payload.get("text") or payload.get("response") or payload.get("message")
            return str(payload)
        except Exception as exc: self.last_error=str(exc); return None
    def ping(self,timeout=4): self.mcp_online=self.mcp.connect(timeout); self.last_error="" if self.mcp_online else self.mcp.last_error; return self.mcp_online
    def diagnose(self): self.ping(6); return "\n".join(["**MCP check**"]+self.mcp.describe())
    def make_fix_provider(self):
        def provider(prompt):
            text=self._call_mcp(prompt,"request_web_patch",self.cfg.get("mcp_timeout_generate",90),True); return self.parse_files(text)
        return provider
    @staticmethod
    def parse_files(text):
        if not text:return {}
        out={}; pattern=re.compile(r"```[^\n]*\n(?:#|//|<!--)\s*file:\s*([^\n>]+?)(?:\s*-->)?\s*\n(.*?)```",re.S|re.I)
        for m in pattern.finditer(text):
            path=m.group(1).strip().replace("\\","/")
            if path and not path.startswith("/") and ".." not in Path(path).parts: out[path]=m.group(2)
        return out
