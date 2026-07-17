"""
Converteix els GeoTIFF crus d'echo tops (data/raw/) a PNG colorejats
reprojectats a EPSG:4326 (data/png/), amb un JSON de metadades per fitxer.
Rutes sempre relatives a l'arrel del repositori (GitHub Actions o local).
"""

import json
import re
from pathlib import Path

import numpy as np
import rasterio
import matplotlib
import matplotlib.colors as mcolors
from rasterio.warp import calculate_default_transform, reproject, Resampling
from matplotlib import cm
from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PNG_DIR = REPO_ROOT / "data" / "png"

FILENAME_RE = re.compile(r"_TOP_(\d{8})_(\d{4})_TOPS130")

# Escala discreta d'alçada d'echo top (km), inspirada en la paleta d'AEMET.
# Colors aproximats — si teniu els codis hex exactes de la guia d'AEMET,
# ajusteu AEMET_COLORS.
AEMET_BOUNDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 999]
AEMET_COLORS = [
    "#0000B3", "#0033FF", "#0080FF", "#00CCFF", "#00FFFF",
    "#4C7300", "#80B300", "#00CC00", "#FFFF00", "#FFA500",
    "#FF7F00", "#FF0000", "#FF00FF", "#800080",
]
VMIN, VMAX = 0.0, 20.0  # es manté per referència, la normalització real la fa BoundaryNorm


def parse_timestamp(filename: str):
    m = FILENAME_RE.search(filename)
    if not m:
        return None
    date_str, hour_str = m.groups()
    return f"{date_str}_{hour_str}"


def get_aemet_cmap_norm():
    cmap = mcolors.ListedColormap(AEMET_COLORS)
    norm = mcolors.BoundaryNorm(AEMET_BOUNDS, cmap.N)
    return cmap, norm


def downsample_max(data: np.ndarray, target_dim: int = 100) -> np.ndarray:
    """Redueix la graella agafant el MÀXIM de cada bloc de píxels (no un
    píxel solt cada N), perquè cap cel·la representi fidelment tota la seva
    àrea i no hi hagi buits ni pics aïllats mal representats."""
    step = max(1, max(data.shape) // target_dim)
    h, w = data.shape
    pad_h = (-h) % step
    pad_w = (-w) % step
    padded = np.pad(data, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=0)
    hh, ww = padded.shape
    blocks = padded.reshape(hh // step, step, ww // step, step)
    return blocks.max(axis=(1, 3))


def tiff_to_png(tiff_path: Path, out_png: Path, out_json: Path):
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
        west = transform.c
        north = transform.f
        east = west + transform.a * width
        south = north + transform.e * height

    cmap, bnorm = get_aemet_cmap_norm()
    rgba = (cmap(bnorm(data)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(data <= 0, 0, 200)

    Image.fromarray(rgba, mode="RGBA").save(out_png)

    # Graella de valors submostrejada (lleugera) perquè el frontend pugui
    # mostrar el valor numèric sota el cursor sense haver de descarregar
    # el TIFF sencer. Fem servir el màxim per bloc (no un píxel solt cada
    # N) perquè cada cel·la representi fidelment tota la seva àrea.
    grid = downsample_max(data)
    grid_values = [
        [round(float(v), 2) if v > 0 else None for v in row]
        for row in grid
    ]

    meta = {
        "bounds": [[float(south), float(west)], [float(north), float(east)]],
        "vmin": VMIN,
        "vmax": VMAX,
        "data_max": float(np.nanmax(data)),
        "grid": {
            "rows": grid.shape[0],
            "cols": grid.shape[1],
            "values": grid_values,
        },
    }
    out_json.write_text(json.dumps(meta))


def main():
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    processats = 0
    errors = []
    for tiff_path in sorted(RAW_DIR.glob("*.tif")):
        ts = parse_timestamp(tiff_path.name)
        if ts is None:
            continue
        out_png = PNG_DIR / f"{ts}.png"
        out_json = PNG_DIR / f"{ts}.json"
        if out_png.exists():
            continue
        try:
            tiff_to_png(tiff_path, out_png, out_json)
            processats += 1
            print(f"Processat: {tiff_path.name} -> {out_png.name}")
        except Exception as e:
            errors.append(tiff_path.name)
            print(f"ERROR processant {tiff_path.name}: {e}")

    print(f"Total processats: {processats}")
    if errors:
        print(f"Fitxers amb error ({len(errors)}): {errors}")


if __name__ == "__main__":
    main()
