#!/usr/bin/env python3
"""Barra de temps: hora gran en local, UTC en petit.  Ús: python3 scripts/patch_hora_local.py index.html
Idempotent i prudent: si no troba exactament el que espera, no escriu res."""
import shutil, sys, time
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "index.html")
s = p.read_text(encoding="utf-8")
if 'id="ts-utc"' in s:
    print("Ja aplicat: no cal fer res")
    raise SystemExit(0)

html_vell = '<span class="ts"><span class="date" id="ts-date">--/--/----</span><span id="ts-time">--:--</span> UTC</span>'
html_nou = ('<span class="ts"><span class="date" id="ts-date">--/--/----</span><span id="ts-time">--:--</span>'
            '<span style="font-size:12px;font-weight:400;color:var(--text-dim);margin-left:6px">hora local</span>'
            '<span id="ts-utc" style="font-size:12px;font-weight:400;color:var(--text-dim);margin-left:8px">--:-- UTC</span></span>')
js_vell = """    const { date, time } = fmtTs(ts);
    tsDate.textContent = date;
    tsTime.textContent = time;
"""
js_nou = """    const { time: horaUtc } = fmtTs(ts);
    // hora de Catalunya (Europe/Madrid), amb horari d'estiu/hivern, sigui quin sigui el fus del navegador
    const pc = {}; new Intl.DateTimeFormat('ca-ES', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(tsToDate(ts)).forEach(x => { pc[x.type] = x.value; });
    tsDate.textContent = `${pc.day}/${pc.month}/${pc.year}`;
    tsTime.textContent = `${pc.hour}:${pc.minute}`;
    const tu = document.getElementById('ts-utc'); if (tu) tu.textContent = `${horaUtc} UTC`;
"""
errs = []
if s.count(html_vell) != 1:
    errs.append("no trobo la capçalera de la barra de temps (HTML)")
if s.count(js_vell) != 1:
    errs.append("no trobo el bloc de showFrame() que escriu l'hora")
if errs:
    raise SystemExit("ABORT, no escric res: " + "; ".join(errs))
bk = Path.home() / f"index.html.backup-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy(p, bk)
p.write_text(s.replace(html_vell, html_nou).replace(js_vell, js_nou), encoding="utf-8")
print("OK, hora local aplicada | còpia:", bk)
