"""
Assets panel (Part 5 GUI): generate / import images, preview, save as Play Store
assets into <project>/playstore_assets/, and show the Play Store checklist.

Network calls run in worker threads; results return to the UI thread through a
queue polled with after(), so no widget is touched from a worker thread.
"""
from __future__ import annotations

import queue
from typing import Any, Callable, Optional

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    import tkinter as ctk
    USE_CTK = False

import tkinter as tk

from PIL import Image, ImageTk

from .api_bridge import generate_image_thread
from .icon_generator import GENRES, STYLES, IconGenerator
from .playstore_assets import PlaystoreAssets, load_image

PREVIEW_BOX = (200, 200)
SLOTS = [
    ("icon", "App Icon (512x512)"),
    ("feature_graphic", "Feature Graphic (1024x500)"),
    ("screenshot", "Phone Screenshot"),
]


class _Slot:
    def __init__(self, kind: str):
        self.kind = kind
        self.image: Optional[Image.Image] = None
        self.preview_ref: Any = None
        self.preview_lbl: Any = None
        self.prompt_entry: Any = None
        self.generate_btn: Any = None


class AssetsPanel:
    """
    project_getter() -> project dict | None
    on_saved(kind, path)  called after an asset file was written
    on_log(msg)           optional
    """

    def __init__(self, parent, project_getter: Callable[[], Optional[dict]],
                 on_saved: Optional[Callable[[str, str], None]] = None,
                 on_log: Optional[Callable[[str], None]] = None):
        self.project_getter = project_getter
        self.on_saved = on_saved
        self.on_log = on_log
        self._q: queue.Queue = queue.Queue()
        self.slots = {k: _Slot(k) for k, _ in SLOTS}

        Frame = ctk.CTkFrame if USE_CTK else ctk.Frame
        Label = ctk.CTkLabel if USE_CTK else ctk.Label
        Button = ctk.CTkButton if USE_CTK else ctk.Button
        Entry = ctk.CTkEntry if USE_CTK else ctk.Entry

        self.frame = Frame(parent, corner_radius=8) if USE_CTK else Frame(parent)
        Label(self.frame, text="Play Store Assets", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 2))
        self.project_lbl = Label(self.frame, text="Project: -", anchor="w")
        self.project_lbl.pack(fill="x", padx=10)

        # ---- inputs -----------------------------------------------------
        form = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        form.pack(fill="x", padx=8, pady=6)
        Label(form, text="Deskripsi").grid(row=0, column=0, sticky="w", padx=4)
        self.desc_entry = Entry(form, width=260 if USE_CTK else 40)
        self.desc_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=4, pady=2)
        Label(form, text="Genre").grid(row=1, column=0, sticky="w", padx=4)
        self.genre_var = tk.StringVar(value=GENRES[0])
        self._option_menu(form, self.genre_var, GENRES).grid(row=1, column=1, sticky="w", padx=4)
        Label(form, text="Style").grid(row=1, column=2, sticky="w", padx=4)
        self.style_var = tk.StringVar(value=STYLES[0])
        self._option_menu(form, self.style_var, STYLES).grid(row=1, column=3, sticky="w", padx=4)
        form.columnconfigure(1, weight=1)
        Button(form, text="Build Prompts", width=120, command=self.build_prompts).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=4, pady=4)

        # ---- slots ------------------------------------------------------
        row = Frame(self.frame, fg_color="transparent") if USE_CTK else Frame(self.frame)
        row.pack(fill="x", padx=8, pady=4)
        for kind, title in SLOTS:
            slot = self.slots[kind]
            col = Frame(row, corner_radius=6) if USE_CTK else Frame(row, bd=1, relief="groove")
            col.pack(side="left", fill="y", padx=4)
            Label(col, text=title, font=("Segoe UI", 11, "bold")).pack(padx=6, pady=(6, 2))
            slot.preview_lbl = (Label(col, text="(belum ada gambar)", width=210, height=210)
                                if USE_CTK else Label(col, text="(belum ada gambar)", width=26, height=10))
            slot.preview_lbl.pack(padx=6, pady=2)
            if kind == "screenshot":
                self.ratio_var = tk.StringVar(value="9:16")
                self._option_menu(col, self.ratio_var, ["9:16", "16:9"]).pack(pady=2)
            slot.prompt_entry = Entry(col, width=200 if USE_CTK else 28)
            slot.prompt_entry.pack(padx=6, pady=2)
            btns = Frame(col, fg_color="transparent") if USE_CTK else Frame(col)
            btns.pack(pady=(2, 6))
            slot.generate_btn = Button(btns, text="Generate", width=70,
                                       command=lambda k=kind: self.generate(k))
            slot.generate_btn.pack(side="left", padx=2)
            Button(btns, text="Import", width=60, command=lambda k=kind: self.import_image(k)).pack(
                side="left", padx=2)
            Button(btns, text="Save", width=60, command=lambda k=kind: self.save(k)).pack(
                side="left", padx=2)

        # ---- checklist + status ----------------------------------------
        self.check_lbl = Label(self.frame, text="", anchor="w", justify="left",
                               font=("Consolas", 11))
        self.check_lbl.pack(fill="x", padx=10, pady=(6, 2))
        self.status_lbl = Label(self.frame, text="", anchor="w")
        self.status_lbl.pack(fill="x", padx=10, pady=(0, 10))

        self.frame.after(100, self._poll)
        self.refresh()

    # ------------------------------------------------------------------
    @staticmethod
    def _option_menu(parent, var, values):
        if USE_CTK:
            return ctk.CTkOptionMenu(parent, values=list(values), variable=var, width=140)
        return tk.OptionMenu(parent, var, *values)

    def _project(self) -> Optional[dict]:
        return self.project_getter()

    def _say(self, msg: str):
        self.status_lbl.configure(text=msg)
        if self.on_log:
            self.on_log(msg)

    def _entry_text(self, entry) -> str:
        return entry.get().strip()

    # ---- public ------------------------------------------------------
    def refresh(self):
        """Call when the active project changes."""
        proj = self._project()
        self.project_lbl.configure(text=f"Project: {proj['name']}" if proj else "Project: - (pilih dulu)")
        if proj:
            rows = PlaystoreAssets(proj["working_dir"]).checklist()
            self.check_lbl.configure(text="\n".join(
                f"[{r['status']:<4}] {r['asset']:<18} {r['requirement']:<22} {r['detail']}" for r in rows))
        else:
            self.check_lbl.configure(text="")

    def build_prompts(self):
        proj = self._project()
        if not proj:
            self._say("Pilih project dulu.")
            return
        gen = IconGenerator(proj)
        prompts = gen.build_prompts(
            self._entry_text(self.desc_entry), self.genre_var.get(), self.style_var.get(),
            self.ratio_var.get())
        for kind, text in prompts.items():
            e = self.slots[kind].prompt_entry
            e.delete(0, "end")
            e.insert(0, text)
        self._say("Prompt dibuat dari data project (nama, genre, warna dominan, style). Boleh diedit.")

    def generate(self, kind: str):
        slot = self.slots[kind]
        if not self._project():
            self._say("Pilih project dulu.")
            return
        if not self._entry_text(slot.prompt_entry):
            self.build_prompts()
        prompt = self._entry_text(slot.prompt_entry)
        slot.generate_btn.configure(state="disabled")
        self._say(f"Generating {kind} ...")
        generate_image_thread(
            prompt,
            on_done=lambda img, k=kind: self._q.put((k, "ok", img)),
            on_error=lambda msg, k=kind: self._q.put((k, "err", msg)),
        )

    def import_image(self, kind: str):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Pilih gambar", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")])
        if not path:
            return
        try:
            self._set_image(kind, load_image(path))
            self._say(f"Gambar dimuat: {path}")
        except Exception as exc:  # noqa: BLE001
            self._say(f"Gagal membuka gambar: {exc}")

    def save(self, kind: str):
        proj = self._project()
        slot = self.slots[kind]
        if not proj:
            self._say("Pilih project dulu.")
            return
        if slot.image is None:
            self._say("Belum ada gambar. Generate atau Import dulu.")
            return
        pa = PlaystoreAssets(proj["working_dir"])
        try:
            if kind == "icon":
                path = pa.save_app_icon(slot.image)
                if pa.apply_icon_to_buildozer_spec(path):
                    self._say(f"Icon disimpan & buildozer.spec diperbarui: {path}")
                else:
                    self._say(f"Icon disimpan: {path}")
            elif kind == "feature_graphic":
                path = pa.save_feature_graphic(slot.image)
                self._say(f"Feature graphic disimpan: {path}")
            else:
                path = pa.save_phone_screenshot(slot.image, self.ratio_var.get())
                self._say(f"Screenshot disimpan: {path}")
        except Exception as exc:  # noqa: BLE001
            self._say(f"Gagal menyimpan: {exc}")
            return
        if self.on_saved:
            self.on_saved(kind, path)
        self.refresh()

    # ---- internals ---------------------------------------------------
    def _set_image(self, kind: str, image: Image.Image):
        slot = self.slots[kind]
        slot.image = image
        thumb = image.copy().convert("RGBA")
        thumb.thumbnail(PREVIEW_BOX)
        if USE_CTK:
            ref = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
        else:
            ref = ImageTk.PhotoImage(thumb)
        slot.preview_ref = ref  # keep a reference or Tk drops the image
        slot.preview_lbl.configure(image=ref, text="")

    def _poll(self):
        try:
            while True:
                kind, status, payload = self._q.get_nowait()
                self.slots[kind].generate_btn.configure(state="normal")
                if status == "ok":
                    self._set_image(kind, payload)
                    self._say(f"{kind} selesai. Cek preview lalu Save.")
                else:
                    self._say(f"Gagal generate {kind}: {payload}")
        except queue.Empty:
            pass
        self.frame.after(100, self._poll)
