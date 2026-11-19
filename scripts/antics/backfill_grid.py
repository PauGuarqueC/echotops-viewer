"""
Recalcula la graella de valors (per al hover del mapa) de TOTS els frames,
amb el mètode de màxim per bloc (més fiable que el mostreig per salts).

Reprocessa també els frames que ja tenien una graella antiga (generada amb
el mètode anterior, que podia donar falsos positius/negatius al hover).

No regenera els PNG (ja existeixen i són correctes) — només recalcula la
reprojecció per obtenir els valors numèrics i actualitza el .json de cada
frame.

Execució: python3 scripts/backfill_grid.py
"""

import json
import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PNG_DIR = REPO_ROOT / "data" / "png"

FILENAME_RE = re.compile(r"_TOP_(\d{8})_(\d{4})_TOPS130")


def parse_timestamp(filename: str):
    m = FILENAME_RE.search(filename)
    if not m:
        return None
    date_str, hour_str = m.groups()
    return f"{date_str}_{hour_str}"


def downsample_max(data: np.ndarray, target_dim: int = 100) -> np.ndarray:
    """Màxim per bloc de píxels, perquè cada cel·la de la graella
    representi fidelment tota la seva àrea (sense buits ni pics aïllats
    mal representats, com passava amb el mostreig per salts anterior)."""
    step = max(1, max(data.shape) // target_dim)
    h, w = data.shape
    pad_h = (-h) % step
    pad_w = (-w) % step
    padded = np.pad(data, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=0)
    hh, ww = padded.shape
    blocks = padded.reshape(hh // step, step, ww // step, step)
    return blocks.max(axis=(1, 3))


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

    grid = downsample_max(data)
    values = [
        [round(float(v), 2) if v > 0 else None for v in row]
        for row in grid
    ]
    return {"rows": grid.shape[0], "cols": grid.shape[1], "values": values}


def main():
    actualitzats = 0
    errors = []

    for tiff_path in sorted(RAW_DIR.glob("*.tif")):
        ts = parse_timestamp(tiff_path.name)
        if ts is None:
            continue
        json_path = PNG_DIR / f"{ts}.json"
        if not json_path.exists():
            continue  # frame sense json (no hauria de passar, es processa junts)

        meta = json.loads(json_path.read_text())

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
    if errors:
        print(f"Errors ({len(errors)}): {errors}")


if __name__ == "__main__":
    main()

