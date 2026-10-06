"""Chat UI for the JuprisX HTML/JS Android builder."""
from __future__ import annotations
import queue, threading
from dataclasses import dataclass
from typing import Any, Callable, Optional
try:
    import customtkinter as ctk; USE_CTK=True
except ImportError:
    import tkinter as ctk; USE_CTK=False
from .context_manager import MODES, ContextManager
from .web_hybrid_engine import WebHybridEngine, Reply

@dataclass
class ChatServices:
    scan:Optional[Callable]=None; keystore:Optional[Callable]=None; build:Optional[Callable]=None
    stage_edits:Optional[Callable]=None; create_project:Optional[Callable]=None; attach_folder:Optional[Callable]=None
    default_projects_dir:Optional[Callable]=None; open_assets:Optional[Callable]=None; setup_env:Optional[Callable]=None; auto_fix:Optional[Callable]=None

class ChatTab:
    def __init__(self,parent_widget,context=None,services=None):
        self.ctx=context or ContextManager(); self.services=services or ChatServices(); self.engine=WebHybridEngine(self.ctx); self._q=queue.Queue(); self._busy=False; self._pending=None
        Frame=ctk.CTkFrame if USE_CTK else ctk.Frame; Label=ctk.CTkLabel if USE_CTK else ctk.Label; Button=ctk.CTkButton if USE_CTK else ctk.Button; Entry=ctk.CTkEntry if USE_CTK else ctk.Entry
        self.frame=Frame(parent_widget,corner_radius=8) if USE_CTK else Frame(parent_widget); Label(self.frame,text="Web App Chat",font=("Segoe UI",14,"bold")).pack(anchor="w",padx=10,pady=(10,2))
        self.status=Label(self.frame,text="Web Agent offline",anchor="w"); self.status.pack(fill="x",padx=10)
        row=Frame(self.frame,fg_color="transparent") if USE_CTK else Frame(self.frame); row.pack(fill="x",padx=8,pady=4)
        self.buttons={}
        for mode in MODES:
            b=Button(row,text=mode,width=105,command=lambda m=mode:self.set_mode(m)); b.pack(side="left",padx=2); self.buttons[mode]=b
        Button(row,text="Attach Folder",width=110,command=self.attach_folder).pack(side="right",padx=2)
        if USE_CTK:self.history=ctk.CTkTextbox(self.frame,font=("Consolas",12),wrap="word")
        else:
            from tkinter import scrolledtext; self.history=scrolledtext.ScrolledText(self.frame,font=("Consolas",12),wrap="word")
        self.history.pack(fill="both",expand=True,padx=8,pady=6); self.history.insert("end","JuprisX Web Agent ready. Contoh: bikin game platformer HTML5 | generate icon | build AAB\n\n")
        inp=Frame(self.frame,fg_color="transparent") if USE_CTK else Frame(self.frame); inp.pack(fill="x",padx=8,pady=(0,10)); self.entry=Entry(inp,font=("Segoe UI",12)); self.entry.pack(side="left",fill="x",expand=True,padx=(0,6)); self.entry.bind("<Return>",lambda _:self._send()); Button(inp,text="Send",width=80,command=self._send).pack(side="right")
        self._refresh(); self.frame.after(100,self._poll); threading.Thread(target=self._ping,daemon=True).start()

    def set_mode(self,mode): self.ctx.set_mode(mode); self._refresh()
    def set_project(self,project):
        self.ctx.set_project(project)
        if project and self.ctx.mode=="General Chat": self.ctx.set_mode("Project Context")
        self._refresh()
    def set_working_dir(self,path): self.ctx.set_working_dir(path); self._refresh()
    def _refresh(self):
        for m,b in self.buttons.items(): b.configure(text=("● " if m==self.ctx.mode else "")+m)
        self.status.configure(text=f"{'● MCP online' if self.engine.mcp_online else '○ MCP offline'} | {self.ctx.mode} | {self.ctx.project.get('name') if self.ctx.project else '-'}")
    def _append(self,text): self.history.insert("end",text); self.history.see("end")
    def receive_message(self,text): self._append(f"AI: {text}\n\n")
    def send_message(self,message):
        message=(message or "").strip()
        if not message or self._busy:return
        self._append(f"You: {message}\n"); self._busy=True; threading.Thread(target=self._worker,args=(message,),daemon=True).start()
    def _worker(self,message):
        try:r=self.engine.handle(message)
        except Exception as exc:r=Reply(f"Error: {exc}")
        self._q.put(r)
    def _ping(self): self.engine.ping(); self._q.put(None)
    def _poll(self):
        try:
            while True:
                item=self._q.get_nowait()
                if item is None:self._refresh(); continue
                self._busy=False; self.receive_message(item.text); self._run_action(item)
        except queue.Empty:pass
        self.frame.after(100,self._poll)
    def _run_action(self,r):
        sv=self.services
        if r.action in {"scan","keystore","build","assets","setup_env","auto_fix"}:
            fn=getattr(sv,{"scan":"scan","keystore":"keystore","build":"build","assets":"open_assets","setup_env":"setup_env","auto_fix":"auto_fix"}[r.action],None)
            if fn:fn()
        elif r.action=="stage_edits" and sv.stage_edits:sv.stage_edits(r.data.get("edits",[]))
        elif r.action=="create_project":self._pending=r.data; self._pick_folder()
    def attach_folder(self):
        from tkinter import filedialog
        folder=filedialog.askdirectory(title="Select HTML/JS project folder")
        if folder and self.services.attach_folder:self.set_project(self.services.attach_folder(folder))
    def _pick_folder(self):
        from tkinter import filedialog
        initial=self.services.default_projects_dir() if self.services.default_projects_dir else None
        folder=filedialog.askdirectory(title="Save web project",initialdir=initial,mustexist=False)
        if folder:self._create(folder)
    def _create(self,folder):
        if not self._pending or not self.services.create_project:return
        data=self._pending; project=self.services.create_project(data["name"],folder,data["files"]); self._pending=None; self.set_project(project); self.receive_message(f"Project saved: {project['working_dir']}")
    def _send(self):
        msg=self.entry.get(); self.entry.delete(0,"end"); self.send_message(msg)
