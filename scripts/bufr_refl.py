#!/usr/bin/env python3
"""Descodificador RÀPID (~1 s, només numpy) de la mosaic de reflectivitat de Météo-France (IMFR27, BUFR, 1 km, 1536x1536).
No necessita ecCodes ni les taules locals: el missatge té una estructura fixa (3 imatges de 1536*1536 valors
amb amplades 10, 12 i 11 bits). Es verifica l'estructura abans de llegir res; si canvia, aixeca ValueError."""
import gzip
import datetime as dt
import numpy as np

N = 1536 * 1536
# Cada imatge va precedida d'una paraula de repetició de 32 bits (= N). Amplades: prob 10 bits, alçada 12, reflectivitat 11.
# Les posicions varien segons el farciment de les metadades, així que es busquen a cada missatge.


def obre(bytes_):
    if bytes_[:2] == b"\x1f\x8b":
        bytes_ = gzip.decompress(bytes_)
    if bytes_[:4] != b"BUFR":
        raise ValueError("no és un BUFR")
    return bytes_


def _seccions(b):
    i = 8
    l1 = int.from_bytes(b[i:i + 3], "big")
    s1 = b[i:i + l1]
    flag2 = s1[9] & 0x80
    i += l1
    if flag2:
        i += int.from_bytes(b[i:i + 3], "big")
    l3 = int.from_bytes(b[i:i + 3], "big")
    i += l3
    l4 = int.from_bytes(b[i:i + 3], "big")
    return s1, i, l4


def hora(b):
    """Hora (UTC) del producte, de la secció 1 (BUFR edició 4)."""
    s1, _, _ = _seccions(b)
    y = int.from_bytes(s1[15:17], "big")
    return dt.datetime(y, s1[17], s1[18], s1[19], s1[20], s1[21] if len(s1) > 21 else 0, tzinfo=dt.timezone.utc)


def _llegeix(b, ini_bit, amplada, n):
    """n enters sense signe de 'amplada' bits consecutius a partir del bit absolut ini_bit."""
    byte0, sh = divmod(ini_bit, 8)
    nb = (sh + amplada * n + 7) // 8
    bits = np.unpackbits(np.frombuffer(b, dtype=np.uint8, count=nb, offset=byte0))[sh:sh + amplada * n]
    bits = bits.reshape(n, amplada)
    out = np.zeros((n, 16), dtype=np.uint8)
    out[:, 16 - amplada:] = bits
    return np.packbits(out, axis=1).view(">u2").ravel().astype(np.uint16)


def _posicions(b):
    """Posicions (en bits des del principi del missatge) de les 3 paraules de repetició = N, a qualsevol alineació."""
    pat = N.to_bytes(4, "big")
    arr = np.frombuffer(b, dtype=np.uint8).astype(np.uint16)
    trobats = []
    for sh in range(8):
        if sh == 0:
            sb = arr.astype(np.uint8).tobytes()
        else:
            sb = (((arr[:-1] << sh) | (arr[1:] >> (8 - sh))) & 0xFF).astype(np.uint8).tobytes()
        k = sb.find(pat)
        while k >= 0:
            trobats.append(k * 8 + sh)
            k = sb.find(pat, k + 1)
    trobats.sort()
    for p1 in trobats:
        p2, p3 = p1 + 32 + 10 * N, p1 + 32 + 10 * N + 32 + 12 * N + 11
        if p2 in trobats and p3 in trobats and p3 + 32 + 11 * N <= len(b) * 8:
            return p1, p2, p3
    raise ValueError("estructura BUFR inesperada: paraules trobades a %s, mida %d" % (trobats[:6], len(b)))


def alcada(b):
    """Alçada de la mesura retinguda (m sobre el nivell del mar), matriu float32 1536x1536; NaN = sense dada.
    Només hi ha valor on hi ha eco. 12 bits: m = raw*10 - 400 (4095 = absent)."""
    b = obre(b)
    _, p2, _ = _posicions(b)
    raw = _llegeix(b, p2 + 32, 12, N).astype(np.float32)
    h = raw * 10.0 - 400.0
    h[raw == 4095] = np.nan
    return h.reshape(1536, 1536)


def reflectivitat(b):
    """Retorna (matriu float32 1536x1536 en dBZ, hora). NaN = sense dada; -40 = sense detecció. Fila 0 = nord."""
    b = obre(b)
    _, _, p3 = _posicions(b)
    # 11 bits: referència nova -400 (a dècimes de dBZ) -> dBZ = (raw-400)/10 ; 2047 = dada absent
    raw = _llegeix(b, p3 + 32, 11, N).astype(np.float32)
    z = (raw - 400.0) / 10.0
    z[raw == 2047] = np.nan
    return z.reshape(1536, 1536), hora(b)


if __name__ == "__main__":
    import sys, time
    t0 = time.time()
    z, h = reflectivitat(open(sys.argv[1], "rb").read())
    print(h, z.shape, "finit", int(np.isfinite(z).sum()), "max", float(np.nanmax(z)), f"{time.time()-t0:.2f}s")
