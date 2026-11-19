"""Rutes del visor d'inundacions, en un sol lloc.

Es configuren amb variables d'entorn (les defineix config.env, que llegeix update.sh).
Si una variable no està definida, es fa servir la ruta d'ara: res canvia fins que no
es configuri la migració a labfire.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ruta(var, defecte):
    return Path(os.environ.get(var) or defecte).expanduser()


WEB = _ruta("INUND_WEB", REPO / "data")                                   # tot el que llegeix el visor (es serveix)
ECHOTOPS = _ruta("INUND_ECHOTOPS", Path.home() / "echotops-data")         # raw/ (TIFF Meteocat), dist_costa.npz
PNG = _ruta("INUND_PNG", ECHOTOPS / "png")                                 # on process_tiffs escriu els PNG d'echotops
RADAR = _ruta("INUND_RADAR", ECHOTOPS / "radar")                           # OPERA: brut/ (.h5) i arxiu_1km/
