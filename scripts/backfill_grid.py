"""
Afegeix retroactivament la graella de valors (per al hover del mapa) als
frames que ja es van processar abans d'aquesta funcionalitat existir.

No regenera els PNG (ja existeixen i són correctes) — només recalcula la
reprojecció per obtenir els valors numèrics i actualitza el .json de cada
frame afegint-hi la clau "grid".

Execució: python3 scripts/backfill_grid.py
"""

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PNG_DIR = REPO_ROOT / "data" / "png"

import re
FILENAME_RE = re.compile(r"_TOP_(\d{8})_(\d{4})_TOPS130")


def parse_timestamp(filename: str):
    m = FILENAME_RE.search(filename)
    if not m:
        return None
    date_str, hour_str = m.groups()
    return f"{date_str}_{hour_str}"


def calcula_graella(tiff_path: Path):
    with rasterio.open(tiff_path) as src:
        dst_crs = "EPSG:4326"
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        data = np.zeros((height, width), dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=0,
        )

    step = max(1, max(data.shape) // 60)
    grid = data[::step, ::step]
    values = [
        [round(float(v), 2) if v > 0 else None for v in row]
        for row in grid
    ]
    return {"rows": grid.shape[0], "cols": grid.shape[1], "values": values}


def main():
    actualitzats = 0
    ja_tenien = 0
    errors = []

    for tiff_path in sorted(RAW_DIR.glob("*.tif")):
        ts = parse_timestamp(tiff_path.name)
        if ts is None:
            continue
        json_path = PNG_DIR / f"{ts}.json"
        if not json_path.exists():
            continue  # frame sense json (no hauria de passar, es processa junts)

        meta = json.loads(json_path.read_text())
        if "grid" in meta:
            ja_tenien += 1
            continue

        try:
            meta["grid"] = calcula_graella(tiff_path)
            json_path.write_text(json.dumps(meta))
            actualitzats += 1
            if actualitzats % 100 == 0:
                print(f"...{actualitzats} actualitzats fins ara")
        except Exception as e:
            errors.append(tiff_path.name)
            print(f"ERROR amb {tiff_path.name}: {e}")

    print(f"\nActualitzats: {actualitzats}")
    print(f"Ja tenien graella (saltats): {ja_tenien}")
    if errors:
        print(f"Errors ({len(errors)}): {errors}")


if __name__ == "__main__":
    main()
