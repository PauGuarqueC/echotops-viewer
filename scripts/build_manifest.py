"""
Genera data/png/manifest.json: un únic fitxer amb la llista de tots els
frames disponibles i els seus bounds, perquè el frontend estàtic (GitHub
Pages, sense backend) no hagi de fer una petició per frame.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PNG_DIR = REPO_ROOT / "data" / "png"
TS_RE = re.compile(r"^\d{8}_\d{4}$")


def main():
    frames = {}
    for json_path in sorted(PNG_DIR.glob("*.json")):
        if not TS_RE.match(json_path.stem):
            continue
        meta = json.loads(json_path.read_text())
        frames[json_path.stem] = meta["bounds"]

    manifest = {"timestamps": sorted(frames.keys()), "bounds": frames}
    (PNG_DIR / "manifest.json").write_text(json.dumps(manifest))
    print(f"Manifest generat amb {len(frames)} frames.")


if __name__ == "__main__":
    main()
