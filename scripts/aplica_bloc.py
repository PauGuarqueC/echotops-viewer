#!/usr/bin/env python3
"""
Aplica el bloc de nowcasting a l'index.html de manera idempotent i segura:
  1. treu el bloc antic de "Persistència de precipitació" (si hi és)
  2. substitueix el bloc de "Tempestes enganxades" (qualsevol versió anterior) pel nou, o l'insereix si no n'hi ha
  3. assegura la crida nowcMostra(ts) a showFrame()
No escriu res si alguna comprovació falla. Abans d'escriure, fa una còpia a ~/index.html.backup-AAAAMMDD-HHMMSS.

Ús:  python3 scripts/aplica_bloc.py index.html scripts/bloc_nowcast.js
"""
import shutil, sys, time
from pathlib import Path

INI_PERSIST = "  // ---- Persistència de precipitació"
FI_PERSIST = "openOn(map);\n  });\n"
INI_NOWC = "  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----\n"
FINS_NOWC = ["  // ---- fi Tempestes enganxades ----\n",                                           # versió actual
             "nowc.timer = setInterval(async () => { await nowcCarrega(); nowcMostra(); }, 2 * 60 * 1000);\n",  # versió amb reflectivitat
             "  nowcActiva(true);\n"]                                                            # primera versió
ANCORA = "  map.addControl(new BasemapControl());\n"
HOOK_ANC = "    currentTs = ts;\n"
HOOK = "    if (typeof nowcMostra === 'function') nowcMostra(ts);\n"


def surt(msg):
    sys.exit(f"No toco res: {msg}")


def main():
    if len(sys.argv) != 3:
        surt("ús: aplica_bloc.py index.html bloc_nowcast.js")
    f, bf = Path(sys.argv[1]), Path(sys.argv[2])
    s, bloc = f.read_text(), bf.read_text()
    if len(s) < 10000:
        surt(f"{f} és massa petit ({len(s)} caràcters); sembla buit o trencat")
    if not bloc.endswith("  // ---- fi Tempestes enganxades ----\n"):
        surt("el bloc no acaba amb el marcador esperat; no és la versió actual")
    orig = s
    resum = []

    # 1) persistència antiga
    n = 0
    while INI_PERSIST in s:
        i = s.index(INI_PERSIST)
        j = s.find(FI_PERSIST, i)
        if j < 0:
            surt("trobo l'inici del bloc de persistència però no el final")
        j += len(FI_PERSIST)
        vell = s[i:j]
        if "nowcMostra" in vell or "nowcDurada" in vell or len(vell) > 20000:
            surt("el bloc de persistència detectat és massa gran o inclou el nowcast")
        s = s[:i] + s[j:]
        n += 1
    resum.append(f"persistència antiga: {n} bloc(s) eliminat(s)")

    # 2) bloc de nowcast
    if INI_NOWC in s:
        if s.count(INI_NOWC) != 1:
            surt(f"el bloc de nowcast surt {s.count(INI_NOWC)} cops")
        i = s.index(INI_NOWC)
        fins = [(s.find(e, i), e) for e in FINS_NOWC if s.find(e, i) >= 0]
        if not fins:
            surt("trobo l'inici del bloc de nowcast però no un final conegut")
        j, e = min(fins)
        j += len(e)
        s = s[:i] + bloc + s[j:]
        resum.append("bloc de nowcast: substituït")
    else:
        if s.count(ANCORA) != 1:
            surt(f"l'ancoratge del control de mapes base surt {s.count(ANCORA)} cops")
        s = s.replace(ANCORA, ANCORA + "\n" + bloc, 1)
        resum.append("bloc de nowcast: inserit")

    # 3) crida des de showFrame
    if HOOK not in s:
        if s.count(HOOK_ANC) != 1:
            surt(f"'currentTs = ts;' surt {s.count(HOOK_ANC)} cops")
        s = s.replace(HOOK_ANC, HOOK_ANC + HOOK, 1)
        resum.append("showFrame(): crida afegida")
    else:
        resum.append("showFrame(): crida ja existent")

    if s.count("persist.") or "PersistControl" in s:
        print("AVÍS: encara queden referències a 'persist' a l'index.html; revisa-ho amb grep -n persist", file=sys.stderr)
    if s == orig:
        print("Sense canvis: l'index.html ja estava al dia.")
        return
    copia = Path.home() / f"index.html.backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(f, copia)
    f.write_text(s)
    print("OK |", " | ".join(resum), f"| còpia: {copia}")


main()
