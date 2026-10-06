"""Offline HTML5/JS/CSS project templates used when MCP is unavailable."""
from __future__ import annotations


def build_template(name: str) -> dict[str, str]:
    """Return a complete offline-first HTML5 starter project."""
    title = (name or "HTML5 Game").strip().title()
    safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#181a21">
<title>{safe}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main id="app" aria-label="{safe}">
<section class="card">
<h1>{safe}</h1>
<p id="question">Tap Start untuk mulai.</p>
<div id="answers" class="answers"></div>
<button id="start" type="button">Start</button>
<p id="score">Skor: 0</p>
</section>
</main>
<script src="app.js" defer></script>
</body>
</html>
'''
    js = '''(() => {
"use strict";
const $ = id => document.getElementById(id);
const question = $("question"), answers = $("answers"), start = $("start"), scoreEl = $("score");
let score = 0, answer = 0;
function nextRound() {
  const a = Math.floor(Math.random() * 20) + 1, b = Math.floor(Math.random() * 20) + 1;
  answer = a + b; question.textContent = `${a} + ${b} = ?`; answers.replaceChildren();
  const options = new Set([answer]);
  while (options.size < 4) options.add(Math.max(0, answer + Math.floor(Math.random() * 11) - 5));
  [...options].sort(() => Math.random() - 0.5).forEach(value => {
    const button = document.createElement("button"); button.type = "button"; button.className = "answer"; button.textContent = String(value);
    button.addEventListener("click", () => { if (Number(value) === answer) score++; scoreEl.textContent = `Skor: ${score}`; nextRound(); }, {passive:true});
    answers.appendChild(button);
  });
}
start.addEventListener("click", () => { score = 0; scoreEl.textContent = "Skor: 0"; start.hidden = true; nextRound(); }, {passive:true});
window.addEventListener("popstate", () => {});
})();
'''
    css = '''*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;min-height:100%;background:#181a21;color:#fff}body{min-height:100dvh;overflow:hidden;font-family:system-ui,sans-serif;user-select:none}#app{min-height:100dvh;display:grid;place-items:center;padding:20px}.card{width:min(92vw,520px);padding:24px;border-radius:24px;background:#242833;text-align:center}h1{font-size:clamp(24px,7vw,42px)}button{min-height:52px;border:0;border-radius:14px;padding:12px 20px;font-size:18px;font-weight:700;touch-action:manipulation}.answers{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0}.answer{background:#3b4252;color:#fff}#start{width:100%;background:#5b8cff;color:#fff}#score{font-weight:700}
'''
    import json
    manifest = json.dumps({"name": title, "short_name": title[:30], "start_url": "./index.html", "display": "standalone", "background_color": "#181a21", "theme_color": "#181a21"}, ensure_ascii=False, indent=2) + "\n"
    return {"index.html": html, "app.js": js, "style.css": css, "manifest.json": manifest, "assets/.gitkeep": ""}
