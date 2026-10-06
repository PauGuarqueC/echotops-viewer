  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----
  // Dades de nowcast_export.py a data/nowcast/: avisos.json/avisos.png (últim fotograma) i historial.json (48 h).
  // La capa segueix l'instant de l'scrubber principal (currentTs, YYYYMMDD_HHMM UTC) via nowcMostra(ts).
  const nowc = { hist: null, ultim: null, overlay: null, marcs: L.layerGroup(), actiu: true, timer: null, ts: null };
  const NOWC_COL = { 1: '#FFC800', 2: '#FF7800', 3: '#E61428' };
  const NOWC_COLS = ['nivell', 'lat', 'lon', 'area_km2', 'enganxada_min', 'classe_max', 'mm_mitjana', 'mm_max', 'mm_h_ara', 's', 'w', 'n', 'e'];

  function nowcDurada(min){
    return min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ' ' + (min % 60) + ' min' : ''}` : `${min} min`;
  }

  const NowcastControl = L.Control.extend({
    options: { position: 'bottomleft' },
    onAdd: function(){
      const div = L.DomUtil.create('div', 'basemap-control');
      div.style.cssText = 'width:230px;color:var(--text);font-size:12px;';
      div.innerHTML = `
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;">
          <input type="checkbox" id="nowc-toggle" checked style="margin-top:2px"> <span><b>Tempestes enganxades</b> (radar AEMET)</span>
        </label>
        <div id="nowc-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>`;
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelector('#nowc-toggle').addEventListener('change', e => nowcActiva(e.target.checked));
      return div;
    },
  });
  map.addControl(new NowcastControl());

  async function nowcCarrega(){
    try{
      const q = `?_=${Date.now()}`;
      const [h, u] = await Promise.all([
        fetch(`data/nowcast/historial.json${q}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
        fetch(`data/nowcast/avisos.json${q}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
      ]);
      nowc.hist = h; nowc.ultim = u;
    }catch(e){
      nowc.hist = nowc.ultim = null;
      console.warn('No s\'han pogut carregar les dades de nowcasting', e);
    }
  }

  const nowcMs = k => Date.UTC(+k.slice(0,4), +k.slice(4,6) - 1, +k.slice(6,8), +k.slice(8,10), +k.slice(10,12));
  const nowcClau = ms => { const d = new Date(ms); const p = n => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}`; };

  function nowcNeteja(){
    if (nowc.overlay){ map.removeLayer(nowc.overlay); nowc.overlay = null; }
    nowc.marcs.clearLayers();
    map.removeLayer(nowc.marcs);
  }

  // Dibuixa l'estat corresponent a l'instant ts de l'scrubber (YYYYMMDD_HHMM, UTC)
  function nowcMostra(ts){
    if (ts) nowc.ts = ts;
    nowcNeteja();
    const info = document.getElementById('nowc-info');
    if (!info) return;
    if (!nowc.actiu){ info.textContent = ''; return; }
    const h = nowc.hist, u = nowc.ultim;
    if (!h || !u){ info.textContent = 'Sense dades de nowcasting disponibles'; return; }
    if (!nowc.ts){ nowc.ts = null; }
    const objectiu = nowc.ts ? nowcMs(nowc.ts.replace('_', '')) : nowcMs(h.final_utc.replace(/[-:TZ]/g, '').slice(0, 12));
    const fi = nowcMs(h.final_utc.replace(/[-:TZ]/g, '').slice(0, 12));
    const pas = (h.pas_min || 10) * 60000;
    const ini = fi - h.hores * 3600000;
    // fotograma AEMET més proper (10 min) a l'instant de l'scrubber
    const ms = Math.round(objectiu / pas) * pas;
    const hora = k => new Date(nowcMs(k)).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });
    if (objectiu > fi + pas || objectiu < ini - pas){
      info.innerHTML = 'Sense dades de radar AEMET per a aquest instant';
      return;
    }
    const clau = nowcClau(Math.min(ms, fi));
    if (h.sense_dades.includes(clau)){
      info.innerHTML = `Falta el fotograma AEMET de les ${hora(clau)}`;
      return;
    }
    const esUltim = clau === nowcClau(fi);
    const cels = esUltim ? u.cel_les : (h.fotogrames[clau] || []).map(f => Object.fromEntries(NOWC_COLS.map((c, i) => [c, f[i]])));
    const nom = { 1: 'Vigilància', 2: 'Atenció', 3: 'Alerta' };
    const edat = (Date.now() - fi) / 60000;
    const vell = esUltim && edat > 60 ? ` <b style="color:#C8102E">(fa ${Math.round(edat)} min: desactualitzat)</b>` : '';
    if (!cels.length){
      info.innerHTML = `Cap tempesta enganxada · radar de les ${hora(clau)}${vell}`;
      return;
    }
    if (esUltim){
      nowc.overlay = L.imageOverlay(`data/nowcast/avisos.png?_=${encodeURIComponent(u.final_utc)}`, u.bounds, { opacity: 0.95, interactive: false }).addTo(map);
      nowc.overlay.bringToFront();
    }
    cels.forEach(c => {
      if (!esUltim){
        L.rectangle([[c.s, c.w], [c.n, c.e]], { color: NOWC_COL[c.nivell], weight: 2, fill: false, interactive: false }).addTo(nowc.marcs);
      }
      const m = L.circleMarker([c.lat, c.lon], { radius: 7 + c.nivell * 2, color: '#fff', weight: 2, fillColor: NOWC_COL[c.nivell], fillOpacity: 0.9 });
      m.on('click', () => {
        if (typeof pickingCenter !== 'undefined' && pickingCenter) return;
        const dbz = { 6: '35–40', 7: '40–45', 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' }[c.classe_max] || '> 35';
        L.popup({ maxWidth: 300 }).setLatLng([c.lat, c.lon]).setContent(
          `<b style="color:${NOWC_COL[c.nivell]}">${nom[c.nivell]}</b> · enganxada fa <b>${nowcDurada(c.enganxada_min)}</b><br>` +
          `Àrea ~${c.area_km2} km² · màx ${dbz} dBZ<br>` +
          `Des que s'ha parat: ~${c.mm_mitjana} mm de mitjana (fins a ~${c.mm_max} mm)<br>` +
          `Aleshores: ~${c.mm_h_ara} mm/h` +
          `<div style="margin-top:4px;opacity:.7;font-size:11px;">Radar de les ${hora(clau)} (hora local). Mm orientatius (Z-R), sense validar amb pluviòmetres.</div>`
        ).openOn(map);
      });
      m.addTo(nowc.marcs);
    });
    nowc.marcs.addTo(map);
    const n = i => cels.filter(c => c.nivell === i).length;
    const fila = (i, t) => n(i) ? `<span style="color:${NOWC_COL[i]}">●</span> ${n(i)} ${t}` : '';
    info.innerHTML = [fila(3, 'alerta'), fila(2, 'atenció'), fila(1, 'vigilància')].filter(Boolean).join(' · ') +
      `<br>radar de les ${hora(clau)}${vell}`;
  }

  async function nowcActiva(on){
    nowc.actiu = on;
    clearInterval(nowc.timer);
    if (on){
      await nowcCarrega();
      nowc.timer = setInterval(async () => { await nowcCarrega(); nowcMostra(); }, 2 * 60 * 1000);
    }
    nowcMostra();
  }
  nowcActiva(true);
