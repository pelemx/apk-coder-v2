"""Offline HTML5 project templates used when MCP is unreachable."""
from __future__ import annotations


def _safe_title(name: str) -> str:
    return (name or "HTML5 App").strip().replace('"', "'")[:80]


def build_template(name: str) -> dict[str, str]:
    """Return a minimal offline-first HTML/CSS/JS Android-ready project."""
    title = _safe_title(name)
    html = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
  <meta name="theme-color" content="#181a21">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main id="app" aria-label="{title}">
    <canvas id="game" aria-label="Game canvas"></canvas>
  </main>
  <script src="app.js" defer></script>
</body>
</html>
'''
    css = '''* { box-sizing: border-box; }
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
body { background: #181a21; color: #fff; font-family: system-ui, sans-serif; touch-action: none; -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
#app { width: 100%; height: 100%; display: grid; place-items: center; padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
#game { display: block; width: 100%; height: 100%; }
'''
    js = f'''"use strict";

const App = {{
  canvas: null,
  ctx: null,
  running: false,
  init() {{
    this.canvas = document.getElementById("game");
    this.ctx = this.canvas.getContext("2d");
    this.resize();
    window.addEventListener("resize", () => this.resize(), {{ passive: true }});
    window.addEventListener("orientationchange", () => this.resize(), {{ passive: true }});
    this.canvas.addEventListener("pointerdown", this.onPointer.bind(this), {{ passive: false }});
    this.canvas.addEventListener("pointermove", this.onPointer.bind(this), {{ passive: false }});
    this.canvas.addEventListener("pointerup", this.onPointer.bind(this), {{ passive: false }});
    this.canvas.addEventListener("pointercancel", this.onPointer.bind(this), {{ passive: false }});
    document.addEventListener("visibilitychange", () => {{
      this.running = document.visibilityState === "visible";
    }});
    this.running = true;
    requestAnimationFrame((t) => this.frame(t));
  }},
  resize() {{
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(innerWidth * dpr);
    this.canvas.height = Math.floor(innerHeight * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }},
  onPointer(event) {{
    event.preventDefault();
    // AI-generated app/game input goes here.
  }},
  frame(time) {{
    if (this.running) {{
      const w = innerWidth, h = innerHeight;
      this.ctx.clearRect(0, 0, w, h);
      this.ctx.fillStyle = "#181a21";
      this.ctx.fillRect(0, 0, w, h);
      this.ctx.fillStyle = "#ffffff";
      this.ctx.textAlign = "center";
      this.ctx.font = "20px system-ui";
      this.ctx.fillText({title!r}, w / 2, h / 2);
    }}
    requestAnimationFrame((t) => this.frame(t));
  }}
}};

document.addEventListener("DOMContentLoaded", () => App.init(), {{ once: true }});
'''
    manifest = f'''{{
  "name": {title!r},
  "short_name": {title!r},
  "start_url": "./index.html",
  "display": "fullscreen",
  "background_color": "#181a21",
  "theme_color": "#181a21"
}}
'''.replace("'", '"')
    return {
        "index.html": html,
        "app.js": js,
        "style.css": css,
        "manifest.json": manifest,
        "assets/.gitkeep": "",
    }
