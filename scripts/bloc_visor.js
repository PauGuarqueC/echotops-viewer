  // ---- Persistència de precipitació intensa (compost AEMET) ----
  // Dades generades per persist_export.py a data/persist/ (meta.json, ratxa_<h>h.png, episodis.json).
  const persist = { meta: null, ep: null, overlay: null, popup: null, hores: 6, actiu: false, timer: null };

  const PersistControl = L.Control.extend({
    options: { position: 'bottomleft' },
    onAdd: function(){
      const div = L.DomUtil.create('div', 'basemap-control');
      div.style.cssText = 'width:210px;color:var(--text);font-size:12px;';
      div.innerHTML = `
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;">
          <input type="checkbox" id="persist-toggle" style="margin-top:2px"> <span>Persistència de pluja intensa (AEMET)</span>
        </label>
        <div id="persist-opts" style="display:none;margin-top:6px;">
          Finestra:
          <select id="persist-hores">
            <option value="3">3 h</option><option value="6" selected>6 h</option>
            <option value="12">12 h</option><option value="24">24 h</option>
          </select>
          <div id="persist-info" style="margin-top:4px;opacity:.8;font-size:11px;line-height:1.35;"></div>
        </div>`;
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelector('#persist-toggle').addEventListener('change', e => persistActiva(e.target.checked));
      div.querySelector('#persist-hores').addEventListener('change', e => {
        persist.hores = parseInt(e.target.value, 10);
        persistPinta();
      });
      return div;
    },
  });
  map.addControl(new PersistControl());

  async function persistCarrega(){
    const q = `?_=${Date.now()}`;
    try{
      const [meta, ep] = await Promise.all([
        fetch('data/persist/meta.json' + q).then(r => r.json()),
        fetch('data/persist/episodis.json' + q).then(r => r.json()),
      ]);
      persist.meta = meta; persist.ep = ep;
    }catch(e){
      persist.meta = null; persist.ep = null;
      console.warn('No s\'han pogut carregar les dades de persistència', e);
    }
  }

  function persistPinta(){
    if (persist.overlay){ map.removeLayer(persist.overlay); persist.overlay = null; }
    const info = document.getElementById('persist-info');
    if (!persist.actiu) return;
    if (!persist.meta){ info.textContent = 'Sense dades de persistència disponibles'; return; }
    const m = persist.meta;
    persist.overlay = L.imageOverlay(`data/persist/ratxa_${persist.hores}h.png?_=${encodeURIComponent(m.final_utc)}`,
      m.bounds, { opacity: 0.85, interactive: false }).addTo(map);
    if (currentOverlay) currentOverlay.bringToFront();
    persist.overlay.bringToFront();
    const edat = (Date.now() - new Date(m.final_utc).getTime()) / 60000;
    const hora = new Date(m.final_utc).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });
    info.innerHTML = `Ratxa contínua ≥ ${m.min_ratxa_min} min amb ≥ 45 dBZ (groc 30 min → granat ≥ 3 h) · dades fins a ${hora}` +
      (edat > 40 ? ` <b style="color:#C8102E">(fa ${Math.round(edat)} min: desactualitzat)</b>` : '');
  }

  async function persistActiva(on){
    persist.actiu = on;
    document.getElementById('persist-opts').style.display = on ? 'block' : 'none';
    clearInterval(persist.timer);
    if (on){
      await persistCarrega();
      persist.timer = setInterval(async () => { await persistCarrega(); persistPinta(); }, 5 * 60 * 1000);
    }else if (persist.popup){
      map.closePopup(persist.popup);
    }
    persistPinta();
  }

  function persistEpisodis(lat, lng){
    const m = persist.meta, [[south, west], [north, east]] = m.bounds;
    if (lat < south || lat > north || lng < west || lng > east) return null;
    const row = Math.min(m.rows - 1, Math.floor((north - lat) / (north - south) * m.rows));
    const col = Math.min(m.cols - 1, Math.floor((lng - west) / (east - west) * m.cols));
    const t0 = new Date(persist.ep.t0).getTime();
    const final = new Date(m.final_utc).getTime();
    const des = final - persist.hores * 3600000;
    const llista = (persist.ep.ep[`${row},${col}`] || [])
      .map(([off, dur, cls, mm, enCurs]) => ({
        ini: t0 + off * 60000, fi: t0 + (off + dur) * 60000, dur, cls, mm, enCurs,
      }))
      .filter(e => e.fi > des);
    return llista;
  }

  const DBZ_CLASSE_TXT = { 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' };
  function persistHora(ms){
    const d = new Date(ms), avui = new Date();
    const h = d.toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });
    return d.toDateString() === avui.toDateString() ? h
      : `${d.toLocaleDateString('ca-ES', { day: '2-digit', month: '2-digit' })} ${h}`;
  }

  map.on('click', (e) => {
    if (!persist.actiu || !persist.meta || !persist.ep) return;
    if (typeof pickingCenter !== 'undefined' && pickingCenter) return;   // el mode "cercle d'anàlisi" té prioritat
    const llista = persistEpisodis(e.latlng.lat, e.latlng.lng);
    if (llista === null) return;                                         // fora de l'àrea coberta
    let html;
    if (!llista.length){
      html = `<b>Sense persistència</b><br>Cap episodi ≥ ${persist.meta.min_ratxa_min} min amb ≥ 45 dBZ en les últimes ${persist.hores} h.`;
    }else{
      const filesHtml = llista.map(x =>
        `<tr><td style="padding:1px 8px 1px 0">${persistHora(x.ini)}–${persistHora(x.fi)}</td><td style="padding:1px 8px 1px 0">${x.dur} min</td>` +
        `<td style="padding:1px 8px 1px 0">${DBZ_CLASSE_TXT[x.cls] || '≥ 45'} dBZ</td><td style="padding:1px 8px 1px 0">~${x.mm} mm</td>` +
        `<td>${x.enCurs ? '<b style="color:#C8102E">en curs</b>' : ''}</td></tr>`).join('');
      const total = llista.reduce((s, x) => s + x.dur, 0);
      html = `<b>Persistència: ${llista.length} episodi${llista.length > 1 ? 's' : ''} · ${total} min</b>` +
        `<table style="margin-top:4px;border-collapse:collapse;font-size:12px;">${filesHtml}</table>` +
        `<div style="margin-top:4px;opacity:.7;font-size:11px;">Últimes ${persist.hores} h (hora local). mm estimats per Z-R: orientatius.</div>`;
    }
    persist.popup = L.popup({ maxWidth: 360 }).setLatLng(e.latlng).setContent(html).openOn(map);
  });
