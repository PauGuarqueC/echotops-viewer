# Echo Tops Viewer — GitHub Pages + Actions

Versió del viewer que **no depèn del `labfire.ctfc.cat`**: GitHub Actions
fa la baixada SFTP + processament cada ~10 min (com un cron al núvol), i
GitHub Pages serveix la pàgina i les imatges, amb URL fixa i gratuïta.

## 1. Crea el repositori

Al teu compte de GitHub, crea un repositori nou **públic** (obligatori pel
pla gratuït de Pages/Actions il·limitat), per exemple `echotops-graf`.

Puja aquest projecte:

```bash
cd echotops_pages
git init
git add .
git commit -m "Setup inicial del viewer"
git branch -M main
git remote add origin https://github.com/<el_teu_usuari>/echotops-graf.git
git push -u origin main
```

## 2. Configura el secret de la contrasenya SFTP

Al repositori de GitHub: **Settings → Secrets and variables → Actions →
New repository secret**

- Nom: `SFTP_METEOCAT_PASS`
- Valor: la contrasenya real de l'usuari `bombers`

## 3. Activa GitHub Pages

**Settings → Pages**:
- Source: `Deploy from a branch`
- Branch: `main` / `(root)`
- Guarda

Al cap d'un minut tindràs la URL (típicament
`https://<el_teu_usuari>.github.io/echotops-graf/`).

## 4. Canvia la contrasenya de la pàgina

El fitxer `index.html` porta un hash d'exemple (contrasenya de prova:
`bombers2026` — **canvia-la**). Per generar el hash de la contrasenya que
vulguis:

```bash
echo -n "la_contrasenya_que_triis" | sha256sum
```

Copia el resultat (només els 64 caràcters, sense el ` -` final) i
substitueix'l a `index.html`:

```js
const PASSWORD_HASH = "AQUÍ_EL_NOU_HASH";
```

Fes commit i push del canvi.

**Nota de seguretat**: això és una protecció bàsica (dificulta l'accés
casual), no seguretat forta — qualsevol amb coneixements tècnics podria
mirar el codi font i trobar el hash. Com que és una pàgina pública a
internet, no hi pengeu res que no pugueu permetre's que es filtri.

## 5. Primera execució

Ves a la pestanya **Actions** del repositori → workflow "Actualitza echo
tops" → **Run workflow** (botó manual, no cal esperar el cron). Això farà
el primer backfill (pot trigar una estona si hi ha molts fitxers pendents
al FTP).

A partir d'aquí, s'executa sol cada ~10 minuts.

## Limitacions a tenir en compte

- **GitHub no garanteix l'exactitud del cron**: en hores de molta càrrega
  al núvol de GitHub, pot retardar-se uns minuts respecte als 10 exactes.
- **Creixement del repositori**: com que es conserva tot l'històric, el
  repositori creixerà uns ~3-4 MB/dia. GitHub recomana no passar d'~1 GB
  (no és un límit dur, però convé vigilar-ho a mig termini).
- **Pàgina pública**: protegida amb contrasenya bàsica, però tècnicament
  visible per a qui en tingui l'enllaç i sàpiga mirar el codi font.

## Fitxers

- `index.html` — la pàgina (mapa Leaflet + pantalla de contrasenya)
- `scripts/descarrega_echotops_sftp.py` — pull SFTP
- `scripts/process_tiffs.py` — conversió TIFF → PNG
- `scripts/build_manifest.py` — genera `data/png/manifest.json`
- `.github/workflows/update.yml` — l'automatització
- `data/raw/`, `data/png/` — dades (es van omplint soles)
