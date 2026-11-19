"""
Recoloreix tots els PNG existents amb la nova paleta discreta estil AEMET,
sense tocar els .json (bounds/graella, que no depenen del color).

Execució: python3 scripts/recolor_pngs.py
"""

import re
from pathlib import Path

import numpy as np
import rasterio
import matplotlib.colors as mcolors
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PNG_DIR = REPO_ROOT / "data" / "png"

FILENAME_RE = re.compile(r"_TOP_(\d{8})_(\d{4})_TOPS130")

AEMET_BOUNDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 999]
AEMET_COLORS = [
    "#0000B3", "#0033FF", "#0080FF", "#00CCFF", "#00FFFF",
    "#4C7300", "#80B300", "#00CC00", "#FFFF00", "#FFA500",
    "#FF7F00", "#FF0000", "#FF00FF", "#800080",
]


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


def recolor(tiff_path: Path, out_png: Path):
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

    cmap, bnorm = get_aemet_cmap_norm()
    rgba = (cmap(bnorm(data)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(data <= 0, 0, 200)
    Image.fromarray(rgba, mode="RGBA").save(out_png)


def main():
    actualitzats = 0
    errors = []

    for tiff_path in sorted(RAW_DIR.glob("*.tif")):
        ts = parse_timestamp(tiff_path.name)
        if ts is None:
            continue
        out_png = PNG_DIR / f"{ts}.png"
        if not out_png.exists():
            continue  # frame sense PNG (no hauria de passar)

        try:
            recolor(tiff_path, out_png)
            actualitzats += 1
            if actualitzats % 100 == 0:
                print(f"...{actualitzats} recolorits fins ara")
        except Exception as e:
            errors.append(tiff_path.name)
            print(f"ERROR amb {tiff_path.name}: {e}")

    print(f"\nRecolorits: {actualitzats}")
    if errors:
        print(f"Errors ({len(errors)}): {errors}")


if __name__ == "__main__":
    main()
