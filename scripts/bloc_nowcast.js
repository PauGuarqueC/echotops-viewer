  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----
  // Dades generades per nowcast_export.py a data/nowcast/: avisos.json + avisos.png
  const nowc = { data: null, overlay: null, marcs: L.layerGroup(), actiu: true, timer: null };

  const NOWC_COL = { 1: '#FFC800', 2: '#FF7800', 3: '#E61428' };

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
      nowc.data = await fetch(`data/nowcast/avisos.json?_=${Date.now()}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    }catch(e){
      nowc.data = null;
      console.warn('No s\'han pogut carregar els avisos de nowcasting', e);
    }
  }

  function nowcPinta(){
    if (nowc.overlay){ map.removeLayer(nowc.overlay); nowc.overlay = null; }
    nowc.marcs.clearLayers();
    map.removeLayer(nowc.marcs);
    const info = document.getElementById('nowc-info');
    if (!info) return;
    if (!nowc.actiu){ info.textContent = ''; return; }
    const d = nowc.data;
    if (!d){ info.textContent = 'Sense dades de nowcasting disponibles'; return; }
    const edat = (Date.now() - new Date(d.final_utc).getTime()) / 60000;
    const hora = new Date(d.final_utc).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });
    const vell = edat > 60 ? ` <b style="color:#C8102E">(fa ${Math.round(edat)} min: desactualitzat)</b>` : '';
    const cels = d.cel_les;
    if (!cels.length){
      info.innerHTML = `Cap tempesta enganxada · radar de les ${hora}${vell}`;
      return;
    }
    nowc.overlay = L.imageOverlay(`data/nowcast/avisos.png?_=${encodeURIComponent(d.final_utc)}`, d.bounds, { opacity: 0.95, interactive: false }).addTo(map);
    nowc.overlay.bringToFront();
    cels.forEach(c => {
      const m = L.circleMarker([c.lat, c.lon], { radius: 7 + c.nivell * 2, color: '#fff', weight: 2, fillColor: NOWC_COL[c.nivell], fillOpacity: 0.9 });
      m.on('click', () => {
        if (typeof pickingCenter !== 'undefined' && pickingCenter) return;
        const dbz = { 6: '35–40', 7: '40–45', 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' }[c.classe_max] || '> 35';
        L.popup({ maxWidth: 300 }).setLatLng([c.lat, c.lon]).setContent(
          `<b style="color:${NOWC_COL[c.nivell]}">${c.nom}</b> · enganxada fa <b>${nowcDurada(c.enganxada_min)}</b><br>` +
          `Àrea ~${c.area_km2} km² · màx ${dbz} dBZ<br>` +
          `Des que s'ha parat: ~${c.mm_mitjana} mm de mitjana (fins a ~${c.mm_max} mm)<br>` +
          `Ara: ~${c.mm_h_ara} mm/h → si es manté, ~${Math.round(c.mm_h_ara)} mm en 1 h` +
          `<div style="margin-top:4px;opacity:.7;font-size:11px;">Radar de les ${hora} (hora local). Mm orientatius (Z-R), sense validar amb pluviòmetres.</div>`
        ).openOn(map);
      });
      m.addTo(nowc.marcs);
    });
    nowc.marcs.addTo(map);
    const n = i => cels.filter(c => c.nivell === i).length;
    const fila = (i, nom) => n(i) ? `<span style="color:${NOWC_COL[i]}">●</span> ${n(i)} ${nom}` : '';
    info.innerHTML = [fila(3, 'alerta'), fila(2, 'atenció'), fila(1, 'vigilància')].filter(Boolean).join(' · ') +
      `<br>radar de les ${hora}${vell}`;
  }

  async function nowcActiva(on){
    nowc.actiu = on;
    clearInterval(nowc.timer);
    if (on){
      await nowcCarrega();
      nowc.timer = setInterval(async () => { await nowcCarrega(); nowcPinta(); }, 2 * 60 * 1000);
    }
    nowcPinta();
  }
  nowcActiva(true);
