  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----
  // Dades de nowcast_export.py a data/nowcast/: avisos.json (últim fotograma), historial.json (48 h), refl/*.png.
  // La capa segueix l'instant de l'scrubber principal (currentTs, YYYYMMDD_HHMM UTC) via nowcMostra(ts).
  // Els avisos fixos amb so surten només per a les cel·les noves de l'últim fotograma (no en recórrer l'historial).
  const nowc = { hist: null, ultim: null, marcs: L.layerGroup(), actiu: true, timer: null, ts: null, vistos: [], so: true, audio: null, pendent: 0 };
  const refl = { overlay: null, actiu: false };
  const REFL_LLEGENDA = [['rgb(150,215,255)', '15'], ['rgb(70,160,255)', '20'], ['rgb(0,190,220)', '25'], ['rgb(0,190,80)', '30'],
    ['rgb(170,215,0)', '35'], ['rgb(255,235,0)', '40'], ['rgb(255,150,0)', '45'], ['rgb(240,40,20)', '50'],
    ['rgb(170,0,30)', '55'], ['rgb(210,0,170)', '60'], ['rgb(150,60,220)', '65']];
  const NOWC_COL = { 1: '#FFC800', 2: '#FF7800', 3: '#E61428' };
  const NOWC_NOM = { 1: 'Vigilància', 2: 'Atenció', 3: 'Alerta' };
  const NOWC_COLS = ['nivell', 'lat', 'lon', 'area_km2', 'enganxada_min', 'classe_max', 'mm_mitjana', 'mm_max', 'mm_h_ara', 's', 'w', 'n', 'e'];
  const NOWC_DBZ = { 6: '35–40', 7: '40–45', 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' };
  const NOWC_LS = 'nowcast_vistos_v1', NOWC_LS_SO = 'nowcast_so_v1', NOWC_LS_OB = 'nowcast_oberts_v1';
  const nowcOberts = [];   // avisos que continuen oberts: [{id, c, horaTxt}] (es conserven en recarregar la pàgina)
  const nowcDesaOberts = () => { try{ localStorage.setItem(NOWC_LS_OB, JSON.stringify(nowcOberts)); }catch(e){} };

  try{ const v = JSON.parse(localStorage.getItem(NOWC_LS) || '[]'); if (Array.isArray(v)) nowc.vistos = v; }catch(e){}
  try{ if (localStorage.getItem(NOWC_LS_SO) === '0') nowc.so = false; }catch(e){}

  // Contenidor dels avisos fixos: sota la llegenda, a la dreta
  (function(){
    const st = document.createElement('style');
    st.textContent = `
      #nowc-avisos{ position:absolute; top:222px; right:20px; width:250px; z-index:1000; display:flex; flex-direction:column; gap:8px;
        max-height:calc(100vh - 380px); overflow-y:auto; font-family:var(--font-ui); }
      #nowc-avisos .nowc-av{ background:var(--panel); color:var(--text); border:1px solid var(--panel-border); border-left:5px solid #888;
        border-radius:3px; padding:8px 10px; font-size:12px; line-height:1.4; box-shadow:0 2px 10px rgba(0,0,0,.25); position:relative; }
      #nowc-avisos .nowc-av .x{ position:absolute; top:3px; right:6px; cursor:pointer; font-size:16px; line-height:1; opacity:.6; background:none; border:0; color:inherit; padding:2px 4px; }
      #nowc-avisos .nowc-av .x:hover{ opacity:1; }
      #nowc-avisos .nowc-av .cap{ cursor:pointer; padding-right:18px; }
      #nowc-avisos .nowc-tot{ align-self:flex-end; font-size:11px; background:var(--panel); color:var(--text); border:1px solid var(--panel-border); border-radius:3px; padding:3px 8px; cursor:pointer; }
      @media (max-width:640px){ #nowc-avisos{ top:76px; right:8px; width:min(250px, calc(100vw - 16px)); max-height:40vh; } }`;
    document.head.appendChild(st);
    const c = document.createElement('div');
    c.id = 'nowc-avisos';
    document.body.appendChild(c);
  })();

  // avisos.json guarda el quadrat com a bbox [[S,W],[N,E]]; l'historial, com a columnes s,w,n,e
  const nowcNorm = c => (c.s !== undefined) ? c : Object.assign({}, c, { s: c.bbox[0][0], w: c.bbox[0][1], n: c.bbox[1][0], e: c.bbox[1][1] });

  function nowcDurada(min){
    return min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ' ' + (min % 60) + ' min' : ''}` : `${min} min`;
  }
  const nowcHoraLocal = ms => new Date(ms).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });

  // Mateix contingut al popup del mapa i als avisos fixos
  function nowcHtml(c, horaTxt, ara){
    return `<b style="color:${NOWC_COL[c.nivell]}">${NOWC_NOM[c.nivell]}</b> · enganxada fa <b>${nowcDurada(c.enganxada_min)}</b><br>` +
      `Àrea ~${c.area_km2} km² · màx ${NOWC_DBZ[c.classe_max] || '> 35'} dBZ<br>` +
      `Des que s'ha parat: ~${c.mm_mitjana} mm de mitjana (fins a ~${c.mm_max} mm)<br>` +
      `${ara ? 'Ara' : 'Aleshores'}: ~${c.mm_h_ara} mm/h` +
      `<div style="margin-top:4px;opacity:.7;font-size:11px;">Radar de les ${horaTxt} (hora local). Mm orientatius (Z-R), sense validar amb pluviòmetres.</div>`;
  }

  // ---- So (Web Audio; els navegadors només el deixen sonar després d'una interacció de l'usuari) ----
  function nowcAudio(){
    try{
      if (!nowc.audio){ const A = window.AudioContext || window.webkitAudioContext; if (!A) return null; nowc.audio = new A(); }
      return nowc.audio;
    }catch(e){ return null; }
  }
  function nowcPip(ctx, t0, freq){
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine'; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(0.35, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.28);
    o.connect(g); g.connect(ctx.destination); o.start(t0); o.stop(t0 + 0.3);
  }
  function nowcSona(nivell){
    if (!nowc.so) return false;
    const ctx = nowcAudio();
    if (!ctx) return false;
    if (ctx.state === 'suspended'){ ctx.resume().catch(() => {}); }
    if (ctx.state !== 'running'){ nowc.pendent = Math.max(nowc.pendent, nivell); return false; }
    const n = nivell, t = ctx.currentTime + 0.05;          // 1, 2 o 3 pips, més aguts com més greu
    for (let i = 0; i < n; i++) nowcPip(ctx, t + i * 0.4, 660 + 110 * nivell);
    return true;
  }
  ['pointerdown', 'keydown'].forEach(ev => window.addEventListener(ev, () => {
    const ctx = nowcAudio();
    if (ctx && ctx.state === 'suspended') ctx.resume().then(() => { if (nowc.pendent){ const p = nowc.pendent; nowc.pendent = 0; nowcSona(p); } }).catch(() => {});
  }, { passive: true }));

  // ---- Avisos fixos ----
  function nowcTancaAvis(el){
    const i = nowcOberts.findIndex(o => o.id === el.dataset.id);
    if (i >= 0) nowcOberts.splice(i, 1);
    nowcDesaOberts(); el.remove(); nowcResumAvisos();
  }
  function nowcResumAvisos(){
    const c = document.getElementById('nowc-avisos');
    let tot = c.querySelector('.nowc-tot');
    const n = c.querySelectorAll('.nowc-av').length;
    if (n >= 2){
      if (!tot){ tot = document.createElement('button'); tot.className = 'nowc-tot'; tot.textContent = 'Tanca-les totes';
        tot.onclick = () => { c.querySelectorAll('.nowc-av').forEach(e => e.remove()); nowcOberts.length = 0; nowcDesaOberts(); nowcResumAvisos(); }; c.appendChild(tot); }
      else c.appendChild(tot);       // sempre al final
    }else if (tot) tot.remove();
  }
  function nowcMostraAvis(id, c, horaTxt){
    const k = nowcOberts.findIndex(o => o.id === id);
    if (k >= 0) nowcOberts[k] = { id, c, horaTxt }; else nowcOberts.unshift({ id, c, horaTxt });
    if (nowcOberts.length > 12) nowcOberts.length = 12;
    nowcDesaOberts();
    const cont = document.getElementById('nowc-avisos');
    let el = cont.querySelector(`.nowc-av[data-id="${id}"]`);
    if (!el){
      el = document.createElement('div'); el.className = 'nowc-av'; el.dataset.id = id;
      cont.insertBefore(el, cont.firstChild);
      while (cont.querySelectorAll('.nowc-av').length > 12) cont.querySelector('.nowc-av:last-of-type').remove();
    }
    el.style.borderLeftColor = NOWC_COL[c.nivell];
    el.innerHTML = `<button class="x" title="Tanca" aria-label="Tanca">×</button><div class="cap" title="Veure al mapa">${nowcHtml(c, horaTxt, true)}</div>`;
    el.querySelector('.x').onclick = () => nowcTancaAvis(el);
    el.querySelector('.cap').onclick = () => map.fitBounds([[c.s, c.w], [c.n, c.e]], { maxZoom: 10, padding: [60, 60] });
    nowcResumAvisos();
  }

  // Detecta cel·les noves (o que pugen de nivell) a l'últim fotograma i en fa avís
  function nowcRevisaNoves(){
    const u = nowc.ultim;
    if (!u || !nowc.actiu) return;
    const fi = Date.parse(u.final_utc);
    if (Date.now() - fi > 90 * 60000) return;                   // dades velles: no avisem
    const horaTxt = nowcHoraLocal(fi), ara = Date.now();
    nowc.vistos = nowc.vistos.filter(r => ara - r.last < 6 * 3600000);
    let maxNou = 0;
    u.cel_les.map(nowcNorm).forEach(c => {
      const cy = (c.s + c.n) / 2, cx = (c.w + c.e) / 2;
      let r = nowc.vistos.find(v => Math.abs(v.lat - cy) < 0.1 && Math.abs(v.lon - cx) < 0.13 && ara - v.last < 90 * 60000);
      const nova = !r, puja = r && c.nivell > r.nivell;
      if (!r){ r = { id: 'a' + ara + Math.round(Math.random() * 1e4), nivell: 0 }; nowc.vistos.push(r); }
      if (nova || puja){ nowcMostraAvis(r.id, c, horaTxt); maxNou = Math.max(maxNou, c.nivell); }
      Object.assign(r, { lat: cy, lon: cx, nivell: Math.max(r.nivell, c.nivell), last: ara });
    });
    try{ localStorage.setItem(NOWC_LS, JSON.stringify(nowc.vistos)); }catch(e){}
    if (maxNou) nowcSona(maxNou);
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
        <div id="nowc-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:center;cursor:pointer;margin-top:6px;">
          <input type="checkbox" id="nowc-so"> <span>So d'avís</span>
          <a href="#" id="nowc-prova" style="margin-left:auto;font-size:11px;">prova</a>
        </label>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:8px;">
          <input type="checkbox" id="refl-toggle" style="margin-top:2px"> <span>Reflectivitat radar (AEMET)</span>
        </label>
        <div id="refl-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>`;
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelector('#nowc-toggle').addEventListener('change', e => nowcActiva(e.target.checked));
      div.querySelector('#refl-toggle').addEventListener('change', e => { refl.actiu = e.target.checked; reflMostra(); });
      const so = div.querySelector('#nowc-so');
      so.checked = nowc.so;
      so.addEventListener('change', e => { nowc.so = e.target.checked; try{ localStorage.setItem(NOWC_LS_SO, nowc.so ? '1' : '0'); }catch(_){} });
      div.querySelector('#nowc-prova').addEventListener('click', e => { e.preventDefault(); const ok = nowcSona(2); if (!ok && !nowc.so) alert('El so està desactivat.'); });
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
    nowc.marcs.clearLayers();
    map.removeLayer(nowc.marcs);
  }

  // Estat corresponent a l'instant ts de l'scrubber (YYYYMMDD_HHMM, UTC)
  function nowcMostra(ts){
    if (ts) nowc.ts = ts;
    nowcMostraAvisos();
    reflMostra();
  }

  function nowcMostraAvisos(){
    nowcNeteja();
    const info = document.getElementById('nowc-info');
    if (!info) return;
    if (!nowc.actiu){ info.textContent = ''; return; }
    const h = nowc.hist, u = nowc.ultim;
    if (!h || !u){ info.textContent = 'Sense dades de nowcasting disponibles'; return; }
    const fi = nowcMs(h.final_utc.replace(/[-:TZ]/g, '').slice(0, 12));
    const objectiu = nowc.ts ? nowcMs(nowc.ts.replace('_', '')) : fi;
    const pas = (h.pas_min || 10) * 60000;
    const ini = fi - h.hores * 3600000;
    const hora = k => nowcHoraLocal(nowcMs(k));
    if (objectiu > fi + pas || objectiu < ini - pas){
      info.innerHTML = 'Sense dades de radar AEMET per a aquest instant';
      return;
    }
    const clau = nowcClau(Math.min(Math.round(objectiu / pas) * pas, fi));
    if (h.sense_dades.includes(clau)){
      info.innerHTML = `Falta el fotograma AEMET de les ${hora(clau)}`;
      return;
    }
    const esUltim = clau === nowcClau(fi);
    const cels = esUltim ? u.cel_les.map(nowcNorm) : (h.fotogrames[clau] || []).map(f => Object.fromEntries(NOWC_COLS.map((c, i) => [c, f[i]])));
    const edat = (Date.now() - fi) / 60000;
    const vell = esUltim && edat > 60 ? ` <b style="color:#C8102E">(fa ${Math.round(edat)} min: desactualitzat)</b>` : '';
    if (!cels.length){
      info.innerHTML = `Cap tempesta enganxada · radar de les ${hora(clau)}${vell}`;
      return;
    }
    cels.forEach(c => {
      // quadrat de la cel·la + punt al mig
      L.rectangle([[c.s, c.w], [c.n, c.e]], { color: NOWC_COL[c.nivell], weight: 2, fillColor: NOWC_COL[c.nivell], fillOpacity: 0.08, interactive: false }).addTo(nowc.marcs);
      const centre = [(c.s + c.n) / 2, (c.w + c.e) / 2];
      const m = L.circleMarker(centre, { radius: 7 + c.nivell * 2, color: '#fff', weight: 2, fillColor: NOWC_COL[c.nivell], fillOpacity: 0.95 });
      m.on('click', () => {
        if (typeof pickingCenter !== 'undefined' && pickingCenter) return;
        L.popup({ maxWidth: 300 }).setLatLng(centre).setContent(nowcHtml(c, hora(clau), esUltim)).openOn(map);
      });
      m.addTo(nowc.marcs);
    });
    nowc.marcs.addTo(map);
    const n = i => cels.filter(c => c.nivell === i).length;
    const fila = (i, t) => n(i) ? `<span style="color:${NOWC_COL[i]}">●</span> ${n(i)} ${t}` : '';
    info.innerHTML = [fila(3, 'alerta'), fila(2, 'atenció'), fila(1, 'vigilància')].filter(Boolean).join(' · ') +
      `<br>radar de les ${hora(clau)}${vell}`;
  }

  // Imatge de reflectivitat (data/nowcast/refl/YYYYMMDDHHMM.png) de l'instant més proper al de l'scrubber
  function reflMostra(){
    if (refl.overlay){ map.removeLayer(refl.overlay); refl.overlay = null; }
    const info = document.getElementById('refl-info');
    if (!info) return;
    const u = nowc.ultim;
    if (!refl.actiu){ info.textContent = ''; return; }
    if (!u){ info.textContent = 'Sense dades de radar disponibles'; return; }
    const fi = nowcMs(u.final_utc.replace(/[-:TZ]/g, '').slice(0, 12));
    const pas = 600000;
    const hores = nowc.hist ? nowc.hist.hores : 48;
    const objectiu = nowc.ts ? nowcMs(nowc.ts.replace('_', '')) : fi;
    if (objectiu > fi + pas || objectiu < fi - hores * 3600000 - pas){
      info.textContent = 'Sense imatge de radar per a aquest instant';
      return;
    }
    const clau = nowcClau(Math.min(Math.round(objectiu / pas) * pas, fi));
    const hora = nowcHoraLocal(nowcMs(clau));
    const llegenda = '<div style="display:flex;margin-top:3px;">' + REFL_LLEGENDA.map(([c, v]) =>
      `<span title="≥ ${v} dBZ" style="flex:1;height:8px;background:${c}"></span>`).join('') +
      '</div><div style="display:flex;justify-content:space-between;opacity:.7;"><span>15</span><span>40</span><span>65+ dBZ</span></div>';
    info.innerHTML = `Radar de les ${hora}` + llegenda;
    const ov = L.imageOverlay(`data/nowcast/refl/${clau}.png`, u.bounds, { opacity: 0.75, interactive: false });
    ov.on('error', () => { if (refl.overlay === ov){ map.removeLayer(ov); refl.overlay = null; info.innerHTML = `Falta la imatge del radar de les ${hora}`; } });
    refl.overlay = ov.addTo(map);
    ov.bringToBack();
  }

  async function nowcActiva(on){
    nowc.actiu = on;
    if (on && !nowc.ultim) await nowcCarrega();
    nowcMostra();
    if (on) nowcRevisaNoves();
  }
  // Restaura els avisos que van quedar oberts abans de recarregar la pàgina (sense so)
  try{
    const ob = JSON.parse(localStorage.getItem(NOWC_LS_OB) || '[]');
    if (Array.isArray(ob)) ob.slice().reverse().forEach(o => { if (o && o.c && o.id) nowcMostraAvis(o.id, o.c, o.horaTxt); });
  }catch(e){}
  async function nowcCicle(){ await nowcCarrega(); nowcMostra(); nowcRevisaNoves(); }
  nowcCicle();
  nowc.timer = setInterval(nowcCicle, 2 * 60 * 1000);
  // ---- fi Tempestes enganxades ----
