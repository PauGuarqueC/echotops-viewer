  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----
  // Dades de nowcast_export.py a data/nowcast/: avisos.json (últim fotograma), historial.json (48 h), refl/*.png.
  // La capa segueix l'instant de l'scrubber principal (currentTs, YYYYMMDD_HHMM UTC) via nowcMostra(ts).
  // Els avisos fixos amb so surten només per a les cel·les noves de l'últim fotograma (no en recórrer l'historial).
  const nowc = { hist: null, ultim: null, marcs: L.layerGroup(), actiu: true, timer: null, ts: null, vistos: [], so: true, audio: null, pendent: 0,
    mov: null, movActiu: false, movCapa: L.layerGroup() };
  const refl = { overlay: null, actiu: false };
  const REFL_LLEGENDA = [['rgb(150,215,255)', '15'], ['rgb(70,160,255)', '20'], ['rgb(0,190,220)', '25'], ['rgb(0,190,80)', '30'],
    ['rgb(170,215,0)', '35'], ['rgb(255,235,0)', '40'], ['rgb(255,150,0)', '45'], ['rgb(240,40,20)', '50'],
    ['rgb(170,0,30)', '55'], ['rgb(210,0,170)', '60'], ['rgb(150,60,220)', '65']];
  const NOWC_COL = { 1: '#FFC800', 2: '#FF7800', 3: '#E61428' };
  const NOWC_NOM = { 1: 'Vigilància', 2: 'Atenció', 3: 'Alerta' };
  const NOWC_COLS = ['nivell', 'lat', 'lon', 'area_km2', 'enganxada_min', 'classe_max', 'mm_mitjana', 'mm_max', 'mm_h_ara', 's', 'w', 'n', 'e', 'dist_costa_km'];
  const NOWC_DBZ = { 6: '35–40', 7: '40–45', 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' };
  const NOWC_LS = 'nowcast_vistos_v1', NOWC_LS_SO = 'nowcast_so_v1', NOWC_LS_OB = 'nowcast_oberts_v1', NOWC_LS_MOV = 'nowcast_mov_v1';
  const nowcOberts = [];   // avisos que continuen oberts: [{id, c, horaTxt}] (es conserven en recarregar la pàgina)
  const nowcDesaOberts = () => { try{ localStorage.setItem(NOWC_LS_OB, JSON.stringify(nowcOberts)); }catch(e){} };

  try{ const v = JSON.parse(localStorage.getItem(NOWC_LS) || '[]'); if (Array.isArray(v)) nowc.vistos = v; }catch(e){}
  try{ if (localStorage.getItem(NOWC_LS_SO) === '0') nowc.so = false; }catch(e){}
  try{ if (localStorage.getItem(NOWC_LS_MOV) === '1') nowc.movActiu = true; }catch(e){}

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
      .nowc-mv{ background:none; border:0; }
      .nowc-mv .nowc-svg{ position:absolute; left:0; top:0; pointer-events:none; filter:drop-shadow(0 1px 1.5px rgba(0,0,0,.45)); }
      .nowc-mv .nowc-dot{ position:absolute; left:19px; top:19px; width:10px; height:10px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px rgba(11,19,32,.6), 0 1px 4px rgba(0,0,0,.5); box-sizing:border-box; }
      .nowc-mv .nowc-pill{ position:absolute; left:34px; top:28px; white-space:nowrap; font:600 10.5px/1 var(--font-mono, monospace); color:#fff;
        background:rgba(11,19,32,.82); border:1px solid rgba(255,255,255,.28); border-radius:9px; padding:3px 6px; box-shadow:0 1px 4px rgba(0,0,0,.4); pointer-events:none; }
      .nowc-zoom-baix .nowc-mv .nowc-pill{ display:none; }
      .nowc-tk{ background:none; border:0; }
      .nowc-tk .nowc-tk-t{ position:absolute; transform:translate(-50%, 6px); font:600 9.5px/1 var(--font-mono, monospace); color:#fff; white-space:nowrap;
        text-shadow:0 0 3px #000, 0 0 3px #000, 0 0 5px #000; pointer-events:none; }
      .nowc-pop-v{ font-size:18px; font-weight:700; line-height:1.2; }
      .nowc-pop-v span{ font-size:12px; font-weight:500; opacity:.65; }
      .nowc-pop-s{ font-size:11.5px; opacity:.65; margin-top:2px; }
      .nowc-ctl{ width:230px; color:var(--text); font-size:12px; }
      .nowc-ctl .nowc-cap{ display:none; cursor:pointer; font-weight:600; align-items:center; justify-content:space-between; gap:8px; }
      @media (max-width:640px){
        #nowc-avisos{ top:76px; right:8px; left:8px; width:auto; max-width:280px; margin-left:auto; max-height:34vh; gap:6px; }
        #nowc-avisos .nowc-av{ font-size:11px; line-height:1.3; padding:6px 8px; }
        #nowc-avisos .nowc-av .x{ font-size:20px; padding:4px 8px; top:0; right:0; }
        html, body{ overflow-x:hidden; }
        #topbar{ flex-direction:column; align-items:stretch; gap:6px; padding:8px 10px; }
        #topbar .brand{ gap:4px 8px; }
        #topbar .brand .mark{ font-size:10px; padding:2px 6px; }
        #topbar .subtitle{ display:none; }
        #status{ flex-wrap:wrap; gap:6px; padding:5px 8px; font-size:11px; }
        #status button{ margin-left:0 !important; font-size:11px; padding:5px 8px; }
        .nowc-ctl{ width:min(230px, calc(100vw - 24px)); font-size:13px; }
        .nowc-ctl .nowc-cap{ display:flex; }
        .nowc-ctl.col .nowc-body{ display:none; }
        .nowc-ctl:not(.col) .nowc-cap{ margin-bottom:6px; padding-bottom:6px; border-bottom:1px solid var(--panel-border); }
        .nowc-ctl input[type=checkbox]{ width:18px; height:18px; }
      }`;
    document.head.appendChild(st);
    const c = document.createElement('div');
    c.id = 'nowc-avisos';
    document.body.appendChild(c);
  })();

  // avisos.json guarda el quadrat com a bbox [[S,W],[N,E]]; l'historial, com a columnes s,w,n,e
  const NOWC_COL_MAR = '#7fa6c9';
  const nowcEsMar = c => c.mar === true || (c.dist_costa_km > (nowc.ultim && nowc.ultim.parametres && nowc.ultim.parametres.dist_costa_km || 20));
  const nowcNorm = c => (c.s !== undefined) ? c : Object.assign({}, c, { s: c.bbox[0][0], w: c.bbox[0][1], n: c.bbox[1][0], e: c.bbox[1][1] });

  function nowcDurada(min){
    return min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ' ' + (min % 60) + ' min' : ''}` : `${min} min`;
  }
  const nowcHoraLocal = ms => new Date(ms).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Europe/Madrid' });

  const NOWC_RUMBS = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];
  const nowcRumbTxt = g => NOWC_RUMBS[Math.round(g / 45) % 8];
  // Text de moviment: "quasi estàtica" per sota de 8 km/h
  function nowcMovTxt(vel, rumb){
    if (vel === null || vel === undefined) return 'encara no calculable (cel·la recent)';
    if (vel < 8) return `quasi estàtica (~${vel} km/h)`;
    return `<b>~${vel} km/h</b> cap al ${nowcRumbTxt(rumb)} (${rumb}°)`;
  }

  // Mateix contingut al popup del mapa i als avisos fixos
  function nowcHtml(c, horaTxt, ara){
    const f = (t, v) => `<div style="margin-top:2px;"><span style="opacity:.7">${t}</span> ${v}</div>`;
    const mar = nowcEsMar(c);
    return (mar ? `<b style="color:${NOWC_COL_MAR}">Sobre el mar</b>` : `<b style="color:${NOWC_COL[c.nivell]}">${NOWC_NOM[c.nivell]}</b>`) + ` · radar de les ${horaTxt}` +
      `<div style="margin-top:2px;">Tempesta aturada fa <b>${nowcDurada(c.enganxada_min)}</b></div>` +
      (mar ? `<div style="margin-top:2px;opacity:.8">A ~${c.dist_costa_km} km de la costa: no genera avís</div>` : '') +
      f('Intensitat de pluja:', `<b>~${c.mm_h_ara} mm/h</b>`) +
      f('Acumulat des que s\'ha aturat:', `<b>~${c.mm_mitjana} mm</b> de mitjana · fins a <b>~${c.mm_max} mm</b>`) +
      f('Reflectivitat màxima:', `${NOWC_DBZ[c.classe_max] || '> 35'} dBZ`) +
      (c.mov ? f('Moviment:', nowcMovTxt(c.mov.vel, c.mov.rumb)) : '');
  }
  // Adjunta a cada cel·la el moviment de la pista més propera del mateix fotograma
  function nowcAdjuntaMov(cels, clau){
    const fr = nowc.mov && nowc.mov.frames && nowc.mov.frames[clau];
    if (!fr) return cels;
    cels.forEach(c => {
      const cy = (c.s + c.n) / 2, cx = (c.w + c.e) / 2;
      let best = null, bd = 1e9;
      fr.forEach(r => { const d = Math.hypot(r[1] - cy, r[2] - cx); if (d < bd){ bd = d; best = r; } });
      if (best && bd < 0.1) c.mov = { vel: best[3], rumb: best[4] };
    });
    return cels;
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
    nowcAdjuntaMov(u.cel_les.map(nowcNorm), nowcClau(fi)).filter(c => !nowcEsMar(c)).forEach(c => {
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
      div.className += ' nowc-ctl';
      div.innerHTML = `<div class="nowc-cap"><span>Tempestes enganxades</span><span class="nowc-fl">▾</span></div><div class="nowc-body">
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;">
          <input type="checkbox" id="nowc-toggle" checked style="margin-top:2px"> <span><b>Tempestes enganxades</b> (radar AEMET)</span>
        </label>
        <div id="nowc-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:center;cursor:pointer;margin-top:6px;">
          <input type="checkbox" id="nowc-so"> <span>So d'avís</span>
          <a href="#" id="nowc-prova" style="margin-left:auto;font-size:11px;">prova</a>
        </label>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:8px;">
          <input type="checkbox" id="refl-toggle" style="margin-top:2px"> <span>Reflectivitat radar (AEMET) <i style="opacity:.7">— substitueix els echotops</i></span>
        </label>
        <div id="refl-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:8px;">
          <input type="checkbox" id="mov-toggle" style="margin-top:2px"> <span>Moviment (rastre i velocitat)</span>
        </label>
        <div id="mov-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div></div>`;
      const cap = div.querySelector('.nowc-cap');
      const fl = div.querySelector('.nowc-fl');
      const plega = c => { div.classList.toggle('col', c); fl.textContent = c ? '▴' : '▾'; nowcAjustaMobil(); };
      cap.addEventListener('click', () => plega(!div.classList.contains('col')));
      if (window.matchMedia('(max-width:640px)').matches) plega(true);
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelector('#nowc-toggle').addEventListener('change', e => nowcActiva(e.target.checked));
      const mt = div.querySelector('#mov-toggle');
      mt.checked = nowc.movActiu;
      mt.addEventListener('change', e => { nowc.movActiu = e.target.checked; try{ localStorage.setItem(NOWC_LS_MOV, nowc.movActiu ? '1' : '0'); }catch(_){} nowcMovMostra(); });
      div.querySelector('#refl-toggle').addEventListener('change', e => { refl.actiu = e.target.checked; reflMostra(); });
      const so = div.querySelector('#nowc-so');
      so.checked = nowc.so;
      so.addEventListener('change', e => { nowc.so = e.target.checked; try{ localStorage.setItem(NOWC_LS_SO, nowc.so ? '1' : '0'); }catch(_){} });
      div.querySelector('#nowc-prova').addEventListener('click', e => { e.preventDefault(); const ok = nowcSona(2); if (!ok && !nowc.so) alert('El so està desactivat.'); });
      return div;
    },
  });
  map.addControl(new NowcastControl());

  // Mòbil: alça els controls inferiors per damunt de la barra de temps i baixa els avisos sota la capçalera
  function nowcAjustaMobil(){
    const mobil = window.matchMedia('(max-width:640px)').matches;
    const bl = document.querySelector('.leaflet-bottom.leaflet-left');
    const tl = document.getElementById('timeline-wrap');
    if (bl) bl.style.marginBottom = (mobil && tl) ? (tl.offsetHeight + 4) + 'px' : '';
    const av = document.getElementById('nowc-avisos');
    const tb = document.getElementById('topbar');
    if (av) av.style.top = (mobil && tb) ? (tb.offsetHeight + 8) + 'px' : '';
  }
  const nowcZoom = () => map.getContainer().classList.toggle('nowc-zoom-baix', map.getZoom() < 8);
  map.on('zoomend', nowcZoom); nowcZoom();
  nowcAjustaMobil();
  window.addEventListener('resize', nowcAjustaMobil);
  window.addEventListener('orientationchange', nowcAjustaMobil);
  setTimeout(nowcAjustaMobil, 500);

  async function nowcCarrega(){
    try{
      const q = `?_=${Date.now()}`;
      const [h, u] = await Promise.all([
        fetch(`data/nowcast/historial.json${q}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
        fetch(`data/nowcast/avisos.json${q}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
      ]);
      nowc.hist = h; nowc.ultim = u;
      try{ const r = await fetch(`data/nowcast/moviment.json${q}`); nowc.mov = r.ok ? await r.json() : null; }catch(_){ nowc.mov = null; }
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
    nowcMovMostra();
    reflMostra();
  }

  // Paleta sobria: blanc suau per a les cel·les que es mouen, gris per a les quasi quietes
  const NOWC_MOV_COL = '#f1f3f5', NOWC_MOV_COL_LENT = '#8f9ba7';
  const nowcMovCol = vel => (vel === null || vel === undefined || vel < 8) ? NOWC_MOV_COL_LENT : NOWC_MOV_COL;
  // Moviment de totes les cel·les intenses: rastre (última hora), fletxa de direcció i velocitat
  function nowcMovMostra(){
    nowc.movCapa.clearLayers();
    map.removeLayer(nowc.movCapa);
    const info = document.getElementById('mov-info');
    if (!info) return;
    if (!nowc.movActiu){ info.textContent = ''; return; }
    const D = nowc.mov;
    if (!D){ info.textContent = 'Sense dades de moviment'; return; }
    const fi = nowcMs(D.final_utc.replace(/[-:TZ]/g, '').slice(0, 12));
    const pas = (D.pas_min || 10) * 60000;
    const objectiu = nowc.ts ? nowcMs(nowc.ts.replace('_', '')) : fi;
    if (objectiu > fi + pas || objectiu < fi - D.hores * 3600000 - pas){
      info.textContent = `Moviment disponible només per a les últimes ${D.hores} h`;
      return;
    }
    const clau = nowcClau(Math.min(Math.round(objectiu / pas) * pas, fi));
    const ms = nowcMs(clau);
    const fr = D.frames[clau];
    if (!fr){ info.textContent = `Sense dades de moviment per a les ${nowcHoraLocal(ms)}`; return; }
    const idx = {};
    const pos = i => { const k = nowcClau(ms - i * pas); if (!(k in idx)) idx[k] = D.frames[k] ? Object.fromEntries(D.frames[k].map(r => [r[0], r])) : null; return idx[k]; };
    const pasMin = D.pas_min || 10;
    const NOWC_RASTRE_MIN = 180;                 // longitud màxima del rastre (mentre la cel·la es pugui seguir)
    fr.forEach(r => {
      const [id, lat, lon, vel, rumb] = r;
      const col = nowcMovCol(vel);
      // posicions de l'última hora (de la més antiga a la més recent) i suavitzat [1 2 1]/4 per treure el soroll del centroide
      let pts = [];
      // de la posició actual cap enrere; es talla si hi ha un salt irreal (canvi d'identitat de la cel·la en fusions/divisions)
      let forats = 0;
      for (let i = 0; i <= NOWC_RASTRE_MIN / pasMin; i++){
        const p = pos(i); if (!(p && p[id])) { if (++forats > 3) break; continue; }
        forats = 0;
        const q = [p[id][1], p[id][2]], ult = pts[pts.length - 1];
        if (ult && Math.hypot(q[0] - ult[0], (q[1] - ult[1]) * 0.75) > 0.2) break;
        pts.push(q);
      }
      pts.reverse();
      if (pts.length >= 3){
        const sm = pts.map((p, q) => (q === 0 || q === pts.length - 1) ? p :
          [(pts[q - 1][0] + 2 * p[0] + pts[q + 1][0]) / 4, (pts[q - 1][1] + 2 * p[1] + pts[q + 1][1]) / 4]);
        pts = sm;
      }
      const nseg = pts.length - 1;
      // rastre: segments que es van esvaint cap al passat, amb contorn fosc per llegir-se sobre qualsevol mapa
      for (let q = 1; q <= nseg; q++){
        const f = q / nseg, seg = [pts[q - 1], pts[q]];
        L.polyline(seg, { color: '#0b1320', weight: 2.5 + 3 * f, opacity: 0.12 + 0.35 * f, lineCap: 'round', interactive: false }).addTo(nowc.movCapa);
        L.polyline(seg, { color: col, weight: 1.2 + 2.2 * f, opacity: 0.2 + 0.75 * f, lineCap: 'round', interactive: false }).addTo(nowc.movCapa);
      }
      // marques de temps cada 10 min i etiqueta a l'extrem més antic
      for (let q = 0; q < nseg; q++){
        L.circleMarker(pts[q], { radius: 1.4 + 1.2 * (q / Math.max(1, nseg)), color: '#0b1320', weight: 0.6, fillColor: col, fillOpacity: 0.85, opacity: 0.8, interactive: false }).addTo(nowc.movCapa);
      }
      for (let q = 0; q < nseg; q++){            // etiquetes cada hora i a l'extrem més antic (si passa de 30 min)
        const min = (nseg - q) * pasMin;
        if (min % 60 === 0 || (q === 0 && min >= 30)){
          L.marker(pts[q], { interactive: false, keyboard: false, icon: L.divIcon({ className: 'nowc-tk', iconSize: [0, 0],
            html: `<span class="nowc-tk-t">−${min % 60 === 0 ? (min / 60) + ' h' : min + '′'}</span>` }) }).addTo(nowc.movCapa);
        }
      }
      // cap de la cel·la: fletxa orientada + etiqueta de velocitat
      const mou = vel !== null && vel >= 8;
      const pill = vel === null ? '' : `<span class="nowc-pill">${vel < 8 ? 'quasi quieta' : vel + ' km/h'}</span>`;
      const fletxa = mou ? `<svg class="nowc-svg" width="48" height="48" viewBox="-24 -24 48 48" style="transform:rotate(${rumb}deg)">
          <path d="M0 -4 L0 -15" stroke="#0b1320" stroke-opacity=".55" stroke-width="6" stroke-linecap="round" fill="none"/>
          <path d="M0 -23 L7.5 -11 L0 -14.5 L-7.5 -11 Z" fill="#0b1320" fill-opacity=".55" stroke="#0b1320" stroke-opacity=".55" stroke-width="3.5" stroke-linejoin="round"/>
          <path d="M0 -4 L0 -15" stroke="${col}" stroke-width="3" stroke-linecap="round" fill="none"/>
          <path d="M0 -22 L6.2 -11.6 L0 -14.8 L-6.2 -11.6 Z" fill="${col}" stroke="#fff" stroke-width="1" stroke-linejoin="round"/></svg>` : '';
      const m = L.marker([lat, lon], { keyboard: false, icon: L.divIcon({ className: 'nowc-mv', iconSize: [48, 48], iconAnchor: [24, 24],
        html: `${fletxa}<span class="nowc-dot" style="background:${col}"></span>${pill}` }) });
      const txt = `<div class="nowc-pop"><div class="nowc-pop-v">${vel === null ? '—' : (vel < 8 ? 'Quasi quieta' : vel + ' km/h')}` +
        `${mou ? ` <span>cap al ${nowcRumbTxt(rumb)}</span>` : ''}</div>` +
        `<div class="nowc-pop-s">${vel === null ? 'Encara no calculable (cel·la recent)' : (mou ? `Rumb ${rumb}° · ` : '') + `~${vel} km/h`}` +
        `${nseg > 0 ? ` · rastre de ${nowcDurada(nseg * pasMin)}` : ''}</div></div>`;
      m.on('click', () => { if (typeof pickingCenter !== 'undefined' && pickingCenter) return;
        L.popup({ maxWidth: 260 }).setLatLng([lat, lon]).setContent(txt).openOn(map); });
      m.addTo(nowc.movCapa);
    });
    nowc.movCapa.addTo(map);
    const nMou = fr.filter(r => r[3] !== null && r[3] >= 8).length;
    info.innerHTML = `${fr.length} cel·les intenses · ${nMou} en moviment`;
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
    const cels = nowcAdjuntaMov(esUltim ? u.cel_les.map(nowcNorm) : (h.fotogrames[clau] || []).map(f => Object.fromEntries(NOWC_COLS.map((c, i) => [c, f[i]]))), clau);
    const edat = (Date.now() - fi) / 60000;
    const vell = esUltim && edat > 60 ? ` <b style="color:#C8102E">(fa ${Math.round(edat)} min: desactualitzat)</b>` : '';
    if (!cels.length){
      info.innerHTML = `Cap tempesta enganxada · radar de les ${hora(clau)}${vell}`;
      return;
    }
    cels.forEach(c => {
      // quadrat de la cel·la + punt al mig
      const mar = nowcEsMar(c);
      const col = mar ? NOWC_COL_MAR : NOWC_COL[c.nivell];
      L.rectangle([[c.s, c.w], [c.n, c.e]], { color: col, weight: mar ? 1.5 : 2, dashArray: mar ? '5 5' : null, fillColor: col, fillOpacity: mar ? 0.05 : 0.08, interactive: false }).addTo(nowc.marcs);
      const centre = [(c.s + c.n) / 2, (c.w + c.e) / 2];
      const m = L.circleMarker(centre, { radius: mar ? 6 : 7 + c.nivell * 2, color: '#fff', weight: 2, fillColor: col, fillOpacity: mar ? 0.7 : 0.95 });
      m.on('click', () => {
        if (typeof pickingCenter !== 'undefined' && pickingCenter) return;
        L.popup({ maxWidth: 300 }).setLatLng(centre).setContent(nowcHtml(c, hora(clau), esUltim)).openOn(map);
      });
      m.addTo(nowc.marcs);
    });
    nowc.marcs.addTo(map);
    const terra = cels.filter(c => !nowcEsMar(c)), nMar = cels.length - terra.length;
    const n = i => terra.filter(c => c.nivell === i).length;
    const fila = (i, t) => n(i) ? `<span style="color:${NOWC_COL[i]}">●</span> ${n(i)} ${t}` : '';
    info.innerHTML = [fila(3, 'alerta'), fila(2, 'atenció'), fila(1, 'vigilància'),
        nMar ? `<span style="color:${NOWC_COL_MAR}">●</span> ${nMar} a mar` : ''].filter(Boolean).join(' · ') +
      `<br>radar de les ${hora(clau)}${vell}`;
  }

  // Imatge de reflectivitat (data/nowcast/refl/YYYYMMDDHHMM.png) de l'instant més proper al de l'scrubber
  // Echotops i reflectivitat són excloents: amb la reflectivitat visible s'amaga la capa d'echotops i la seva llegenda
  function reflExcl(){
    const on = !!refl.overlay;
    if (typeof currentOverlay !== 'undefined' && currentOverlay) currentOverlay.setOpacity(on ? 0 : 0.85);
    const lg = document.getElementById('legend');
    if (lg) lg.style.display = on ? 'none' : '';
  }
  function reflMostra(){
    if (refl.overlay){ map.removeLayer(refl.overlay); refl.overlay = null; }
    reflExcl(); setTimeout(reflExcl, 0);
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
    ov.on('error', () => { if (refl.overlay === ov){ map.removeLayer(ov); refl.overlay = null; reflExcl(); info.innerHTML = `Falta la imatge del radar de les ${hora}`; } });
    refl.overlay = ov.addTo(map);
    ov.bringToBack();
    reflExcl(); setTimeout(reflExcl, 0);
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
