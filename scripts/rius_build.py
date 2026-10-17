#!/usr/bin/env python3
"""Rius de Catalunya i de les conques que desemboquen a l'Ebre -> data/rius/rius.geojson (lleuger, per al visor).

Es corre UNA vegada (o quan vulguis refrescar-lo): els rius no canvien. Baixa d'OpenStreetMap (Overpass API):
  - tots els waterway=river de la finestra gran (Catalunya + conca de l'Ebre, de Cantàbria al delta);
  - a Catalunya, tots els waterway=stream (amb nom i sense).
Es queda amb els rius i les rieres amb nom; els trams SENSE nom només s'hi afegeixen si són la continuació riu avall d'un
tram amb nom (així una riera no es talla de cop quan OpenStreetMap té el tros final sense nom) fins que arriba a un altre
tram, al mar o al límit de --max-continua-km. Després simplifica (Douglas-Peucker), arrodoneix i agrupa per nom.

  python3 scripts/rius_build.py --brut ~/echotops-data/osm_rius2.json     # baixa (o reutilitza) i genera data/rius/rius.geojson
Dades © OpenStreetMap contributors (ODbL): el visor ho cita al peu de les exportacions.
Format antic de --brut (clau "elements", sense els trams sense nom): es pot llegir, però no es poden omplir els talls."""
import argparse, json, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from pathlib import Path

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
GRAN = (-4.40, 40.00, 3.45, 43.45)       # (lon0, lat0, lon1, lat1) Catalunya + conca de l'Ebre (Reinosa -> delta, Pirineu)
CAT = (0.10, 40.45, 3.40, 42.95)         # on es baixen també totes les rieres (amb nom i sense)
UA = "echotops-viewer/rius_build (CTFC; contacte: pguarque@gmail.com)"


def trosseja(b, nx, ny):
    lon0, lat0, lon1, lat1 = b
    xs = [lon0 + (lon1 - lon0) * i / nx for i in range(nx + 1)]
    ys = [lat0 + (lat1 - lat0) * j / ny for j in range(ny + 1)]
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1]) for i in range(nx) for j in range(ny)]


def consulta(q):
    dades = urllib.parse.urlencode({"data": q}).encode()
    ultim = None
    for intent in range(6):
        ep = ENDPOINTS[intent % len(ENDPOINTS)]
        try:
            rq = urllib.request.Request(ep, data=dades, headers={"User-Agent": UA})
            with urllib.request.urlopen(rq, timeout=600) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            ultim = e
            print(f"  {ep}: {e} (reintent)", file=sys.stderr)
            time.sleep(10 * (intent + 1))
    raise SystemExit(f"Overpass no respon: {ultim}")


def compacta(e):
    """element d'Overpass -> {id, n(om), c(lasse 1 riu / 2 riera), nodes, pts} o None."""
    g = e.get("geometry")
    if e.get("type") != "way" or not g:
        return None
    tags = e.get("tags", {})
    return {"id": e["id"], "n": (tags.get("name") or "").strip(), "c": 1 if tags.get("waterway") == "river" else 2,
            "nodes": e.get("nodes") or [], "pts": [(round(p["lon"], 5), round(p["lat"], 5)) for p in g]}


def baixa():
    ways = {}
    def fes(caixes, tipus, etiqueta):
        for n, (x0, y0, x1, y1) in enumerate(caixes, 1):
            bb = f"({y0:.4f},{x0:.4f},{y1:.4f},{x1:.4f})"
            q = f'[out:json][timeout:540];way["waterway"~"^({tipus})$"]{bb};out geom;'
            print(f"{etiqueta} {n}/{len(caixes)} {bb} ...", flush=True)
            for e in consulta(q).get("elements", []):
                w = compacta(e)
                if w:
                    ways[w["id"]] = w            # un tram que travessa dos trossos només es guarda un cop
            time.sleep(4)
    fes(trosseja(GRAN, 4, 3), "river", "Rius")
    fes(trosseja(CAT, 5, 4), "river|stream", "Catalunya")
    return {"w": list(ways.values())}


def carrega_brut(d):
    if "w" in d:
        ws = d["w"]
    else:                                                       # format antic (només rius i rieres amb nom)
        print("AVÍS: format antic de --brut: no hi ha els trams sense nom i no es poden omplir els talls; "
              "esborra el fitxer per tornar a baixar.", file=sys.stderr)
        ws = [w for w in (compacta(e) for e in d["elements"]) if w]
    for w in ws:                                                # baixada sense ids de node: els vèrtexs amb les mateixes coordenades fan de nodes
        if not w["nodes"]:
            w["nodes"] = [tuple(p) for p in w["pts"]]
    return {w["id"]: w for w in ws}


def dp(pts, tol):
    """Douglas-Peucker iteratiu (graus). pts: llista de (lon, lat)."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n; keep[0] = keep[-1] = True
    pila = [(0, n - 1)]
    while pila:
        a, b = pila.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        dmax, imax = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if l2 == 0:
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
                d = ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol and imax > 0:
            keep[imax] = True
            pila.append((a, imax)); pila.append((imax, b))
    return [p for p, k in zip(pts, keep) if k]


def km(pts):
    s = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        s += (((x1 - x0) * 0.75) ** 2 + (y1 - y0) ** 2) ** 0.5 * 111.2
    return s


def selecciona(ways, min_km, max_cont_km, max_salts):
    """Retorna {id: nom_a_mostrar}. Base: trams amb nom + rius sense nom llargs. Continuació: trams sense nom que
    segueixen riu avall (OSM dibuixa els cursos d'aigua en el sentit del corrent) el final d'un tram base."""
    for w in ways.values():
        w["km"] = km(w["pts"])
    base = [i for i, w in ways.items() if w["n"] or (w["c"] == 1 and w["km"] >= min_km)]
    sel = {i: ways[i]["n"] for i in base}
    nbase = defaultdict(int)                                    # a quants trams base pertany cada node
    for i in base:
        for nd in set(ways[i]["nodes"]):
            nbase[nd] += 1
    inici = defaultdict(list)                                   # node -> trams NO base que hi comencen
    for i, w in ways.items():
        if i not in sel and w["nodes"]:
            inici[w["nodes"][0]].append(i)
    n_cont = 0
    for i in base:
        w = ways[i]
        if not w["nodes"]:
            continue
        cur = w["nodes"][-1]
        if nbase[cur] > 1:                                      # desemboca en un altre tram: no hi ha tall
            continue
        tot = 0.0
        for _ in range(max_salts):
            cands = [x for x in inici.get(cur, []) if x not in sel]
            if not cands:
                break
            x = max(cands, key=lambda k: ways[k]["km"])
            if tot + ways[x]["km"] > max_cont_km:
                break
            sel[x] = w["n"]; tot += ways[x]["km"]; n_cont += 1
            cur = ways[x]["nodes"][-1]
            if nbase[cur] >= 1:                                 # ha arribat a un altre tram: ja està unit
                break
    return sel, len(base), n_cont


def construeix(ways, tol, min_km, max_cont_km, max_salts):
    sel, nbase, ncont = selecciona(ways, min_km, max_cont_km, max_salts)
    grups = {}
    for i, nom in sel.items():
        w = ways[i]
        pts = [(round(x, 4), round(y, 4)) for x, y in dp(w["pts"], tol)]
        if len(pts) >= 2:
            grups.setdefault((nom, w["c"]), []).append([[x, y] for x, y in pts])
    feats = [{"type": "Feature", "properties": {"n": k[0], "c": k[1]},
              "geometry": {"type": "MultiLineString", "coordinates": ls}} for k, ls in sorted(grups.items())]
    return {"type": "FeatureCollection", "features": feats}, nbase, ncont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortida", default="data/rius/rius.geojson")
    ap.add_argument("--brut", help="fitxer on desar la baixada d'Overpass (si ja existeix, s'hi reutilitza i no es baixa)")
    ap.add_argument("--tolerancia", type=float, default=0.0002, help="simplificació en graus (0,0002 ~ 20 m)")
    ap.add_argument("--min-km", type=float, default=1.0, help="els rius sense nom més curts que això es descarten")
    ap.add_argument("--max-continua-km", type=float, default=8.0, help="màxim de recorregut sense nom que s'afegeix a la continuació d'una riera")
    ap.add_argument("--max-salts", type=int, default=12, help="màxim de trams sense nom encadenats per riera")
    ap.add_argument("--max-mb", type=float, default=12.0)
    a = ap.parse_args()
    if a.brut and Path(a.brut).exists():
        ways = carrega_brut(json.loads(Path(a.brut).read_text(encoding="utf-8"))); print("Reutilitzo", a.brut)
    else:
        raw = baixa()
        if a.brut:
            Path(a.brut).write_text(json.dumps(raw, separators=(",", ":")), encoding="utf-8")
        ways = carrega_brut(raw)
    print(f"{len(ways)} trams de cursos d'aigua")
    tol = a.tolerancia
    for _ in range(6):
        gj, nbase, ncont = construeix(ways, tol, a.min_km, a.max_continua_km, a.max_salts)
        txt = json.dumps(gj, ensure_ascii=False, separators=(",", ":"))
        mb = len(txt.encode("utf-8")) / 1e6
        print(f"tolerància {tol:g}: {len(gj['features'])} grups ({nbase} trams base + {ncont} de continuació), {mb:.2f} MB")
        if mb <= a.max_mb:
            break
        tol *= 1.6
    out = Path(a.sortida); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt, encoding="utf-8")
    print("Desat", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
