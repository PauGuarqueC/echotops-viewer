"""
Descàrrega directa via SFTP dels TIFFs d'echo tops des de ftp.meteo.cat.

Pensat per executar-se dins de GitHub Actions (o també en local): les rutes
són sempre relatives a l'arrel del repositori.
"""

import os
from pathlib import Path

import paramiko

SFTP_HOST = "ftp.meteo.cat"
SFTP_PORT = 22
SFTP_USER = "bombers"
SFTP_PASS = os.environ["SFTP_METEOCAT_PASS"]  # ve d'un GitHub Secret

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
REMOTE_DIR = "/Dades/echotops"
FILE_SUFFIX = "TOPS130_12.tif"


def connecta_sftp():
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    # Servidor amb host key ssh-rsa (SHA-1, antiga). Requereix paramiko < 4.0.
    transport.get_security_options().key_types = ["ssh-rsa"]
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    return paramiko.SFTPClient.from_transport(transport), transport


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ja_descarregats = {p.name for p in RAW_DIR.glob("*.tif")}

    sftp, transport = connecta_sftp()
    try:
        pendents = [
            e.filename for e in sftp.listdir_attr(REMOTE_DIR)
            if e.filename.endswith(FILE_SUFFIX) and e.filename not in ja_descarregats
        ]
        print(f"Fitxers pendents: {len(pendents)}")
        for nom in pendents:
            remot = f"{REMOTE_DIR}/{nom}"
            local = RAW_DIR / nom
            sftp.get(remot, str(local))
            if local.stat().st_size == 0:
                local.unlink()
                print(f"Descartat (0 bytes): {nom}")
            else:
                print(f"Descarregat: {nom}")
    finally:
        sftp.close()
        transport.close()


if __name__ == "__main__":
    main()
