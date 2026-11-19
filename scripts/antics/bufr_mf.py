#!/usr/bin/env python3
"""Taules BUFR locals de Météo-France (centre 85) -> format d'ecCodes, i activació.
Entrada: el .zip «radar-tables-decodage-AAAAMMDD.zip» (CSV: localtabb_85_N.csv, localtabd_85_N.csv, ...)."""
import unicodedata, zipfile
from pathlib import Path


def _ascii(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().replace("|", "/").strip()


def _lines(z, nom):
    return z.read(nom).decode("latin-1").splitlines()


def construeix(zip_path, dest, centre=85, versio_local=14, subcentre=0):
    """Escriu <dest>/bufr/tables/0/local/<versio>/<centre>/<subcentre>/{element.table,sequence.def}."""
    z = zipfile.ZipFile(zip_path)
    noms = {Path(n).name: n for n in z.namelist()}
    b, d = f"localtabb_{centre}_{versio_local}.csv", f"localtabd_{centre}_{versio_local}.csv"
    if b not in noms or d not in noms:
        raise SystemExit(f"Al .zip falten {b} o {d}")
    out = Path(dest) / "bufr" / "tables" / "0" / "local" / str(versio_local) / str(centre) / str(subcentre)
    out.mkdir(parents=True, exist_ok=True)
    el = ["#code|abbreviation|type|name|unit|scale|reference|width|crex_unit|crex_scale|crex_width"]
    for l in _lines(z, noms[b]):
        p = [x.strip() for x in l.split(";")]
        if len(p) < 8 or p[0] != "0":
            continue
        cod = f"0{int(p[1]):02d}{int(p[2]):03d}"
        nom, unit, scale, ref, w = _ascii(p[3]), p[4], int(p[5]), int(p[6]), int(p[7])
        ul = unit.lower()
        tip = "string" if ul.startswith("ccitt") else "table" if ul == "code table" else "flag" if ul == "flag table" else ("double" if scale > 0 else "long")
        un = _ascii(unit).upper() if ul in ("code table", "flag table") or ul.startswith("ccitt") or ul == "numeric" else _ascii(unit)
        el.append(f"{cod}|mfLocal{cod}|{tip}|{nom}|{un}|{scale}|{ref}|{w}|{un}|{scale}|{len(str(2 ** w))}")
    (out / "element.table").write_text("\n".join(el) + "\n", encoding="ascii")
    seq, cur = {}, None
    for l in _lines(z, noms[d]):
        p = [x.strip() for x in l.split(";")]
        if len(p) < 6:
            continue
        if p[0] == "3":
            cur = f"3{int(p[1]):02d}{int(p[2]):03d}"
            seq[cur] = []
        if cur and p[3] != "":
            seq[cur].append(f"{int(p[3])}{int(p[4]):02d}{int(p[5]):03d}")
    (out / "sequence.def").write_text("".join(f'"{k}" = [ {", ".join(v)} ]\n' for k, v in seq.items()), encoding="ascii")
    return str(dest), len(el) - 1, len(seq)


def activa(dest):
    """Afegeix <dest> al camí de definicions d'ecCodes (abans de les pròpies) i retorna el mòdul eccodes."""
    import eccodes as ec
    base = ec.codes_definition_path()
    if str(dest) not in base:
        ec.codes_set_definitions_path(f"{dest}:{base}")
    return ec
