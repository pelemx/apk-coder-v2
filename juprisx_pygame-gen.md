# JuprisX Pygame Agentic Desktop

**Agentic Pygame Code Compatibility → APK/AAB Play Store Ready**

---

## OVERVIEW & CORE RULE

```text
BUILDER          = FIXED (immutable)
PYGAME CODE      = ADAPTIVE
JUprisX AGENT    = ANALYZER + PLANNER + CODER + FIXER + VALIDATOR
```

Aplikasi ini **bukan** Builder.  
Aplikasi ini adalah **Agentic Client** yang:

1. Menerima project Pygame
2. Memeriksa compatibility terhadap Builder (WSL + fixed runtime)
3. Memperbaiki source code (bukan builder)
4. Generate keystore + compile ke APK/AAB
5. Siap upload Play Store

---

## PART 1 — BUILDER → CODE → APK / AAB / KEYSTORE

**Tujuan Part ini:**  
Memmbuat Dari Awal code atau Mengubah project Pygame yang sudah valid menjadi **Play Store ready package**.

### 1.1 Keystore Generation

```bash
keytool -genkey -v \
  -keystore my-release-key.jks \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -alias juprisx-release
```

**Yang harus disimpan di Project JSON:**
- Path keystore
- Alias
- Store password
- Key password
- Tanggal generate

> Keystore **tidak boleh hilang**. Satu keystore untuk selamanya (update Play Store).

### 1.2 WSL Checker (Wajib)

Fungsi yang harus ada:

```python
def check_wsl_environment() -> dict:
    """
    Return:
    {
      "is_wsl": bool,
      "python_version": str,
      "pygame_installed": bool,
      "jdk_available": bool,
      "android_sdk": bool,
      "buildozer_available": bool,
      "errors": list
    }
    """
```

Checklist minimal:
- Apakah di dalam WSL?
- Python version sesuai Builder
- pygame tersedia
- JDK (untuk keytool + signing)
- Android SDK / Buildozer (untuk compile APK/AAB)
- Permission folder project

### 1.3 Compile Pipeline

```text
Project Folder (sudah di-fix)
        │
        ▼
Generate / Load Keystore
        │
        ▼
Prepare buildozer.spec / gradle
        │
        ▼
buildozer android release   (atau gradle)
        │
        ▼
Output:
  - app-release.apk
  - app-release.aab
  - keystore.jks
```

### 1.4 Final Deliverables (Part 1)

| File              | Keterangan                          |
|-------------------|-------------------------------------|
| `*.apk`           | Installable                         |
| `*.aab`           | Play Store preferred                |
| `*.jks` / keystore| Signing key                         |
| `project.json`    | Metadata + password (encrypted)     |

---

## PART 2 — CODE GENERATOR / REFIXED (AGENTIC LOOP)

**Tujuan Part ini:**  
Menerima request game → generate code → loop fix sampai compatible dengan Builder.

### 2.1 Agentic Loop (Wajib)

```text
SCAN
 ↓
UNDERSTAND
 ↓
CHECK BUILDER CONSTRAINT
 ↓
CHECK WSL
 ↓
CHECK DEPENDENCIES
 ↓
FIND PROBLEMS
 ↓
BUILD FIX PLAN
 ↓
APPLY PATCH (bukan rewrite total)
 ↓
VALIDATE
 ↓
RE-SCAN
 ↓
FINAL RESULT
```

### 2.2 Builder Contract (Immutable)

```json
{
  "name": "JuprisX Pygame Builder",
  "version": "1.0",
  "runtime": {
    "os": "WSL",
    "python": "fixed",
    "pygame": "fixed"
  },
  "filesystem": {
    "working_directory": "project_root",
    "windows_absolute_paths": false,
    "case_sensitive": true
  },
  "pygame": {
    "display": "builder_managed",
    "resolution": "builder_managed",
    "font_system": "bundled_fonts",
    "audio": "builder_managed"
  },
  "rules": [
    "Do not modify builder",
    "Do not require Windows-only APIs",
    "Do not assume host-installed fonts",
    "Do not use hardcoded absolute paths",
    "Use project-relative assets"
  ]
}
```

### 2.3 MCP Entry Point

```json
{
  "jsonrpc": "2.0",
  "id": "chat-001",
  "method": "tools/call",
  "params": {
    "name": "jupris_agentic_brain",
    "arguments": {
      "prompt": "bikin game pygame tebak warna",
      "intent": "generate_game"
    }
  }
}
```

### 2.4 Skill & RAG Usage

```text
jupris_list_skills
        ↓
jupris_load_skill
        ↓
RAG / DSS Response
        ↓
Generate Code (referensi skill)
```

### 2.5 Patch Style (Preferensi)

```diff
--- game.py
+++ game.py
@@
- font = pygame.font.SysFont("Arial", 32)
+ font = pygame.font.Font(str(FONT_PATH), 32)
```

Jangan rewrite seluruh file kalau patch lokal sudah cukup.

### 2.6 Backup & Rollback

```text
project/
.juprisx/
    backup/
    patches/
    reports/
```

---

## PART 3 — PROJECT DATA / TABLE / WORKFLOW / REVIEWER

**Tujuan Part ini:**  
Menyimpan state project, history, dan review sebelum compile.

### 3.1 Project JSON Structure

```json
{
  "project_id": "uuid",
  "name": "Tebak Warna",
  "created_at": "2026-10-03T21:00:00",
  "working_dir": "/home/user/projects/tebak-warna",
  "status": "ready_to_build",
  "keystore": {
    "path": "release.jks",
    "alias": "juprisx-release",
    "store_password": "encrypted...",
    "key_password": "encrypted..."
  },
  "findings": [],
  "patches_applied": [],
  "validation": {
    "syntax": true,
    "imports": true,
    "pygame": true,
    "wsl": true,
    "builder": true
  },
  "build": {
    "apk": null,
    "aab": null,
    "last_build": null
  }
}
```

### 3.2 Project Table (GUI)

| ID | Nama Project     | Status          | Last Scan | Action          |
|----|------------------|-----------------|-----------|-----------------|
| 1  | Tebak Warna      | ready_to_build  | 21:30     | Review / Build  |
| 2  | Snake Classic    | needs_fix      | 20:15     | Fix             |

### 3.3 Workflow States

```text
NEW
 ↓
SCANNING
 ↓
NEEDS_FIX
 ↓
PLAN_READY
 ↓
FIXED
 ↓
VALIDATED
 ↓
READY_TO_BUILD
 ↓
BUILDING
 ↓
PLAYSTORE_READY
```

### 3.4 Reviewer Panel

Sebelum AUTO FIX atau BUILD, user harus bisa melihat:

- Findings (HIGH / MED / LOW)
- Diff (Original vs Fixed)
- Validation result
- Tombol: Approve / Reject / Rollback

---

## PART 4 — CHAT TAB (DISKUSI + WORKING DIR)

**Tujuan Part ini:**  
Chat yang sadar context project.

### 4.1 Fitur Utama

- Bisa chat biasa (diskusi)
- Bisa **attach / pilih Working Directory** project
- AI otomatis paham project mana yang sedang dibahas
- Bisa mulai **project baru** dari chat

### 4.2 Mode Chat

| Mode              | Keterangan                                      |
|-------------------|-------------------------------------------------|
| General Chat      | Diskusi bebas (tidak terikat project)           |
| Project Context   | Chat terikat ke working_dir yang aktif          |
| New Project       | Dari chat langsung generate project baru        |

### 4.3 Hybrid Chat Engine

```text
Intent.SIMPLE   → Qwen 1.5B lokal (< 1 detik)
Intent.COMPLEX  → Escalate ke Bimbo → Jupris R9
Intent.TOOL     → Escalate + tool execution
```

### 4.4 Contoh Flow

```text
User: "oke bikin game pygame tebak-tebakan warna"
AI  : (deteksi intent generate_game)
     → Load skill
     → Generate code
     → Tanya: "Mau simpan di folder mana?"
User: pilih / buat working_dir
AI  : simpan project + update Project Table
```

### 4.5 MCP Status di Chat Tab

```text
● Connected
Engine: Qwen2.5-Coder-1.5B
Working Dir: /home/user/projects/tebak-warna
```

---

## PART 5 — COMPONENT GENERATOR (ICON + PLAYSTORE ASSETS)

**Tujuan Part ini:**  
Generate icon dan asset Play Store berdasarkan data game.

### 5.1 Custom API Bridge (Wajib)

```python
API_URL = "http://100.118.242.120:4333"
API_KEY = "Sahar_Sec_9921_X"
```

### 5.2 Generate Image Function

```python
def generate_image_thread(self, prompt, label_widget, dimension):
    label_widget.configure(text="Generating...\nLoading Image", image=None)
    try:
        url = f"{API_URL}/generate_image"
        headers = {"x-internal-key": API_KEY}
        payload = {"prompt": prompt}
        response = requests.post(url, json=payload, headers=headers, timeout=120.0)
        response.raise_for_status()
        
        data = response.json()
        b64_out = data.get("image_base64", "")
        
        if not b64_out:
            raise ValueError("Payload base64 kosong dari server")
        img_bytes = base64.b64decode(b64_out)
        image = Image.open(io.BytesIO(img_bytes))
        
        label_widget.original_image = image
        
        aspect_ratio = "9:16" if "9:16" in dimension else "16:9"
        if aspect_ratio == "9:16":
            preview_image = image.resize((170, 300))
        else:
            preview_image = image.resize((300, 170))
        
        ctk_image = ctk.CTkImage(
            light_image=preview_image,
            dark_image=preview_image,
            size=preview_image.size
        )
        label_widget.configure(image=ctk_image, text="")
    except Exception as e:
        print(f"Error Image Gen: {e}")
        label_widget.configure(text="Gagal.\nKlik Retry.")
```

### 5.3 Save Image

```python
def save_image(self, label_widget, scene_num):
    if hasattr(label_widget, 'original_image') and label_widget.original_image:
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            initialfile=f"Scene_{scene_num}.jpg",
            title="Save Image",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")]
        )
        if filepath:
            label_widget.original_image.save(filepath)
            self.lbl_status.configure(text=f"Gambar Scene {scene_num} berhasil disimpan.")
```

### 5.4 Input untuk Icon Generation

Prompt dibangun dari:
- Nama game
- Deskripsi singkat
- Genre
- Warna dominan (dari pygame data)
- Style (flat, cartoon, pixel, dll)

Contoh prompt:
```text
App icon for Android game "Tebak Warna", 
color guessing game, bright colorful, 
flat design, high contrast, 
Play Store style, no text
```

### 5.5 Play Store Asset Checklist

| Asset                  | Size / Ratio     | Sumber                  |
|------------------------|------------------|-------------------------|
| App Icon               | 512×512          | Generate + auto-cut     |
| Feature Graphic        | 1024×500         | Generate                |
| Phone Screenshot       | 16:9 / 9:16      | Manual / Generate       |
| Promo Video (opsional) | -                | External                |

---

## RECOMMENDED FOLDER STRUCTURE (untuk coding per Part)

```text
juprisx_pygame_agent/
│
├── main.py
├── config.json
│
├── part1_builder/               # Part 1
│   ├── keystore.py
│   ├── wsl_checker.py
│   ├── compiler.py
│   └── buildozer_helper.py
│
├── part2_generator/             # Part 2
│   ├── agent_client.py
│   ├── analyzer.py
│   ├── planner.py
│   ├── fixer.py
│   ├── validator.py
│   └── prompts.py
│
├── part3_project/               # Part 3
│   ├── project_manager.py
│   ├── project_table.py
│   ├── workflow.py
│   └── reviewer.py
│
├── part4_chat/                  # Part 4
│   ├── chat_tab.py
│   ├── context_manager.py
│   └── hybrid_engine.py
│
├── part5_assets/                # Part 5
│   ├── icon_generator.py
│   ├── api_bridge.py
│   └── playstore_assets.py
│
├── gui/                         # Digabung belakangan
│   ├── app.py
│   ├── project_panel.py
│   ├── findings_panel.py
│   ├── diff_panel.py
│   └── log_panel.py
│
└── workspace/
```

---

## URUTAN KERJA YANG DISARANKAN

1. **Part 2** dulu (Generator + Agentic Loop) → biar bisa generate & fix code
2. **Part 3** (Project Data + Table) → simpan state
3. **Part 1** (Builder → APK/AAB/Keystore) → compile
4. **Part 5** (Icon Generator) → asset Play Store
5. **Part 4** (Chat Tab) → integrasi semuanya lewat chat
6. Baru gabung ke **GUI** utama

---

## MCP SERVER (Referensi)

```text
Server : http://100.118.242.120:3333
Auth   : X-API-Key: <API_KEY>

Core Tools:
- jupris_agentic_brain
- jupris_data_receiver
- jupris_list_skills
- jupris_load_skill
```

---

## CATATAN PENTING

- Builder **tidak boleh** diubah
- Semua path harus project-relative
- Font harus bundled
- Keystore harus di-backup aman
- Setiap Part harus bisa di-test mandiri sebelum digabung
```
================
need Update
icon generator can genearte icon/ image for APP/ agems pygame for use in game --
