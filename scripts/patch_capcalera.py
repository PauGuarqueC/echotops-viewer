#!/usr/bin/env python3
"""Capçalera amb l'estil dels altres visors (Finestra de Crema, Visor de sondes): fons blanc, vora fina,
títol 18 px en negreta amb un mot en vermell, subtítol gris i botons de contorn.
Ús: python3 scripts/patch_capcalera.py index.html   (idempotent; si no troba el que espera, no escriu res)"""
import shutil, sys, time
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "index.html")
s = p.read_text(encoding="utf-8")
if 'id="estil-capcalera"' in s:
    print("Ja aplicat: no cal fer res")
    raise SystemExit(0)

html_vell = """      <span class="mark">BOMBERS · GRAF</span>
      <h1>Echo Tops<span class="subtitle">&nbsp;/ dades Meteocat</span></h1>"""
html_nou = """      <h1>Echo <span class="nom">Tops</span><span class="subtitle">dades Meteocat</span></h1>"""
css = """<style id="estil-capcalera">
  /* Capçalera com la dels altres visors del GRAF */
  #topbar{ background:var(--panel); border-bottom:1px solid var(--panel-border); box-shadow:none; padding:12px 20px; }
  #topbar .brand{ gap:14px; }
  #topbar h1{ font-size:18px; font-weight:700; letter-spacing:0; color:var(--charcoal); display:flex; align-items:baseline; gap:12px; }
  #topbar h1 .nom{ color:var(--red); margin-left:-8px; }
  #topbar .subtitle{ font-size:12.5px; font-weight:400; color:var(--text-dim); margin:0; }
  #status{ color:var(--text-dim); background:#fafafa; border:1px solid var(--panel-border); font-size:12px; }
  #status .dot.stale{ background:#b5b5b5; }
  #analysis-btn, #export-btn{
    font-family:var(--font-mono); font-size:12px; font-weight:400; color:var(--text-dim); background:var(--panel);
    border:1px solid var(--panel-border); border-radius:5px; padding:6px 12px;
  }
  #analysis-btn:hover, #export-btn:hover{ background:var(--panel); color:var(--red); border-color:var(--red); }
  #analysis-btn.active, #export-btn.active{ background:var(--panel); color:var(--red); border-color:var(--red); }
  #date-select{ font-family:var(--font-mono); font-size:12px; color:var(--charcoal); background:#fafafa;
    border:1px solid var(--panel-border); border-radius:5px; padding:5px 8px; margin-left:0; }
  #live-btn{ font-family:var(--font-mono); font-size:12px; font-weight:400; color:var(--red); background:var(--panel);
    border:1px solid var(--red); border-radius:5px; padding:6px 12px; margin-left:0; }
  #live-btn:hover{ background:var(--red); color:#fff; }
</style>
"""
errs = []
if s.count(html_vell) != 1:
    errs.append("no trobo l'HTML de la capçalera")
if s.count("</head>") != 1:
    errs.append("no trobo </head>")
if errs:
    raise SystemExit("ABORT, no escric res: " + "; ".join(errs))
bk = Path.home() / f"index.html.backup-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy(p, bk)
p.write_text(s.replace(html_vell, html_nou).replace("</head>", css + "</head>"), encoding="utf-8")
print("OK, capçalera aplicada | còpia:", bk)
