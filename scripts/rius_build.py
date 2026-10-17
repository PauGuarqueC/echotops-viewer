#!/usr/bin/env python3
"""Rius de Catalunya i de les conques que desemboquen a l'Ebre -> data/rius/rius.geojson (lleuger, per al visor).

Es corre UNA vegada (o quan vulguis refrescar-lo): els rius no canvien. Baixa d'OpenStreetMap (Overpass API):
  - tots els waterway=river de la finestra gran (Catalunya + conca de l'Ebre, de Cantàbria al delta);
  - els waterway=stream amb nom, només a Catalunya (rieres i torrents que importen en una crescuda).
Després: treu els trams curts sense nom, simplifica les línies (Douglas-Peucker) i arrodoneix a 4 decimals (~10 m),
agrupa per nom i desa un GeoJSON compacte. Si pesa més de --max-mb, torna a simplificar amb més tolerància.

  python3 scripts/rius_build.py                     # baixa i genera data/rius/rius.geojson
  python3 scripts/rius_build.py --brut /tmp/osm.json   # desa/reutilitza la resposta d'Overpass (per no tornar a baixar)
Dades © OpenStreetMap contributors (ODbL): el visor ho cita al peu de les exportacions."""
import argparse, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
GRAN = (-4.40, 40.00, 3.45, 43.45)       # (lon0, lat0, lon1, lat1) Catalunya + conca de l'Ebre (Reinosa -> delta, Pirineu)
CAT = (0.10, 40.45, 3.40, 42.95)         # on s'afegeixen també els torrents amb nom
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
            with urllib.request.urlopen(rq, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            ultim = e
            print(f"  {ep}: {e} (reintent)", file=sys.stderr)
            time.sleep(10 * (intent + 1))
    raise SystemExit(f"Overpass no respon: {ultim}")


def baixa():
    elems = {}
    caixes = trosseja(GRAN, 4, 3)
    for n, (x0, y0, x1, y1) in enumerate(caixes, 1):
        bb = f"({y0:.4f},{x0:.4f},{y1:.4f},{x1:.4f})"
        q = f'[out:json][timeout:240];(way["waterway"="river"]{bb};'
        if not (x1 < CAT[0] or x0 > CAT[2] or y1 < CAT[1] or y0 > CAT[3]):
            cb = f"({max(y0, CAT[1]):.4f},{max(x0, CAT[0]):.4f},{min(y1, CAT[3]):.4f},{min(x1, CAT[2]):.4f})"
            q += f'way["waterway"="stream"]["name"]{cb};'
        q += ");out geom tags;"
        print(f"Tros {n}/{len(caixes)} {bb} ...")
        for e in consulta(q).get("elements", []):
            if e.get("type") == "way" and e.get("geometry"):
                elems[e["id"]] = e            # un tram que travessa dos trossos només es guarda un cop
        time.sleep(3)
    return {"elements": list(elems.values())}


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


def construeix(osm, tol, min_km):
    grups = {}
    for e in osm["elements"]:
        tags = e.get("tags", {}); nom = (tags.get("name") or "").strip()
        cls = 1 if tags.get("waterway") == "river" else 2
        pts = [(g["lon"], g["lat"]) for g in e["geometry"]]
        if len(pts) < 2:
            continue
        if not nom and km(pts) < min_km:
            continue                                   # tram curt sense nom: soroll
        pts = [(round(x, 4), round(y, 4)) for x, y in dp(pts, tol)]
        if len(pts) >= 2:
            grups.setdefault((nom, cls), []).append([[x, y] for x, y in pts])
    feats = [{"type": "Feature", "properties": {"n": k[0], "c": k[1]},
              "geometry": {"type": "MultiLineString", "coordinates": ls}} for k, ls in sorted(grups.items())]
    return {"type": "FeatureCollection", "features": feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortida", default="data/rius/rius.geojson")
    ap.add_argument("--brut", help="fitxer on desar la resposta d'Overpass (si ja existeix, s'hi reutilitza i no es baixa)")
    ap.add_argument("--tolerancia", type=float, default=0.0004, help="simplificació en graus (0,0004 ~ 40 m)")
    ap.add_argument("--min-km", type=float, default=1.0, help="els trams sense nom més curts que això es descarten")
    ap.add_argument("--max-mb", type=float, default=4.0)
    a = ap.parse_args()
    if a.brut and Path(a.brut).exists():
        osm = json.loads(Path(a.brut).read_text(encoding="utf-8")); print("Reutilitzo", a.brut)
    else:
        osm = baixa()
        if a.brut:
            Path(a.brut).write_text(json.dumps(osm), encoding="utf-8")
    tol = a.tolerancia
    for _ in range(6):
        gj = construeix(osm, tol, a.min_km)
        txt = json.dumps(gj, ensure_ascii=False, separators=(",", ":"))
        mb = len(txt.encode("utf-8")) / 1e6
        print(f"tolerància {tol:g}: {len(gj['features'])} grups, {mb:.2f} MB")
        if mb <= a.max_mb:
            break
        tol *= 1.6
    out = Path(a.sortida); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt, encoding="utf-8")
    print("Desat", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
