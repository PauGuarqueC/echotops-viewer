  // ---- Tempestes enganxades (nowcasting, compost AEMET) ----
  // Dades de nowcast_export.py a data/nowcast/: avisos.json (últim fotograma), historial.json (48 h), refl/*.png.
  // La capa segueix l'instant de l'scrubber principal (currentTs, YYYYMMDD_HHMM UTC) via nowcMostra(ts).
  // Els avisos fixos amb so surten només per a les cel·les noves de l'últim fotograma (no en recórrer l'historial).
  const nowc = { hist: null, ultim: null, marcs: L.layerGroup(), actiu: true, timer: null, ts: null, vistos: [], so: true, audio: null, pendent: 0,
    mov: null, movActiu: false, movCapa: L.layerGroup() };
  const refl = { overlay: null, actiu: false, mode: 'echo' };
  const capaM = m => CAPA_MODES[m] || ((typeof m === 'string' && m.indexOf('mod:') === 0) ? [false, false] : null);
  const CAPA_MODES = { 'echo': [false, false], 'refl': [true, false], 'sat': [false, true], 'echo+sat': [false, true], 'refl+sat': [true, true] };
  const mod = { models: {}, sel: null, t: null, acum: 0, overlay: null, cur: null, cache: {}, token: 0, pendent: null, cs: null, aplica: null };
  const sat = { actiu: false, op: 65, capa: null, time: null, errs: 0 };
  const REFL_LLEGENDA = [['rgb(150,215,255)', '15'], ['rgb(70,160,255)', '20'], ['rgb(0,190,220)', '25'], ['rgb(0,190,80)', '30'],
    ['rgb(170,215,0)', '35'], ['rgb(255,235,0)', '40'], ['rgb(255,150,0)', '45'], ['rgb(240,40,20)', '50'],
    ['rgb(170,0,30)', '55'], ['rgb(210,0,170)', '60'], ['rgb(150,60,220)', '65']];
  const NOWC_COL = { 1: '#FFC800', 2: '#FF7800', 3: '#E61428' };
  const NOWC_NOM = { 1: 'Vigilància', 2: 'Atenció', 3: 'Alerta' };
  const NOWC_COLS = ['nivell', 'lat', 'lon', 'area_km2', 'enganxada_min', 'classe_max', 'mm_mitjana', 'mm_max', 'mm_h_ara', 's', 'w', 'n', 'e', 'dist_costa_km'];
  const NOWC_DBZ = { 6: '35–40', 7: '40–45', 8: '45–50', 9: '50–55', 10: '55–60', 11: '60–65', 12: '> 65' };
  const lim = { com: undefined, carregant: false };
  const NOWC_LS = 'nowcast_vistos_v1', NOWC_LS_SO = 'nowcast_so_v1', NOWC_LS_OB = 'nowcast_oberts_v1', NOWC_LS_MOV = 'nowcast_mov_v1', NOWC_LS_SAT = 'nowcast_sat_v2', NOWC_LS_CAPA = 'nowcast_capa_v1';
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
      .nowc-sec{ font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; opacity:.65; }
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

  // ---- Evolució de la tempesta: intensitat (línia, mm/h) i acumulació (barres, mm) al llarg del temps ----
  // L'historial no porta identificador de cel·la: se segueix pel fotograma veí més proper amb una durada d'aturada coherent.
  // Si moviment.json porta la intensitat de cada pista, es dibuixa tota la vida de la cel·la (des de la primera detecció)
  function nowcSeriePista(c, clau){
    const D = nowc.mov;
    if (!D || !D.columnes || D.columnes.indexOf('mm_h') < 0 || !D.frames[clau]) return null;
    const pas = (D.pas_min || 10) * 60000, h = (D.pas_min || 10) / 60;
    const cy = (c.s + c.n) / 2, cx = (c.w + c.e) / 2;
    // fila de partida: la pista més propera al centre de la cel·la (preferint la del mateix id)
    let r0 = null, bd = 0.12;
    D.frames[clau].forEach(r => { const d = Math.hypot(r[1] - cy, r[2] - cx) - ((c.mov && c.mov.id === r[0]) ? 0.03 : 0); if (d < bd){ bd = d; r0 = r; } });
    if (!r0) return null;
    // se segueix la cel·la fotograma a fotograma amb la posició predita pel moviment (tolera canvis d'id i forats de fins a 3 fotogrames)
    const camina = dir => {
      const res = [];
      let r = r0, ms = nowcMs(clau);
      for (let n = 0; n < 80; n++){
        let trobat = null;
        for (let k = 1; k <= 3 && !trobat; k++){
          const fr = D.frames[nowcClau(ms + dir * k * pas)];
          if (!fr) continue;
          const v = r[3] || 0, th = (r[4] || 0) * Math.PI / 180;
          const py = r[1] + dir * k * (v * Math.cos(th) * h) / 111.2, px = r[2] + dir * k * (v * Math.sin(th) * h) / (111.2 * Math.cos(r[1] * Math.PI / 180));
          let best = null, bs = 0.1 + 0.02 * k;
          fr.forEach(q => { const d = Math.hypot(q[1] - py, q[2] - px) - (q[0] === r[0] ? 0.03 : 0); if (d < bs){ bs = d; best = q; } });
          if (best) trobat = { q: best, ms: ms + dir * k * pas };
        }
        if (!trobat) break;
        res.push(trobat); r = trobat.q; ms = trobat.ms;
      }
      return res;
    };
    const cadena = [{ q: r0, ms: nowcMs(clau) }].concat(camina(-1), camina(+1)).filter(p => p.q[5] !== undefined).sort((x, y) => x.ms - y.ms);
    // alternativa: tota la pista amb el mateix id (és la que dibuixa el rastre); es tria la que cobreix més temps
    const perId = [];
    Object.keys(D.frames).sort().forEach(k => { const q = D.frames[k].find(z => z[0] === r0[0]); if (q && q[5] !== undefined) perId.push({ q, ms: nowcMs(k) }); });
    const span = a => a.length ? a[a.length - 1].ms - a[0].ms : 0;
    const punts = span(perId) > span(cadena) ? perId : cadena;
    let acum = 0, prev = null;
    const S = punts.map(p => { acum += p.q[5] * (prev === null ? pas : p.ms - prev) / 3600000; prev = p.ms; return { ms: p.ms, mmh: p.q[5], acum: Math.round(acum * 10) / 10 }; });
    return S.length >= 2 ? S : null;
  }
  function nowcSerie(c, clau){
    const h = nowc.hist; if (!h || !h.fotogrames) return [];
    const pas = (h.pas_min || 10) * 60000, ms0 = nowcMs(clau);
    const cols = Object.fromEntries(h.columnes.map((n, i) => [n, i]));
    const obj = f => Object.fromEntries(h.columnes.map((n, i) => [n, f[i]]));
    const cen = r => [(r.s + r.n) / 2, (r.w + r.e) / 2];
    const veina = (r, ms, dir) => {
      const [cy, cx] = cen(r);
      for (let k = 1; k <= 3; k++){
        const fr = h.fotogrames[nowcClau(ms + dir * k * pas)];
        if (!fr) continue;
        let best = null, bs = 1e9;
        fr.forEach(f => {
          const q = obj(f), d = Math.hypot(cen(q)[0] - cy, cen(q)[1] - cx);
          if (d > 0.15) return;
          // la durada d'aturada no és estrictament monòtona (fusions, recàlculs): només desempata
          const sc = d + Math.abs((q.enganxada_min - r.enganxada_min) * dir - 10 * k) * 0.001;
          if (sc < bs){ bs = sc; best = q; }
        });
        if (best) return { r: best, ms: ms + dir * k * pas };
      }
      return null;
    };
    const pt = (r, ms) => ({ ms, mmh: r.mm_h_ara, acum: r.mm_mitjana });
    const cap = [pt(c, ms0)];
    for (let r = c, ms = ms0, n = 0; n < 60; n++){ const v = veina(r, ms, -1); if (!v || v.ms < ms0 - (c.enganxada_min + 20) * 60000) break; cap.unshift(pt(v.r, v.ms)); r = v.r; ms = v.ms; }
    for (let r = c, ms = ms0, n = 0; n < 60; n++){ const v = veina(r, ms, +1); if (!v) break; cap.push(pt(v.r, v.ms)); r = v.r; ms = v.ms; }
    return cap;
  }
  function nowcGraf(c, clau){
    const S = nowcSeriePista(c, clau) || nowcSerie(c, clau), ms0 = nowcMs(clau);
    if (S.length < 2) return '<div style="margin-top:8px;font-size:11px;opacity:.7;">Encara no hi ha prou historial per dibuixar l\'evolució.</div>';
    const W = 300, H = 150, L_ = 30, R_ = 32, T_ = 10, B_ = 22, pw = W - L_ - R_, ph = H - T_ - B_;
    const nice = v => { const e = Math.pow(10, Math.floor(Math.log10(v || 1))), m = v / e; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * e; };
    const maxI = nice(Math.max(1, ...S.map(p => p.mmh)) * 1.05), maxA = nice(Math.max(1, ...S.map(p => p.acum)) * 1.05);
    const t0 = S[0].ms, t1 = S[S.length - 1].ms, dt = Math.max(1, t1 - t0);
    const X = ms => L_ + (ms - t0) / dt * pw, YI = v => T_ + ph - v / maxI * ph, YA = v => T_ + ph - v / maxA * ph;
    const bw = Math.max(2, Math.min(12, pw / (S.length) * 0.7));
    const fmt = v => (v >= 10 || Number.isInteger(v)) ? String(Math.round(v)) : v.toFixed(1);
    let g = '';
    for (let i = 0; i <= 4; i++){
      const y = T_ + ph - i / 4 * ph;
      g += `<line x1="${L_}" x2="${L_ + pw}" y1="${y}" y2="${y}" stroke="#e3e7eb" stroke-width="1"/>` +
        `<text x="${L_ - 4}" y="${y + 3}" text-anchor="end" font-size="9" fill="#52606d">${fmt(maxI * i / 4)}</text>` +
        `<text x="${L_ + pw + 4}" y="${y + 3}" font-size="9" fill="#7b8794">${fmt(maxA * i / 4)}</text>`;
    }
    const barres = S.map(p => `<rect x="${(X(p.ms) - bw / 2).toFixed(1)}" y="${YA(p.acum).toFixed(1)}" width="${bw.toFixed(1)}" height="${(T_ + ph - YA(p.acum)).toFixed(1)}" fill="#b8c4d0"/>`).join('');
    const linia = S.map((p, i) => `${i ? 'L' : 'M'}${X(p.ms).toFixed(1)},${YI(p.mmh).toFixed(1)}`).join(' ');
    const punts = S.map(p => `<circle cx="${X(p.ms).toFixed(1)}" cy="${YI(p.mmh).toFixed(1)}" r="2" fill="#fff" stroke="#1f2933" stroke-width="1.2"/>`).join('');
    const tick = n => Math.min(n, S.length);
    let eixX = '';
    const nt = Math.min(4, S.length - 1);
    for (let i = 0; i <= nt; i++){
      const ms = t0 + dt * i / nt;
      eixX += `<text x="${X(ms).toFixed(1)}" y="${H - 8}" text-anchor="${i === 0 ? 'start' : i === nt ? 'end' : 'middle'}" font-size="9" fill="#52606d">${nowcHoraLocal(Math.round(ms / 600000) * 600000)}</text>`;
    }
    const ara = (ms0 >= t0 && ms0 <= t1) ? `<line x1="${X(ms0).toFixed(1)}" x2="${X(ms0).toFixed(1)}" y1="${T_}" y2="${T_ + ph}" stroke="#C8102E" stroke-width="1" stroke-dasharray="3 3"/>` : '';
    const hit = S.map(p => `<rect x="${(X(p.ms) - pw / S.length / 2).toFixed(1)}" y="${T_}" width="${(pw / S.length).toFixed(1)}" height="${ph}" fill="transparent"><title>${nowcHoraLocal(p.ms)} · ${p.mmh} mm/h · ${p.acum} mm acumulats</title></rect>`).join('');
    return `<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--panel-border);">` +
      `<div style="display:flex;justify-content:space-between;font-size:10px;color:#52606d;margin-bottom:2px;"><span>mm/h</span><span>mm acumulats</span></div>` +
      `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;max-width:${W}px;font-family:inherit;">${g}${barres}<path d="${linia}" fill="none" stroke="#1f2933" stroke-width="1.6" stroke-linejoin="round"/>${punts}${ara}` +
      `<line x1="${L_}" x2="${L_ + pw}" y1="${T_ + ph}" y2="${T_ + ph}" stroke="#9aa5b1"/>${eixX}${hit}</svg>` +
      `<div style="display:flex;gap:12px;font-size:10px;color:#52606d;margin-top:2px;"><span><span style="display:inline-block;width:14px;height:2px;background:#1f2933;vertical-align:middle"></span> Intensitat</span>` +
      `<span><span style="display:inline-block;width:9px;height:9px;background:#b8c4d0;vertical-align:middle"></span> Acumulació</span>` +
      (ara ? `<span><span style="display:inline-block;width:14px;border-top:1px dashed #C8102E;vertical-align:middle"></span> Ara</span>` : '') + `</div></div>`;
  }
  // Adjunta a cada cel·la el moviment de la pista més propera del mateix fotograma
  function nowcAdjuntaMov(cels, clau){
    const fr = nowc.mov && nowc.mov.frames && nowc.mov.frames[clau];
    if (!fr) return cels;
    cels.forEach(c => {
      const cy = (c.s + c.n) / 2, cx = (c.w + c.e) / 2;
      let best = null, bd = 1e9;
      fr.forEach(r => { const d = Math.hypot(r[1] - cy, r[2] - cx); if (d < bd){ bd = d; best = r; } });
      if (best && bd < 0.1) c.mov = { vel: best[3], rumb: best[4], id: best[0] };
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
      div.innerHTML = `<div class="nowc-cap"><span>Capes</span><span class="nowc-fl">▾</span></div><div class="nowc-body">
        <select id="capa-sel" style="display:none;">
          <option value="echo">Echotops (Meteocat)</option>
          <option value="refl">Reflectivitat radar (AEMET)</option>
          <option value="sat">Satèl·lit IR 10,5 µm (MTG)</option>
          <option value="echo+sat">Echotops + satèl·lit</option>
          <option value="refl+sat">Reflectivitat + satèl·lit</option>
        </select>
        <div id="refl-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <div id="mod-ctl" style="display:none;margin-top:4px;">
          <div id="mod-info" style="font-size:11px;line-height:1.4;"></div>
          <div style="display:flex;align-items:center;gap:4px;margin-top:4px;">
            <button type="button" id="mod-prev" title="Hora anterior" style="padding:2px 8px;">◀</button>
            <input type="range" id="mod-t" min="1" max="48" step="1" style="flex:1;margin:0;min-width:0;" title="Hora de la previsió">
            <button type="button" id="mod-next" title="Hora següent" style="padding:2px 8px;">▶</button>
          </div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11px;">
            <span id="mod-acum-row" style="display:none;align-items:center;gap:4px;">Acumulat
              <select id="mod-acum"><option value="0">des de l'inici</option><option value="3">3 h</option><option value="6">6 h</option><option value="12">12 h</option><option value="24">24 h</option></select></span>
            <button type="button" id="mod-ara" style="margin-left:auto;padding:2px 8px;">Ara</button>
          </div>
        </div>
        <div id="sat-ctl" style="display:none;margin-top:4px;">
          <div style="display:flex;align-items:center;gap:6px;font-size:11px;opacity:.85;"><span>Opacitat satèl·lit</span>
            <input type="range" id="sat-op" min="20" max="100" step="5" style="flex:1;margin:0;min-width:0;" title="Opacitat del satèl·lit"></div>
          <div id="sat-info" style="margin-top:2px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        </div>
        <div class="nowc-sec" style="margin-top:10px;border-top:1px solid var(--panel-border);padding-top:8px;">Superposicions</div>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:3px;">
          <input type="checkbox" id="nowc-toggle" checked style="margin-top:2px"> <span><b>Tempestes enganxades</b> (radar AEMET)</span>
        </label>
        <div id="nowc-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:6px;">
          <input type="checkbox" id="mov-toggle" style="margin-top:2px"> <span>Moviment (rastre i velocitat)</span>
        </label>
        <div id="mov-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:flex-start;cursor:pointer;margin-top:6px;">
          <input type="checkbox" id="aca-toggle" checked style="margin-top:2px"> <span>Pluviòmetres ACA</span>
        </label>
        <div id="aca-info" style="margin-top:4px;font-size:11px;line-height:1.4;opacity:.9;"></div>
        <label style="display:flex;gap:6px;align-items:center;cursor:pointer;margin-top:6px;">
          <input type="checkbox" id="nowc-so"> <span>So d'avís</span>
          <a href="#" id="nowc-prova" style="margin-left:auto;font-size:11px;">prova</a>
        </label></div>`;
      const cap = div.querySelector('.nowc-cap');
      const fl = div.querySelector('.nowc-fl');
      const plega = c => { div.classList.toggle('col', c); fl.textContent = c ? '▴' : '▾'; nowcAjustaMobil(); };
      cap.addEventListener('click', () => plega(!div.classList.contains('col')));
      if (window.matchMedia('(max-width:640px)').matches) plega(true);
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelector('#nowc-toggle').addEventListener('change', e => nowcActiva(e.target.checked));
      const cs = div.querySelector('#capa-sel'), so_ = div.querySelector('#sat-op');
      try{ const m = localStorage.getItem(NOWC_LS_CAPA); if (m && CAPA_MODES[m]) refl.mode = m; else if (m && m.indexOf('mod:') === 0) mod.pendent = m; }catch(_){}
      try{ const o = +(JSON.parse(localStorage.getItem(NOWC_LS_SAT) || '{}').op); if (o >= 20 && o <= 100) sat.op = o; }catch(_){}
      cs.value = refl.mode; so_.value = sat.op;
      const capaAplica = () => { [refl.actiu, sat.actiu] = capaM(refl.mode) || [false, false]; };
      mod.cs = cs; mod.aplica = capaAplica;
      capaAplica();
      cs.addEventListener('change', e => {
        refl.mode = e.target.value; capaAplica();
        try{ localStorage.setItem(NOWC_LS_CAPA, refl.mode); }catch(_){}
        reflMostra(); satMostra(); modMostra();
      });
      so_.addEventListener('input', e => { sat.op = +e.target.value; try{ localStorage.setItem(NOWC_LS_SAT, JSON.stringify({ op: sat.op })); }catch(_){} if (sat.capa) sat.capa.setOpacity(sat.op / 100); });
      const mt = div.querySelector('#mov-toggle');
      mt.checked = nowc.movActiu;
      mt.addEventListener('change', e => { nowc.movActiu = e.target.checked; try{ localStorage.setItem(NOWC_LS_MOV, nowc.movActiu ? '1' : '0'); }catch(_){} nowcMovMostra(); });
      const so = div.querySelector('#nowc-so');
      so.checked = nowc.so;
      so.addEventListener('change', e => { nowc.so = e.target.checked; try{ localStorage.setItem(NOWC_LS_SO, nowc.so ? '1' : '0'); }catch(_){} });
      div.querySelector('#nowc-prova').addEventListener('click', e => { e.preventDefault(); const ok = nowcSona(2); if (!ok && !nowc.so) alert('El so està desactivat.'); });
      return div;
    },
  });
  map.addControl(new NowcastControl());

  // ---- Selector de fons: dos botons (Observació / Predicció) a dalt a l'esquerra. El <select id="capa-sel"> (ocult) continua sent la font de veritat ----
  (function(){
    const OBS = [['echo', 'Echotops (Meteocat)'], ['refl', 'Reflectivitat radar (AEMET)'], ['sat', 'Satèl·lit IR 10,5 µm (MTG)'], ['echo+sat', 'Echotops + satèl·lit'], ['refl+sat', 'Reflectivitat + satèl·lit']];
    const st = document.createElement('style');
    st.textContent = `
      #timeline-wrap{ padding:6px 12px 8px !important; }
      #timeline-panel{ display:flex; align-items:center; gap:14px; max-width:660px !important; padding:5px 12px !important; }
      #timeline-readout{ margin:0 !important; gap:12px; flex:0 0 auto; }
      #timeline-readout .ts{ font-size:14px !important; white-space:nowrap; }
      #timeline-readout .ts .date{ font-size:11px !important; margin-right:5px !important; }
      #playbtn{ font-size:11px !important; padding:3px 9px !important; white-space:nowrap; }
      #scrubber{ flex:1 1 auto; min-width:0; height:18px !important; }
      #scrubber::-webkit-slider-thumb{ width:13px !important; height:13px !important; margin-top:-5px !important; }
      @media (max-width:640px){ #timeline-panel{ flex-wrap:wrap; gap:2px 10px; } #scrubber{ flex:1 0 100%; } }
      .fons-ctl{ background:var(--panel,#fff); border:1px solid var(--panel-border,#ccc); border-radius:3px; box-shadow:0 1px 5px rgba(0,0,0,.25);
        font:15px/1.3 var(--font-ui, sans-serif); color:var(--text,#222); position:fixed; left:10px; top:70px; z-index:1100; }
      .fons-ctl .fons-tabs{ display:flex; }
      .fons-ctl .fons-tab{ flex:1; padding:11px 22px; border:0; background:transparent; color:inherit; font:inherit; font-size:14px; font-weight:700; cursor:pointer; white-space:nowrap; }
      .fons-ctl .fons-tab + .fons-tab{ border-left:1px solid var(--panel-border,#ccc); }
      .fons-ctl .fons-tab:hover{ color:#C8102E; }
      .fons-ctl .fons-tab.act{ color:#C8102E; box-shadow:inset 0 -2px 0 #C8102E; }
      .fons-ctl .fons-tab[disabled]{ opacity:.45; cursor:default; color:inherit; }
      .fons-ctl .fons-llista{ display:none; border-top:1px solid var(--panel-border,#ccc); padding:6px 0; min-width:270px; }
      .fons-ctl .fons-llista.obert{ display:block; }
      .fons-ctl .fons-it{ display:flex; gap:10px; align-items:center; padding:7px 16px; cursor:pointer; font-size:12px; font-weight:400; }
      .fons-ctl .fons-it:hover{ background:rgba(200,16,46,.07); }
      .fons-ctl .fons-it .pt{ width:8px; height:8px; border-radius:50%; border:1px solid #888; flex:none; }
      .fons-ctl .fons-it.sel .pt{ background:#C8102E; border-color:#C8102E; }
      .fons-ctl .fons-it.sel{ font-weight:400; }
      .fons-ctl .fons-sep{ padding:8px 16px 3px; font-size:12px; font-weight:700; color:var(--text,#222); }
      .fons-ctl .fons-sep + .fons-it, .fons-ctl .fons-it + .fons-sep{ }
      .fons-ctl .fons-sep:not(:first-child){ border-top:1px solid var(--panel-border,#ddd); margin-top:4px; padding-top:10px; }`;
    document.head.appendChild(st);
    const cs = document.getElementById('capa-sel');
    const d = document.createElement('div');
    d.className = 'fons-ctl';
    d.innerHTML = '<div class="fons-tabs"><button type="button" class="fons-tab" data-t="obs" aria-expanded="false">Observació</button>' +
      '<button type="button" class="fons-tab" data-t="pre" aria-expanded="false">Predicció</button></div><div class="fons-llista"></div>';
    document.body.appendChild(d);
    L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
    const posa = () => { const tb = document.getElementById('topbar'); d.style.top = ((tb ? tb.getBoundingClientRect().bottom : 0) + 10) + 'px'; };   // sota la capçalera
    posa(); window.addEventListener('resize', posa); window.addEventListener('orientationchange', posa); setTimeout(posa, 500);
    const ll = d.querySelector('.fons-llista'), tabs = [...d.querySelectorAll('.fons-tab')];
    let obert = null;
    const llistaPre = () => {
      const out = [];
      Object.keys(mod.models || {}).forEach(k => { const M = mod.models[k];
        out.push(['sep', M.nom]); out.push([`mod:${k}:h`, 'Pluja horària']); out.push([`mod:${k}:a`, 'Pluja acumulada']); });
      return out;
    };
    const pinta = t => {
      const items = t === 'obs' ? OBS : llistaPre(), cur = refl.mode;
      ll.innerHTML = items.map(([v, n]) => v === 'sep' ? `<div class="fons-sep">${n}</div>` : `<div class="fons-it${v === cur ? ' sel' : ''}" data-v="${v}"><span class="pt"></span><span>${n}</span></div>`).join('');
    };
    const sync = () => {
      const esPre = String(refl.mode).indexOf('mod:') === 0, hiHaModels = Object.keys(mod.models || {}).length > 0;
      tabs.forEach(b => { const pre = b.dataset.t === 'pre'; b.classList.toggle('act', pre === esPre); b.disabled = pre && !hiHaModels; b.title = (pre && !hiHaModels) ? 'Previsió no disponible' : ''; });
      if (obert) pinta(obert);
    };
    const tanca = () => { obert = null; ll.classList.remove('obert'); tabs.forEach(b => b.setAttribute('aria-expanded', 'false')); };
    tabs.forEach(b => b.addEventListener('click', () => {
      if (b.disabled) return;
      if (obert === b.dataset.t){ tanca(); return; }
      obert = b.dataset.t; pinta(obert); ll.classList.add('obert');
      tabs.forEach(x => x.setAttribute('aria-expanded', String(x === b)));
    }));
    ll.addEventListener('click', e => {
      const it = e.target.closest('.fons-it'); if (!it) return;
      const v = it.dataset.v;
      if (cs.querySelector(`option[value="${v}"]`)){ cs.value = v; cs.dispatchEvent(new Event('change')); }
      sync(); tanca();
    });
    document.addEventListener('click', e => { if (obert && !d.contains(e.target)) tanca(); });
    cs.addEventListener('change', sync);
    window.fonsSync = sync;
    sync();
  })();

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
    satMostra();
    if (ts) modSegueix(ts);
    modMostra();
    if (ts && window.acaMostra) window.acaMostra(ts);
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
          const mk = L.marker(pts[q], { interactive: false, keyboard: false, icon: L.divIcon({ className: 'nowc-tk', iconSize: [0, 0],
            html: `<span class="nowc-tk-t">−${min % 60 === 0 ? (min / 60) + ' h' : min + '′'}</span>` }) });
          mk._exp = { t: 'tk', txt: `−${min % 60 === 0 ? (min / 60) + ' h' : min + '′'}` }; mk.addTo(nowc.movCapa);
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
      m._exp = { t: 'mv', col, mou, rumb, pill: vel === null ? '' : (vel < 8 ? 'quasi quieta' : vel + ' km/h') };
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

  // ---- Satèl·lit MTG FCI IR 10,5 µm (EUMETView WMS, sense clau ni cost) ----
  // El servei només parla EPSG:4326: cada tessel·la (512 px) es demana amb la seva caixa lat/lon. L'instant segueix l'scrubber.
  const SAT = {
    url: 'https://view.eumetsat.int/geoserver/ows',
    capa: 'mtg_fd:ir105_hrfi',
    estil: 'mtg_fd:mtg_fd_ir105_hrfi_style_01',      // "SLD MTG HRFI IR 10.5 Style - 01"
  };
  const SatWMS = L.TileLayer.extend({
    getTileUrl: function(coords){
      const b = this._tileCoordsToBounds(coords);
      const bbox = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map(x => x.toFixed(5)).join(',');   // WMS 1.3.0 + EPSG:4326: lat,lon
      const o = this.options;
      return `${SAT.url}?service=WMS&request=GetMap&version=1.3.0&layers=${encodeURIComponent(SAT.capa)}&styles=${encodeURIComponent(SAT.estil)}` +
        `&format=image/png&transparent=true&crs=EPSG:4326&bbox=${bbox}&width=512&height=512&time=${o.time}`;
    },
  });
  const satTime = ms => { const d = new Date(Math.floor(ms / 600000) * 600000); return d.toISOString().slice(0, 19) + 'Z'; };
  function satMostra(){
    const ctl = document.getElementById('sat-ctl'), info = document.getElementById('sat-info');
    if (!ctl) return;
    ctl.style.display = sat.actiu ? 'block' : 'none';
    if (!sat.actiu){ if (sat.capa){ map.removeLayer(sat.capa); sat.capa = null; sat.time = null; } return; }
    if (!map.getPane('sat')){ map.createPane('sat'); const p = map.getPane('sat'); p.style.zIndex = 250; p.style.pointerEvents = 'none'; }
    const ref = nowc.ts ? nowcMs(nowc.ts.replace('_', '')) : Date.now() - 30 * 60000;
    const t = satTime(ref);
    if (!sat.capa){
      sat.errs = 0;
      sat.capa = new SatWMS('', { pane: 'sat', tileSize: 512, zoomOffset: -1, opacity: sat.op / 100, time: t, updateWhenIdle: true, keepBuffer: 1, maxNativeZoom: 12 });
      sat.capa.on('tileerror', () => { if (++sat.errs === 3 && info) info.innerHTML = '<b style="color:#C8102E">No s\'han pogut carregar les imatges de satèl·lit</b>'; });
      sat.capa.on('tileload', () => { sat.errs = 0; });
      sat.capa.addTo(map);
      sat.time = t;
    }else if (t !== sat.time){
      sat.time = t; sat.capa.options.time = t; sat.capa.redraw();
    }
    if (info && sat.errs < 3) info.textContent = `MTG de les ${nowcHoraLocal(Date.parse(t))} · una imatge cada 10 min · © EUMETSAT`;
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
        L.popup({ maxWidth: 320, minWidth: Math.min(300, window.innerWidth - 60) }).setLatLng(centre).setContent(nowcHtml(c, hora(clau), esUltim) + nowcGraf(c, clau)).openOn(map);
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

  // ---- Llegenda compartida: el mateix quadre (posició i lectura al passar el ratolí) que echotops ----
    const LX_SAT_LEG = () => `${SAT.url}?service=WMS&request=GetLegendGraphic&version=1.3.0&format=image/png&layer=${encodeURIComponent(SAT.capa)}&style=${encodeURIComponent(SAT.estil)}`;
  const LX_TXT0 = 'Passa el cursor pel mapa';
  function legendaMode(){ return mod.sel ? 'mod' : (refl.actiu ? 'refl' : (refl.mode === 'sat' ? 'sat' : 'echo')); }
  function legendaX(){
    const lg = document.getElementById('legend'); if (!lg) return;
    let x = document.getElementById('legend-x');
    if (!x){
      const st = document.createElement('style');
      st.textContent = '#legend.nx > *:not(#legend-x){ display:none !important; }';
      document.head.appendChild(st);
      lg.insertAdjacentHTML('afterbegin', '<div id="legend-x" style="display:none"><div class="title" id="lx-title"></div><div id="lx-body"></div>' +
        '<div id="lx-hover" style="margin-top:10px;padding-top:8px;border-top:1px solid var(--panel-border);color:var(--text);font-weight:500;font-size:12px;">' + LX_TXT0 + '</div>' +
        '<div id="lx-credit" style="margin-top:8px;font-size:10px;color:var(--text-dim);"></div></div>');
      x = document.getElementById('legend-x');
    }
    const m = legendaMode();
    lg.classList.toggle('nx', m !== 'echo');
    x.style.display = m === 'echo' ? 'none' : 'block';
    const clauL = m + (m === 'mod' ? ':' + mod.sel : '');
    if (clauL === x.dataset.mode) return;
    x.dataset.mode = clauL;
    const t = document.getElementById('lx-title'), b = document.getElementById('lx-body'), c = document.getElementById('lx-credit'), h = document.getElementById('lx-hover');
    if (h){ h.textContent = LX_TXT0; h.style.display = (m === 'refl' || m === 'mod') ? '' : 'none'; }
    lg.style.width = '';
    if (m === 'mod'){
      const P = modPaleta(), M = mod.models[modK()] || {};
      t.innerHTML = (M.nom || 'Model') + (mod.sel.endsWith(':h') ? ' · pluja horària <span style="text-transform:none">(mm/h)</span>' : ' · pluja acumulada <span style="text-transform:none">(mm)</span>');
      lg.style.width = '360px';
      const nb = P.length + 1, lab = (par) => '<div class="band-labels" style="height:12px;margin:0">' + P.map(([v], i) => i % 2 === par ? `<span style="left:${((i + 1) / nb * 100).toFixed(2)}%">${v}</span>` : '').join('') + '</div>';
      b.innerHTML = lab(0) + '<div class="bands" style="margin:1px 0;box-shadow:0 0 0 1px rgba(0,0,0,.25)">' + [MOD_ZERO].concat(P.map(q => q[1])).map(col => `<span style="background:${col}"></span>`).join('') + '</div>' + lab(1);
      c.textContent = 'Model: ' + (M.nom || '') + (M.model === 'arome' ? ' (Météo-France)' : ' (SMC)');
      if (h) h.style.display = '';
    }else if (m === 'refl'){
      t.textContent = 'Reflectivitat radar (dBZ)';
      b.innerHTML = '<div class="bands">' + REFL_LLEGENDA.map(([col, v]) => `<span style="background:${col}" title="≥ ${v} dBZ"></span>`).join('') + '</div>' +
        '<div class="band-labels">' + REFL_LLEGENDA.map(([col, v], i) => (i % 2 === 0) ? `<span style="left:${((i + 0.5) / REFL_LLEGENDA.length * 100).toFixed(2)}%">${v}${i === REFL_LLEGENDA.length - 1 ? '+' : ''}</span>` : '').join('') + '</div>';
      c.textContent = 'Dades: AEMET';
    }else if (m === 'sat'){
      t.textContent = 'Satèl·lit IR 10,5 µm';
      b.innerHTML = '<img alt="" style="display:block;max-width:100%;" src="' + LX_SAT_LEG() + '" onerror="this.outerHTML=\'<span style=&quot;font-size:10px&quot;>Llegenda no disponible</span>\'">';
      c.textContent = '© EUMETSAT · MTG FCI';
    }
  }
  function reflPix(clau, bounds){
    refl.px = null; refl.clau = clau; refl.bnd = bounds;
    const im = new Image();
    im.onload = () => {
      if (refl.clau !== clau) return;
      const c = document.createElement('canvas'); c.width = im.width; c.height = im.height;
      const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(im, 0, 0);
      refl.px = { g, w: im.width, h: im.height };
    };
    im.src = `data/nowcast/refl/${clau}.png`;
  }
  function reflValor(ll){
    if (!refl.px || !refl.bnd) return 'Sense dades de valor per aquest frame';
    const [[s, w], [n, e]] = refl.bnd;
    if (ll.lat < s || ll.lat > n || ll.lng < w || ll.lng > e) return "Fora de l'àrea de radar";
    const x = Math.min(refl.px.w - 1, Math.max(0, Math.floor((ll.lng - w) / (e - w) * refl.px.w)));
    const y = Math.min(refl.px.h - 1, Math.max(0, Math.floor((n - ll.lat) / (n - s) * refl.px.h)));
    const d = refl.px.g.getImageData(x, y, 1, 1).data;
    if (d[3] === 0) return 'Sense eco a aquest punt';
    let k = 0, best = 1e9;
    REFL_LLEGENDA.forEach(([col], i) => { const q = col.match(/\d+/g).map(Number); const dd = (q[0] - d[0]) ** 2 + (q[1] - d[1]) ** 2 + (q[2] - d[2]) ** 2; if (dd < best){ best = dd; k = i; } });
    const lo = +REFL_LLEGENDA[k][1];
    return k === REFL_LLEGENDA.length - 1 ? `Reflectivitat: ≥ ${lo} dBZ` : `Reflectivitat: ${lo}–${lo + 5} dBZ`;
  }
  map.on('mousemove', e => {
    const lm = legendaMode(); if (lm !== 'refl' && lm !== 'mod') return;
    const el = document.getElementById('lx-hover'); if (el) el.textContent = lm === 'mod' ? modValor(e.latlng) : reflValor(e.latlng);
  });
  map.on('mouseout', () => { const el = document.getElementById('lx-hover'); if (el) el.textContent = LX_TXT0; });
  function reflExcl(){
    const on = !!refl.overlay || refl.mode === 'sat' || mod.sel;
    if (typeof currentOverlay !== 'undefined' && currentOverlay) currentOverlay.setOpacity(on ? 0 : 0.85);
    legendaX();
  }
  function reflMostra(){
    if (refl.overlay){ map.removeLayer(refl.overlay); refl.overlay = null; }
    refl.px = null;
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
    info.innerHTML = `Radar de les ${hora}`;
    const ov = L.imageOverlay(`data/nowcast/refl/${clau}.png`, u.bounds, { opacity: 0.75, interactive: false });
    ov.on('error', () => { if (refl.overlay === ov){ map.removeLayer(ov); refl.overlay = null; reflExcl(); info.innerHTML = `Falta la imatge del radar de les ${hora}`; } });
    refl.overlay = ov.addTo(map);
    reflPix(clau, u.bounds);
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

  // ---- Previsió: pluja horària i acumulada dels models (WRF-SMC, AROME) a partir de data/models/<model>/ ----
  // precip_h.png és un sprite amb un pas horari per tile; cada píxel codifica la pluja horària en 16 bits (R alt, G baix; 65535 = sense dada).
  // L'acumulat (des de l'inici o en finestres de 3-24 h) se suma aquí, sobre els passos horaris.
  // Paletes i llindars calcats de l'escala de Meteologix (Precipitation 1h / Accumulated total precipitation). Per sota del primer llindar: sense color (gris clar a la llegenda).
  const MOD_PAL_H = [[0.1, 'rgb(180,215,255)'], [0.2, 'rgb(117,186,255)'], [0.5, 'rgb(53,154,255)'], [1, 'rgb(4,130,255)'], [2, 'rgb(0,105,210)'], [3, 'rgb(0,54,127)'], [4, 'rgb(20,143,27)'], [5, 'rgb(26,207,5)'], [6, 'rgb(99,237,7)'], [7, 'rgb(255,244,43)'], [8, 'rgb(232,220,0)'], [9, 'rgb(240,96,0)'], [10, 'rgb(255,127,39)'], [12, 'rgb(255,166,106)'], [14, 'rgb(248,78,120)'], [16, 'rgb(247,30,84)'], [20, 'rgb(191,0,0)'], [24, 'rgb(136,0,0)'], [30, 'rgb(100,0,127)'], [40, 'rgb(194,0,251)'], [50, 'rgb(221,102,255)'], [60, 'rgb(235,166,255)'], [80, 'rgb(249,230,255)'], [100, 'rgb(212,212,212)'], [125, 'rgb(150,150,150)']];
  const MOD_PAL_A = [[0.1, 'rgb(222,222,242)'], [1, 'rgb(180,215,255)'], [2, 'rgb(117,186,255)'], [3, 'rgb(53,154,255)'], [5, 'rgb(4,130,255)'], [7, 'rgb(0,105,210)'], [10, 'rgb(0,54,127)'], [15, 'rgb(20,143,27)'], [20, 'rgb(26,207,5)'], [25, 'rgb(99,237,7)'], [30, 'rgb(255,244,43)'], [40, 'rgb(232,220,0)'], [50, 'rgb(240,96,0)'], [60, 'rgb(255,127,39)'], [70, 'rgb(255,166,106)'], [80, 'rgb(248,78,120)'], [90, 'rgb(247,30,84)'], [100, 'rgb(191,0,0)'], [125, 'rgb(136,0,0)'], [150, 'rgb(100,0,127)'], [175, 'rgb(194,0,251)'], [200, 'rgb(221,102,255)'], [250, 'rgb(235,166,255)'], [300, 'rgb(249,230,255)'], [400, 'rgb(212,212,212)'], [500, 'rgb(150,150,150)']];
  const MOD_ZERO = 'rgb(240,240,240)';
  const modK = () => mod.sel ? mod.sel.split(':')[1] : null;
  const modPaleta = () => (mod.sel && mod.sel.endsWith(':h')) ? MOD_PAL_H : MOD_PAL_A;
  const modMs = M => Date.parse(M.run_utc);
  const modMercY = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  const modData = ms => new Intl.DateTimeFormat('ca-ES', { timeZone: 'Europe/Madrid', weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(ms));

  async function modRefresca(){
    try{
      const q = `?_=${Date.now()}`;
      const idx = await fetch(`data/models/index.json${q}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
      const nous = {};
      for (const e of idx.models){
        try{ const m = await fetch(`data/models/${e.model}/meta.json${q}`).then(r => r.json()); nous[e.model] = m; }catch(_){}
      }
      mod.models = nous;
    }catch(_){ mod.models = {}; }
    const cs = mod.cs; if (!cs) return;
    let og = cs.querySelector('optgroup[data-mod]');
    if (og) og.remove();
    const claus = Object.keys(mod.models);
    if (claus.length){
      og = document.createElement('optgroup'); og.label = 'Previsió (models)'; og.setAttribute('data-mod', '1');
      claus.forEach(k => { const M = mod.models[k];
        [['h', 'pluja horària'], ['a', 'pluja acumulada']].forEach(([t, nom]) => { const o = document.createElement('option'); o.value = `mod:${k}:${t}`; o.textContent = `${M.nom} · ${nom}`; og.appendChild(o); }); });
      cs.appendChild(og);
    }
    if (mod.pendent){
      const p = mod.pendent; mod.pendent = null;
      if (cs.querySelector(`option[value="${p}"]`)){ refl.mode = p; cs.value = p; mod.aplica(); reflMostra(); satMostra(); modMostra(); if (window.fonsSync) window.fonsSync(); return; }
    }
    if (mod.sel && !(modK() in mod.models)){ refl.mode = 'echo'; cs.value = 'echo'; mod.aplica(); reflMostra(); satMostra(); }
    modMostra();
    if (window.fonsSync) window.fonsSync();
  }

  async function modCarrega(k){
    const M = mod.models[k];
    const clau = k + '@' + M.run_utc;
    if (mod.cache[clau]) return mod.cache[clau];
    const im = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = `data/models/${k}/${M.fitxer}?v=${encodeURIComponent(M.run_utc)}`; });
    const cv = document.createElement('canvas'); cv.width = im.width; cv.height = im.height;
    const g = cv.getContext('2d', { willReadFrequently: true }); g.drawImage(im, 0, 0);
    const D = g.getImageData(0, 0, im.width, im.height).data;
    const W = M.w, H = M.h, passos = [];
    const pas = s => {                                         // Uint16Array (W*H) del pas s
      if (passos[s]) return passos[s];
      const a = new Uint16Array(W * H), c0 = (s % M.cols) * W, r0 = Math.floor(s / M.cols) * H;
      for (let y = 0; y < H; y++){ let o = ((r0 + y) * im.width + c0) * 4; for (let x = 0; x < W; x++, o += 4) a[y * W + x] = (D[o] << 8) | D[o + 1]; }
      return (passos[s] = a);
    };
    for (const kk of Object.keys(mod.cache)) if (kk.split('@')[0] === k) delete mod.cache[kk];
    return (mod.cache[clau] = { M, pas, W, H });
  }

  // Camp (Float32Array, NaN = sense dada) del pas s: horari o acumulat a la finestra n (0 = des de l'inici)
  function modCamp(C, s, hor, n){
    const { M, pas, W, H } = C, out = new Float32Array(W * H), a0 = hor ? s : Math.max(1, n ? s - n + 1 : 1);
    const ref = pas(s);
    for (let i = 0; i < out.length; i++) out[i] = ref[i] === M.nodata ? NaN : 0;
    for (let k = a0; k <= s; k++){ const a = pas(k); for (let i = 0; i < out.length; i++) if (!Number.isNaN(out[i])) out[i] += a[i] * M.escala; }
    return out;
  }

  function modSegueix(ts){
    if (!mod.sel) return;
    const M = mod.models[modK()]; if (!M) return;
    const ms = Math.round(nowcMs(ts.replace('_', '')) / 3600000) * 3600000, r0 = modMs(M);
    if (ms >= r0 + 3600000 && ms <= r0 + (M.passos - 1) * 3600000) mod.t = ms;
  }

  async function modMostra(){
    const tok = ++mod.token;
    const ctl = document.getElementById('mod-ctl'), info = document.getElementById('mod-info');
    const sel = refl.mode.indexOf('mod:') === 0 ? refl.mode : null;
    const Mq = sel && mod.models[sel.split(':')[1]];
    const clauR = Mq ? [sel, mod.t, mod.acum, Mq.run_utc].join('|') : null;
    if (clauR && clauR === mod.clau && mod.overlay){ reflExcl(); return; }      // res no ha canviat
    mod.clau = null;
    if (mod.overlay){ map.removeLayer(mod.overlay); mod.overlay = null; }
    mod.cur = null;
    mod.sel = sel;
    reflExcl();
    if (!ctl) return;
    ctl.style.display = sel ? 'block' : 'none';
    if (!sel) return;
    const [, k, tipus] = sel.split(':'), M = mod.models[k];
    if (!M){ info.textContent = 'Model no disponible'; return; }
    const hor = tipus === 'h', r0 = modMs(M), n = M.passos;
    document.getElementById('mod-acum-row').style.display = hor ? 'none' : 'inline-flex';
    const sl = document.getElementById('mod-t'); sl.max = n - 1;
    const ara = Math.round(Date.now() / 3600000) * 3600000;
    if (mod.t === null || mod.t === undefined) mod.t = ara;
    mod.t = Math.min(Math.max(mod.t, r0 + 3600000), r0 + (n - 1) * 3600000);
    const s = Math.round((mod.t - r0) / 3600000);
    sl.value = s;
    const rt = new Date(r0);
    info.innerHTML = `<b>${M.nom}</b> · run ${String(rt.getUTCDate()).padStart(2, '0')}/${String(rt.getUTCMonth() + 1).padStart(2, '0')} ${String(rt.getUTCHours()).padStart(2, '0')} UTC<br>` +
      `Vàlid: <b>${modData(mod.t)}</b> (local) · +${s} h`;
    let C;
    try{ C = await modCarrega(k); }catch(_){ if (tok === mod.token) info.innerHTML += '<br><b style="color:#C8102E">No s\'ha pogut carregar la previsió</b>'; return; }
    if (tok !== mod.token) return;
    const camp = modCamp(C, s, hor, mod.acum), pal = hor ? MOD_PAL_H : MOD_PAL_A;
    // Suavitzat: interpolació bilineal del camp a F× la resolució abans de classificar per colors (isohietes arrodonides en lloc de blocs).
    const F = 4, CW = C.W * F, CH = C.H * F;
    const cv = document.createElement('canvas'); cv.width = CW; cv.height = CH;
    const g = cv.getContext('2d'), im = g.createImageData(CW, CH), cols = pal.map(([v, c]) => [v, ...c.match(/\d+/g).map(Number)]);
    const W = C.W, H = C.H;
    for (let Y = 0; Y < CH; Y++){
      const sy = Math.min(H - 1, Math.max(0, (Y + 0.5) / F - 0.5)), y0 = Math.floor(sy), y1 = Math.min(H - 1, y0 + 1), fy = sy - y0;
      for (let X = 0; X < CW; X++){
        const sx = Math.min(W - 1, Math.max(0, (X + 0.5) / F - 0.5)), x0 = Math.floor(sx), x1 = Math.min(W - 1, x0 + 1), fx = sx - x0;
        const a00 = camp[y0 * W + x0], a10 = camp[y0 * W + x1], a01 = camp[y1 * W + x0], a11 = camp[y1 * W + x1];
        let v;
        if (a00 === a00 && a10 === a10 && a01 === a01 && a11 === a11) v = (a00 * (1 - fx) + a10 * fx) * (1 - fy) + (a01 * (1 - fx) + a11 * fx) * fy;
        else v = camp[(fy < 0.5 ? y0 : y1) * W + (fx < 0.5 ? x0 : x1)];        // vora del domini: veí més proper
        if (!(v >= cols[0][0])) continue;
        let q = 0; while (q + 1 < cols.length && v >= cols[q + 1][0]) q++;
        const o = (Y * CW + X) * 4;
        im.data[o] = cols[q][1]; im.data[o + 1] = cols[q][2]; im.data[o + 2] = cols[q][3]; im.data[o + 3] = 255;
      }
    }
    g.putImageData(im, 0, 0);
    mod.cur = { camp, W: C.W, H: C.H, b: M.bounds, hor, n: mod.acum };
    mod.overlay = L.imageOverlay(cv.toDataURL('image/png'), M.bounds, { opacity: 0.8, interactive: false }).addTo(map);
    mod.overlay.bringToBack();
    mod.clau = [sel, mod.t, mod.acum, M.run_utc].join('|');
    reflExcl();
  }
  function modValor(ll){
    const C = mod.cur; if (!C) return 'Sense dades de valor per aquest instant';
    const [[s, w], [n, e]] = C.b;
    if (ll.lat < s || ll.lat > n || ll.lng < w || ll.lng > e) return 'Fora del domini del model';
    const x = Math.min(C.W - 1, Math.max(0, Math.floor((ll.lng - w) / (e - w) * C.W)));
    const y = Math.min(C.H - 1, Math.max(0, Math.floor((modMercY(n) - modMercY(ll.lat)) / (modMercY(n) - modMercY(s)) * C.H)));
    const v = C.camp[y * C.W + x];
    if (Number.isNaN(v)) return 'Fora del domini del model';
    if (v < 0.05) return 'Sense pluja';
    return C.hor ? `Pluja horària: ${v.toFixed(1)} mm/h` : `Pluja acumulada${C.n ? ' (' + C.n + ' h)' : ''}: ${v.toFixed(1)} mm`;
  }
  (function(){
    const q = id => document.getElementById(id);
    const ini = () => {
      const sl = q('mod-t'); if (!sl) return setTimeout(ini, 200);
      const canvia = s => { const m = mod.models[modK()]; if (!m) return; mod.t = modMs(m) + s * 3600000; modMostra(); };
      sl.addEventListener('input', () => canvia(+sl.value));
      q('mod-prev').addEventListener('click', () => canvia(+sl.value - 1));
      q('mod-next').addEventListener('click', () => canvia(+sl.value + 1));
      q('mod-ara').addEventListener('click', () => { mod.t = Math.round(Date.now() / 3600000) * 3600000; modMostra(); });
      const ac = q('mod-acum');
      try{ const v = localStorage.getItem('nowcast_modacum_v1'); if (v !== null && ac.querySelector(`option[value="${v}"]`)){ ac.value = v; mod.acum = +v; } }catch(_){}
      ac.addEventListener('change', () => { mod.acum = +ac.value; try{ localStorage.setItem('nowcast_modacum_v1', ac.value); }catch(_){} modMostra(); });
    };
    ini();
  })();
  modRefresca();
  setInterval(modRefresca, 15 * 60 * 1000);

  // ---- Contorns i noms a les exportacions (imatge i GIF), no al visor ----
  // Els límits de comarques (WMS de l'ICGC; si no respon, data/comarques.geojson) es dibuixen en blanc per sobre de les capes de dades. Sense noms.
  // Base ICGC neta de noms. Les tessel·les "administratiu" tenen mar = gris clar pla (≈215), terra = gris pla (≈183), línies blanques i text fosc.
  // Es classifica cada píxel; el que no és ni mar ni terra ni línia (text, vores suavitzades) s'omple amb els veïns. Retorna {base, linies} o null.
  const LIM_GRUIX = 0.6, LIM_OPAC = 0.9;       // gruix extra (px a 1500 d'ample) i opacitat de les línies de límits sobre les dades
  async function icgcNet(nw, se, org, Zf, W, H){
    const l = baseLayers.icgc; if (!l) return null;
    try{
      const t = document.createElement('canvas'); t.width = W; t.height = H;
      const g = t.getContext('2d', { willReadFrequently: true });
      const tam = (l.options.tileSize && l.options.tileSize.x) || l.options.tileSize || 256, zt = Math.min(l.options.maxZoom || 18, Math.round(Zf)), sc = Math.pow(2, Zf - zt);
      const r = await expTessel(g, { tam, zt, nw, se, alpha: 1, prog: () => {},
        url: (x, y) => { const tz = l._tileZoom; l._tileZoom = zt; try{ return l.getTileUrl({ x, y, z: zt }); } finally { l._tileZoom = tz; } },
        rect: (x, y) => [x * tam * sc - org.x, y * tam * sc - org.y, tam * sc, tam * sc] });
      if (!r.total || r.fallats > r.total * 0.3) return null;
      const im = g.getImageData(0, 0, W, H), d = im.data, N = W * H;
      let c = new Uint8Array(N), altres = 0;                                  // 1 mar, 2 terra, 3 línia, 0 altres
      for (let i = 0, p = 0; p < N; i += 4, p++){
        const rr = d[i], mx = Math.max(rr, d[i + 1], d[i + 2]), mn = Math.min(rr, d[i + 1], d[i + 2]);
        if (mx - mn <= 6){ if (Math.abs(rr - 215) <= 3) c[p] = 1; else if (Math.abs(rr - 183) <= 3) c[p] = 2; }   // les línies i halos de la tessel·la (≥222) no es classifiquen: s'omplen amb els veïns i les línies es dibuixen des de comarques.geojson
        if (!c[p]) altres++;
      }
      if (altres > N * 0.4) return null;                                      // colors inesperats (p. ex. relleu): no es toca la base
      const q = new Int32Array(N), vist = new Uint8Array(N);
      const elimina = (cl, thr, rad) => {                                     // esborra (→ 0) els components connexos de la classe cl amb menys de thr píxels (rad = 2 pont buits d'1 px)
        vist.fill(0);
        for (let p0 = 0; p0 < N; p0++){
          if (c[p0] !== cl || vist[p0]) continue;
          let h = 0, t = 0; q[t++] = p0; vist[p0] = 1;
          while (h < t){
            const p = q[h++], x = p % W;
            for (let dy = -rad; dy <= rad; dy++) for (let dx = -rad; dx <= rad; dx++){
              if (!dx && !dy) continue;
              const xx = x + dx; if (xx < 0 || xx >= W) continue;
              const pp = p + dy * W + dx; if (pp < 0 || pp >= N || c[pp] !== cl || vist[pp]) continue;
              vist[pp] = 1; q[t++] = pp;
            }
          }
          if (t < thr){ for (let i = 0; i < t; i++) c[q[i]] = 0; altres += t; }
        }
      };
      elimina(1, Math.round(1500 * W / 1500), 1);                                // mar: fora els petits anells que deixa el text suavitzat
      const lin = new Uint8Array(N);                                                  // línies originals (3) abans d'omplir
      {                                                                       // terra fi (≤2 px) = vora suavitzada d'un text sobre el mar: es descarta
        const n = c.slice();
        for (let y = 0, p = 0; y < H; y++) for (let x = 0; x < W; x++, p++){
          if (c[p] !== 2) continue;
          const v = (x > 0 && c[p - 1] === 2) + (x < W - 1 && c[p + 1] === 2) + (y > 0 && c[p - W] === 2) + (y < H - 1 && c[p + W] === 2);
          if (v < 3){ n[p] = 0; altres++; }
        }
        c = n;
      }
      for (let pas = 0; pas < 14 && altres > 0; pas++){                        // omple text i vores amb mar/terra veïns
        const n = c.slice();
        for (let y = 0, p = 0; y < H; y++) for (let x = 0; x < W; x++, p++){
          if (c[p]) continue;
          let m = 0, tr = 0;
          for (const q of [x > 0 ? c[p - 1] : 0, x < W - 1 ? c[p + 1] : 0, y > 0 ? c[p - W] : 0, y < H - 1 ? c[p + W] : 0]){ if (q === 1) m++; else if (q === 2) tr++; }
          if (m || tr){ n[p] = tr >= m ? 2 : 1; altres--; }
        }
        c = n;
      }
      for (let p = 0; p < N; p++) if (!c[p]) c[p] = 2;
      // base: mar, terra i línies originals en blanc
      const bi = g.createImageData(W, H), li = g.createImageData(W, H), b = bi.data, ld = li.data;
      for (let y = 0, p = 0; y < H; y++) for (let x = 0; x < W; x++, p++){
        const i = p * 4, k = c[p], v = (lin[p] === 3 || k === 3) ? 255 : (k === 1 ? 215 : 183);
        b[i] = b[i + 1] = b[i + 2] = v; b[i + 3] = 255;
        const costa = k === 1 && ((x > 0 && c[p - 1] === 2) || (x < W - 1 && c[p + 1] === 2) || (y > 0 && c[p - W] === 2) || (y < H - 1 && c[p + W] === 2));
        if (false && costa){ ld[i] = ld[i + 1] = ld[i + 2] = 255; ld[i + 3] = 255; }
      }
      const cb = document.createElement('canvas'); cb.width = W; cb.height = H; cb.getContext('2d').putImageData(bi, 0, 0);
      const cl = document.createElement('canvas'); cl.width = W; cl.height = H; cl.getContext('2d').putImageData(li, 0, 0);
      return { base: cb, linies: cl };
    }catch(e){ console.warn('base ICGC', e); return null; }
  }
  function limDibuixaNet(ctx, cl, W){
    const gr = Math.max(1, Math.round(LIM_GRUIX * W / 1500)), ds = [[0, 0], [gr, 0], [-gr, 0], [0, gr], [0, -gr], [gr, gr], [-gr, gr], [gr, -gr], [-gr, -gr]];
    ctx.globalAlpha = LIM_OPAC; ds.forEach(([dx, dy]) => ctx.drawImage(cl, dx, dy)); ctx.globalAlpha = 1;
  }
  // Límits de comarques de l'ICGC (WMS, PNG transparent). Es demana una sola imatge per a tota l'àrea exportada, i es pinta de blanc.
  const LIM_WMS = 'https://geoserveis.icgc.cat/servei/catalunya/divisions-administratives/wms';
  const LIM_CAPES = ['1000000', '500000', '250000', '100000', '50000', '5000'].map(n => 'divisions_administratives_comarques_' + n).join(',');
  async function limWms(nw, se, W, H){
    const a = L.CRS.EPSG3857.project(nw), b = L.CRS.EPSG3857.project(se);
    const bbox = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)].map(v => v.toFixed(2)).join(',');
    const url = `${LIM_WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${LIM_CAPES}&STYLES=&CRS=EPSG:3857&BBOX=${bbox}&WIDTH=${W}&HEIGHT=${H}&FORMAT=image/png&TRANSPARENT=TRUE`;
    return await expImg(url);
  }
  function limDibuixaWms(ctx, im, W, H){
    const t = document.createElement('canvas'); t.width = W; t.height = H;
    const g = t.getContext('2d'); g.drawImage(im, 0, 0, W, H);
    g.globalCompositeOperation = 'source-in'; g.fillStyle = '#fff'; g.fillRect(0, 0, W, H);   // tot blanc, es conserva només l'alfa de la línia
    ctx.globalAlpha = 0.85; ctx.drawImage(t, 0, 0); ctx.globalAlpha = 1;
  }
  async function limCarrega(){
    if (lim.com !== undefined || lim.carregant) return;
    lim.carregant = true;
    try{ lim.com = await fetch('data/comarques.geojson').then(r => r.ok ? r.json() : null); }catch(e){ lim.com = null; }
    lim.carregant = false;
  }
  // Tot blanc i subtil. Només es fa servir data/comarques.geojson: les línies fines són totes les comarques i,
  // si el fitxer és topològic (vores compartides), el contorn exterior (costa i fronteres) es dibuixa una mica més gruixut.
  function expLimits(ctx, P, k){
    if (!lim.com || !lim.com.features) return;
    const anells = [], afegeix = r => anells.push(r.map(c => [c[1], c[0]]));
    lim.com.features.forEach(f => { const g = f.geometry; if (!g) return;
      if (g.type === 'Polygon') g.coordinates.forEach(afegeix);
      else if (g.type === 'MultiPolygon') g.coordinates.forEach(pg => pg.forEach(afegeix));
      else if (g.type === 'LineString') afegeix(g.coordinates);
      else if (g.type === 'MultiLineString') g.coordinates.forEach(afegeix); });
    ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.setLineDash([]); ctx.strokeStyle = '#fff';
    const traça = (segs, w, op) => { ctx.globalAlpha = op; ctx.lineWidth = w * k; ctx.beginPath();
      segs.forEach(([p, q]) => { const a = P(p), b = P(q); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }); ctx.stroke(); ctx.globalAlpha = 1; };
    const clau = (p, q) => { const a = p[0].toFixed(4) + ',' + p[1].toFixed(4), b = q[0].toFixed(4) + ',' + q[1].toFixed(4); return a < b ? a + '|' + b : b + '|' + a; };
    const segs = [], cnt = new Map();
    anells.forEach(r => { for (let i = 1; i < r.length; i++){ segs.push([r[i - 1], r[i]]); const c = clau(r[i - 1], r[i]); cnt.set(c, (cnt.get(c) || 0) + 1); } });
    const ext = segs.filter(([p, q]) => cnt.get(clau(p, q)) === 1);
    if (ext.length > 0 && ext.length < segs.length * 0.5){
      traça(segs.filter(([p, q]) => cnt.get(clau(p, q)) > 1), 0.8, 0.75);          // vores interiors entre comarques
      traça(ext, 1.2, 0.9);                                                          // contorn exterior
    }else traça(segs, 1.0, 0.8);                                                     // dades no topològiques: tot igual
  }

  // ---- Exportació d'imatge: l'usuari tria l'àrea i es compon (a alta resolució) amb les capes actives i les seves llegendes ----
  const EXP = { actiu: false, bar: null, caixa: null, ocupat: false, net: null };
  const EXP_FONT = 'Roboto, "Helvetica Neue", Arial, sans-serif', EXP_MONO = '"Roboto Mono", ui-monospace, Menlo, monospace';
  const EXP_CAT = [[40.40, 0.00], [42.95, 3.45]];             // Tot Catalunya: [[S, O], [N, E]] fix, independent del zoom del visor
  const EXP_LLARG = 3000;                                    // píxels del costat llarg del mapa exportat
  const EXP_ECHO_COLS = ['#0000B3', '#0033FF', '#0080FF', '#00CCFF', '#00FFFF', '#4C7300', '#80B300', '#00CC00', '#FFFF00', '#FFA500', '#FF7F00', '#FF0000', '#FF00FF', '#800080'];
  const EXP_ECHO_LBL = ['1', '2', '3', '4', '5', '6', '7', '8', '10', '12', '14', '16', '20'];
  (function(){
    const st = document.createElement('style');
    st.textContent = `
      #map.exp-sel, #map.exp-sel .leaflet-interactive{ cursor:crosshair !important; touch-action:none; }
      #exp-bar{ position:fixed; top:74px; left:50%; transform:translateX(-50%); z-index:2500; background:var(--panel, #fff); color:var(--text, #222);
        border:1px solid var(--panel-border, #ccc); border-radius:3px; box-shadow:0 2px 10px rgba(0,0,0,.3); padding:8px 10px; font:13px/1.3 var(--font-ui, sans-serif);
        display:flex; align-items:center; gap:10px; flex-wrap:wrap; max-width:calc(100vw - 16px); }
      #exp-bar b{ font-weight:600; }
      #exp-bar select{ font:inherit; font-size:12px; padding:4px 6px; border:1px solid var(--panel-border, #ccc); background:#fff; color:inherit; border-radius:3px; }
      #exp-bar button{ font:inherit; font-size:12px; padding:5px 10px; border:1px solid var(--panel-border, #ccc); background:#fff; color:inherit; border-radius:3px; cursor:pointer; }
      #exp-bar button:hover{ border-color:#C8102E; color:#C8102E; }
      #exp-caixa{ position:absolute; z-index:1200; border:2px solid #fff; outline:1px solid rgba(0,0,0,.6); box-shadow:0 0 0 9999px rgba(8,12,18,.45); pointer-events:none; }
      @media (max-width:640px){ #exp-bar{ top:64px; font-size:12px; } }`;
    document.head.appendChild(st);
    const btn = document.getElementById('export-btn');
    if (btn) btn.addEventListener('click', e => { e.stopImmediatePropagation(); e.preventDefault(); EXP.actiu ? expAtura() : expInici(); }, true);
  })();

  function expTs(){
    if (typeof currentTs !== 'undefined' && currentTs) return currentTs;
    if (nowc.ts) return nowc.ts;
    const f = nowc.hist && nowc.hist.final_utc; if (!f) return null;
    const k = nowcClau(nowcMs(f.replace(/[-:TZ]/g, '').slice(0, 12))); return k.slice(0, 8) + '_' + k.slice(8);
  }
  function expMissatge(h){ if (EXP.bar){ EXP.bar.querySelector('.exp-t').innerHTML = h; } }
  function expInici(){
    const ov = document.getElementById('export-overlay'); if (ov) ov.classList.remove('visible');
    if (!expTs()){ alert('Encara no hi ha cap frame carregat.'); return; }
    EXP.actiu = true;
    const btn = document.getElementById('export-btn'); if (btn) btn.classList.add('active');
    map.closePopup();
    map.dragging.disable(); map.doubleClickZoom.disable();
    const cont = map.getContainer(); cont.classList.add('exp-sel');
    const bar = document.createElement('div'); bar.id = 'exp-bar';
    const modo = expModActiu();
    EXP.fmt = 'png';
    bar.innerHTML = '<span class="exp-t"><b>Exporta imatge</b> · arrossega sobre el mapa per triar l\'àrea</span>' +
      '<select id="exp-fmt" title="Format"><option value="png">Imatge (PNG)</option><option value="gif">GIF animat</option></select>' +
      '<select id="exp-rang" style="display:none" title="Durada">' + (modo
        ? [6, 12, 24, 48].map(h => `<option value="${h}"${h === 12 ? ' selected' : ''}>Següents ${h} h</option>`).join('')
        : [1, 2, 3, 6].map(h => `<option value="${h}"${h === 3 ? ' selected' : ''}>Últimes ${h} h</option>`).join('')) + '</select>' +
      '<select id="exp-vel" style="display:none" title="Fotogrames per segon">' + [2, 4, 6, 8, 10].map(f => `<option value="${f}"${f === 4 ? ' selected' : ''}>${f} fps</option>`).join('') + '</select>' +
      '<button data-a="tot">Tot Catalunya</button><button data-a="no">Cancel·la</button>';
    document.body.appendChild(bar); EXP.bar = bar;
    L.DomEvent.disableClickPropagation(bar);
    bar.querySelector('#exp-fmt').addEventListener('change', e => {
      EXP.fmt = e.target.value; bar.querySelector('#exp-rang').style.display = bar.querySelector('#exp-vel').style.display = EXP.fmt === 'gif' ? '' : 'none';
      bar.querySelector('.exp-t').innerHTML = EXP.fmt === 'gif' ? '<b>Exporta GIF</b> · arrossega sobre el mapa per triar l\'àrea' : '<b>Exporta imatge</b> · arrossega sobre el mapa per triar l\'àrea';
    });
    bar.addEventListener('click', e => {
      const a = e.target.dataset && e.target.dataset.a; if (!a || EXP.ocupat) return;
      if (a === 'no') expAtura();
      else if (a === 'tot'){ const p = map.latLngToContainerPoint(L.latLng(EXP_CAT[1][0], EXP_CAT[0][1])), q = map.latLngToContainerPoint(L.latLng(EXP_CAT[0][0], EXP_CAT[1][1])); expGenera(p.x, p.y, q.x, q.y, true); }
    });
    let ini = null;
    const pt = e => { const r = cont.getBoundingClientRect(); return [Math.min(Math.max(e.clientX - r.left, 0), r.width), Math.min(Math.max(e.clientY - r.top, 0), r.height)]; };
    const pinta = p => {
      if (!EXP.caixa){ EXP.caixa = document.createElement('div'); EXP.caixa.id = 'exp-caixa'; cont.appendChild(EXP.caixa); }
      const x = Math.min(ini[0], p[0]), y = Math.min(ini[1], p[1]);
      Object.assign(EXP.caixa.style, { left: x + 'px', top: y + 'px', width: Math.abs(p[0] - ini[0]) + 'px', height: Math.abs(p[1] - ini[1]) + 'px' });
    };
    const down = e => {
      if (EXP.ocupat || (e.button !== undefined && e.button > 0) || e.target.closest('.leaflet-control, #exp-bar, .leaflet-popup')) return;
      e.preventDefault(); e.stopPropagation();
      ini = pt(e); try{ cont.setPointerCapture(e.pointerId); }catch(_){}
      pinta(ini);
    };
    const move = e => { if (!ini) return; e.preventDefault(); pinta(pt(e)); };
    const up = e => {
      if (!ini) return;
      const p = pt(e), a = ini; ini = null;
      if (Math.abs(p[0] - a[0]) < 30 || Math.abs(p[1] - a[1]) < 30){ if (EXP.caixa){ EXP.caixa.remove(); EXP.caixa = null; } return; }
      expGenera(Math.min(a[0], p[0]), Math.min(a[1], p[1]), Math.max(a[0], p[0]), Math.max(a[1], p[1]));
    };
    const tecla = e => { if (e.key === 'Escape' && !EXP.ocupat) expAtura(); };
    cont.addEventListener('pointerdown', down, true); cont.addEventListener('pointermove', move, true); cont.addEventListener('pointerup', up, true);
    document.addEventListener('keydown', tecla);
    EXP.net = () => {
      cont.removeEventListener('pointerdown', down, true); cont.removeEventListener('pointermove', move, true); cont.removeEventListener('pointerup', up, true);
      document.removeEventListener('keydown', tecla);
    };
  }
  function expAtura(){
    EXP.actiu = false; EXP.ocupat = false;
    if (EXP.net){ EXP.net(); EXP.net = null; }
    if (EXP.bar){ EXP.bar.remove(); EXP.bar = null; }
    if (EXP.caixa){ EXP.caixa.remove(); EXP.caixa = null; }
    map.dragging.enable(); map.doubleClickZoom.enable();
    map.getContainer().classList.remove('exp-sel');
    const btn = document.getElementById('export-btn'); if (btn) btn.classList.remove('active');
  }

  const expImg0 = url => new Promise(res => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => res(i); i.onerror = () => res(null); i.src = url; });
  const expImg = url => { if (!EXP.cache) return expImg0(url); if (!EXP.cache.has(url)) EXP.cache.set(url, expImg0(url)); return EXP.cache.get(url); };
  async function expPool(items, n, fn){ let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < items.length){ await fn(items[i++]); } })); }

  // Capa de tessel·les (mapa base o satèl·lit): només es demanen les que cauen dins l'àrea
  async function expTessel(ctx, o){
    const a = map.project(o.nw, o.zt), b = map.project(o.se, o.zt), nMax = Math.round(256 * Math.pow(2, o.zt) / o.tam);
    const llista = [];
    for (let x = Math.floor(a.x / o.tam); x <= Math.floor(b.x / o.tam); x++)
      for (let y = Math.max(0, Math.floor(a.y / o.tam)); y <= Math.min(nMax - 1, Math.floor(b.y / o.tam)); y++) llista.push([x, y]);
    let fets = 0, fallats = 0;
    await expPool(llista, 8, async ([x, y]) => {
      const im = await expImg(o.url(((x % nMax) + nMax) % nMax, y));
      if (im){ const r = o.rect(x, y); ctx.globalAlpha = o.alpha; ctx.drawImage(im, r[0], r[1], r[2] + 0.7, r[3] + 0.7); ctx.globalAlpha = 1; } else fallats++;
      o.prog && o.prog(++fets, llista.length);
    });
    return { total: llista.length, fallats };
  }

  function expVectors(ctx, P, k){
    const grups = [];
    [nowc.marcs, nowc.movCapa].forEach(g => { if (g && map.hasLayer(g)) grups.push(g); });
    const marcadors = [];
    const traç = (l, trac) => {
      const o = l.options;
      if (o.fill && o.fillOpacity > 0){ ctx.globalAlpha = o.fillOpacity; ctx.fillStyle = o.fillColor || o.color; ctx.fill(); }
      if (o.stroke !== false && o.weight > 0){
        ctx.globalAlpha = o.opacity === undefined ? 1 : o.opacity; ctx.strokeStyle = o.color; ctx.lineWidth = o.weight * k;
        ctx.lineCap = o.lineCap || 'round'; ctx.lineJoin = 'round';
        ctx.setLineDash(o.dashArray ? String(o.dashArray).split(/[ ,]+/).map(v => +v * k) : []);
        ctx.stroke();
      }
      ctx.globalAlpha = 1; ctx.setLineDash([]);
    };
    grups.forEach(g => g.eachLayer(l => {
      if (l instanceof L.Rectangle){
        const b = l.getBounds(), p1 = P(b.getNorthWest()), p2 = P(b.getSouthEast());
        ctx.beginPath(); ctx.rect(p1[0], p1[1], p2[0] - p1[0], p2[1] - p1[1]); traç(l);
      }else if (l instanceof L.CircleMarker){
        const p = P(l.getLatLng());
        ctx.beginPath(); ctx.arc(p[0], p[1], l.getRadius() * k, 0, 2 * Math.PI); traç(l);
      }else if (l instanceof L.Polyline){
        const ll = l.getLatLngs(); ctx.beginPath();
        (Array.isArray(ll[0]) ? ll : [ll]).forEach(part => part.forEach((q, i) => { const p = P(q); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }));
        traç(l);
      }else if (l instanceof L.Marker && l._exp){ marcadors.push(l); }
    }));
    marcadors.forEach(l => {
      const e = l._exp, p = P(l.getLatLng());
      ctx.save(); ctx.translate(p[0], p[1]); ctx.scale(k, k);
      if (e.t === 'tk'){
        ctx.font = `600 9.5px ${EXP_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.shadowColor = '#000'; ctx.shadowBlur = 3; ctx.fillStyle = '#fff';
        ctx.fillText(e.txt, 0, 6 + 5); ctx.fillText(e.txt, 0, 6 + 5);
      }else if (e.t === 'mv'){
        if (e.mou){
          ctx.save(); ctx.rotate(e.rumb * Math.PI / 180); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
          ctx.strokeStyle = 'rgba(11,19,32,.55)'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(0, -4); ctx.lineTo(0, -15); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(0, -23); ctx.lineTo(7.5, -11); ctx.lineTo(0, -14.5); ctx.lineTo(-7.5, -11); ctx.closePath();
          ctx.fillStyle = 'rgba(11,19,32,.55)'; ctx.fill(); ctx.lineWidth = 3.5; ctx.stroke();
          ctx.strokeStyle = e.col; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(0, -4); ctx.lineTo(0, -15); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(0, -22); ctx.lineTo(6.2, -11.6); ctx.lineTo(0, -14.8); ctx.lineTo(-6.2, -11.6); ctx.closePath();
          ctx.fillStyle = e.col; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.stroke();
          ctx.restore();
        }
        ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 4; ctx.shadowOffsetY = 1;
        ctx.beginPath(); ctx.arc(0, 0, 5.5, 0, 2 * Math.PI); ctx.fillStyle = 'rgba(11,19,32,.6)'; ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.beginPath(); ctx.arc(0, 0, 5, 0, 2 * Math.PI); ctx.fillStyle = '#fff'; ctx.fill();
        ctx.beginPath(); ctx.arc(0, 0, 3, 0, 2 * Math.PI); ctx.fillStyle = e.col; ctx.fill();
        if (e.pill && map.getZoom() >= 8){
          ctx.font = `600 10.5px ${EXP_MONO}`;
          const w = ctx.measureText(e.pill).width + 14, h = 19, x = 10, y = 4;
          ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, 9.5) : ctx.rect(x, y, w, h);
          ctx.shadowColor = 'rgba(0,0,0,.4)'; ctx.shadowBlur = 4; ctx.shadowOffsetY = 1;
          ctx.fillStyle = 'rgba(11,19,32,.82)'; ctx.fill(); ctx.shadowColor = 'transparent';
          ctx.strokeStyle = 'rgba(255,255,255,.28)'; ctx.lineWidth = 1; ctx.stroke();
          ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(e.pill, x + 7, y + h / 2 + 0.5);
        }
      }
      ctx.restore();
    });
  }

  // Compon la imatge (mapa + capes actives + peu amb llegendes) segons l'estat actual del visor. Retorna el canvas.
  async function expCompon(x0, y0, x1, y1, opt){
    opt = opt || {}; const LL = opt.llarg || EXP_LLARG, AMPLE = opt.ample || 1500;
    {
      // "Tot Catalunya": coordenades fixes i mida independent del zoom/enquadrament del visor
      const cat = !!opt.cat, Z0 = cat ? 8 : map.getZoom();
      const nw = cat ? L.latLng(EXP_CAT[1][0], EXP_CAT[0][1]) : map.containerPointToLatLng([x0, y0]), se = cat ? L.latLng(EXP_CAT[0][0], EXP_CAT[1][1]) : map.containerPointToLatLng([x1, y1]);
      const pa = map.project(nw, Z0), pb = map.project(se, Z0);
      const selW = cat ? pb.x - pa.x : x1 - x0, selH = cat ? pb.y - pa.y : y1 - y0;
      const k = Math.min(8, LL / Math.max(selW, selH));
      const MW = Math.round(selW * k), MH = Math.round(selH * k);
      const Zf = Z0 + Math.log2(k);
      const org = map.project(nw, Zf);
      const P = ll => { const q = map.project(L.latLng(ll), Zf); return [q.x - org.x, q.y - org.y]; };

      // --- quines capes estan actives
      const echoOn = typeof currentOverlay !== 'undefined' && currentOverlay && map.hasLayer(currentOverlay) && currentOverlay.options.opacity > 0;
      const reflOn = !!(refl.overlay && map.hasLayer(refl.overlay));
      const modOn = !!(mod.sel && mod.overlay && map.hasLayer(mod.overlay) && mod.models[modK()]);
      const satOn = !!(sat.capa && map.hasLayer(sat.capa));
      const stormOn = !!(nowc.marcs && map.hasLayer(nowc.marcs) && nowc.marcs.getLayers().length);
      const base = Object.values(baseLayers).filter(l => map.hasLayer(l));

      // --- peus i capçalera: dimensions segons l'amplada final
      const Wc = Math.max(MW, AMPLE), u = Wc / 1000, HH = 0, FH = Math.round(60 * u);
      const cv = document.createElement('canvas'); cv.width = Wc; cv.height = HH + MH + FH;
      const ctx = cv.getContext('2d'); ctx.imageSmoothingQuality = 'high';
      ctx.fillStyle = '#e9ecef'; ctx.fillRect(0, 0, cv.width, cv.height);
      const mx = Math.round((Wc - MW) / 2), my = HH;

      // --- mapa
      ctx.save(); ctx.beginPath(); ctx.rect(mx, my, MW, MH); ctx.clip(); ctx.translate(mx, my);
      ctx.fillStyle = '#cfd6dd'; ctx.fillRect(0, 0, MW, MH);
      let prog = opt.prog || ((n, t) => expMissatge(`<b>Generant imatge…</b> ${n} / ${t} tessel·les`));
      let fallBase = 0, totBase = 0;
      // Sense noms: CARTO en versió "nolabels"; la base ICGC es neteja (mar i terra plans, es conserven les línies i es dibuixa la costa)
      const icgcL = (typeof baseLayers !== 'undefined') ? baseLayers.icgc : null;
      const net = (icgcL && base.includes(icgcL)) ? await icgcNet(nw, se, org, Zf, MW, MH) : null;
      for (const l of base){
        if (l === icgcL && net){ ctx.drawImage(net.base, 0, 0); continue; }
        const zt = Math.min(l.options.maxZoom || 12, Math.round(Zf)), sc = Math.pow(2, Zf - zt);
        const r = await expTessel(ctx, { tam: 256, zt, nw, se, alpha: l.options.opacity === undefined ? 1 : l.options.opacity, prog,
          url: (x, y) => { const tz = l._tileZoom; l._tileZoom = zt; try{ return l.getTileUrl({ x, y, z: zt }).replace('/light_all/', '/light_nolabels/').replace('/dark_all/', '/dark_nolabels/'); } finally { l._tileZoom = tz; } },
          rect: (x, y) => [x * 256 * sc - org.x, y * 256 * sc - org.y, 256 * sc, 256 * sc] });
        fallBase += r.fallats; totBase += r.total;
      }
      if (satOn){
        const zt = Math.min(12, Math.round(Zf));
        await expTessel(ctx, { tam: 512, zt, nw, se, alpha: sat.capa.options.opacity, prog,
          url: (x, y) => sat.capa.getTileUrl(Object.assign(L.point(x, y), { z: zt })),
          rect: (x, y) => { const a = P(map.unproject(L.point(x * 512, y * 512), zt)), b = P(map.unproject(L.point((x + 1) * 512, (y + 1) * 512), zt)); return [a[0], a[1], b[0] - a[0], b[1] - a[1]]; } });
      }
      if (!opt.sil) expMissatge('<b>Generant imatge…</b> radar i tempestes');
      for (const ov of [echoOn ? currentOverlay : null, reflOn ? refl.overlay : null, modOn ? mod.overlay : null]){
        if (!ov) continue;
        const im = await expImg(ov._url);
        if (!im) continue;
        const b = ov.getBounds(), a = P(b.getNorthWest()), c = P(b.getSouthEast());
        ctx.globalAlpha = ov.options.opacity; ctx.drawImage(im, a[0], a[1], c[0] - a[0], c[1] - a[1]); ctx.globalAlpha = 1;
      }
      if (!opt.senseLimits){
        await limCarrega(); expLimits(ctx, P, k);                                  // contorns sempre des de comarques.geojson (el WMS porta noms)
      }
      expVectors(ctx, P, k);
      ctx.restore();
      ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = Math.max(1, u); ctx.strokeRect(mx, my, MW, MH);

      const TS = expTs(), MM = modOn ? mod.models[modK()] : null, ms = modOn ? mod.t : nowcMs(TS.replace('_', ''));
      const dl = new Intl.DateTimeFormat('ca-ES', { timeZone: 'Europe/Madrid', day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(ms));
      const dUtc = nowcClau(ms).slice(8, 10) + ':' + nowcClau(ms).slice(10, 12) + ' UTC';

      // --- peu: llegendes de les capes actives
      const fy = HH + MH; ctx.fillStyle = '#fff'; ctx.fillRect(0, fy, Wc, FH);
      ctx.fillStyle = '#d3d8de'; ctx.fillRect(0, fy, Wc, Math.max(1, u));
      const blocs = [];
      if (echoOn) blocs.push({ w: 3, f: (x, y, w) => expLlegBandes(ctx, u, x, y, w, 'ALÇADA ECHO TOP (KM)', EXP_ECHO_COLS, EXP_ECHO_LBL, 'frontera') });
      if (reflOn) blocs.push({ w: 3, f: (x, y, w) => expLlegBandes(ctx, u, x, y, w, 'REFLECTIVITAT RADAR (dBZ)', REFL_LLEGENDA.map(q => q[0]), REFL_LLEGENDA.map((q, i) => i % 2 === 0 ? q[1] + (i === REFL_LLEGENDA.length - 1 ? '+' : '') : ''), 'centre') });
      if (satOn){
        const li = await expImg(`${SAT.url}?service=WMS&request=GetLegendGraphic&version=1.3.0&format=image/png&layer=${encodeURIComponent(SAT.capa)}&style=${encodeURIComponent(SAT.estil)}`);
        blocs.push({ w: 3, f: (x, y, w) => {
          ctx.fillStyle = '#52606d'; ctx.font = `600 ${9.5 * u}px ${EXP_FONT}`; ctx.fillText('SATÈL·LIT IR 10,5 µm (MTG)', x, y + 5 * u);
          if (li){ const h = Math.min(22 * u, w * li.height / li.width), ww = h * li.width / li.height; ctx.drawImage(li, x, y + 13 * u, Math.min(w, ww), h); }
        } });
      }
      if (modOn){
        const P = modPaleta(), hor = mod.sel.endsWith(':h');
        blocs.push({ w: 3, f: (x, y, w) => expLlegBandes(ctx, u, x, y, w, `${MM.nom.toUpperCase()} · ${hor ? 'PLUJA HORÀRIA (mm/h)' : 'PLUJA ACUMULADA' + (mod.acum ? ' ' + mod.acum + ' h' : ' DES DE L\'INICI') + ' (mm)'}`,
          [MOD_ZERO].concat(P.map(q => q[1])), P.map(q => String(q[0])), 'alterna') });
      }
      blocs.push({ w: 2.4, f: (x, y, w) => {
        ctx.fillStyle = '#52606d'; ctx.font = `600 ${9.5 * u}px ${EXP_FONT}`; ctx.textBaseline = 'middle'; ctx.fillText(modOn ? 'PREVISIÓ VÀLIDA' : 'DATA I HORA', x, y + 5 * u);
        const hh = nowcHoraLocal(ms);
        ctx.fillStyle = '#243b53'; ctx.font = `600 ${13 * u}px ${EXP_MONO}`; ctx.fillText(dl, x, y + 24 * u);
        const w1 = ctx.measureText(dl).width;
        ctx.font = `700 ${19 * u}px ${EXP_MONO}`; ctx.fillStyle = '#C8102E'; ctx.fillText(hh, x + w1 + 10 * u, y + 24 * u);
        const w2 = ctx.measureText(hh).width;
        ctx.fillStyle = '#7b8794'; ctx.font = `500 ${10 * u}px ${EXP_MONO}`; ctx.fillText('local · ' + dUtc, x + w1 + w2 + 20 * u, y + 25 * u);
        if (modOn){ const rt = new Date(modMs(MM)); ctx.fillStyle = '#52606d'; ctx.font = `500 ${9.5 * u}px ${EXP_FONT}`;
          ctx.fillText(`${MM.nom} · run ${String(rt.getUTCDate()).padStart(2, '0')}/${String(rt.getUTCMonth() + 1).padStart(2, '0')} ${String(rt.getUTCHours()).padStart(2, '0')} UTC · +${Math.round((mod.t - modMs(MM)) / 3600000)} h`, x, y + 40 * u); }
      } });
      const tot = blocs.reduce((s, b) => s + b.w, 0), pad = 18 * u, gap = 26 * u;
      let cx = pad; const util = Wc - 2 * pad - gap * Math.max(0, blocs.length - 1);
      blocs.forEach(b => { const w = Math.min(util * b.w / tot, 520 * u); b.f(cx, fy + 7 * u, w); cx += w + gap; });
      ctx.fillStyle = '#7b8794'; ctx.font = `400 ${9 * u}px ${EXP_FONT}`; ctx.textAlign = 'left';
      const cred = [echoOn ? 'Meteocat' : '', (reflOn || stormOn) ? 'AEMET' : '', satOn ? '© EUMETSAT' : '', modOn ? (MM.model === 'arome' ? 'AROME (Météo-France)' : 'WRF-SMC (SMC)') : ''].filter(Boolean).join(' · ');
      const txtCred = `Dades: ${cred}  |  Mapa base: ${base.length ? (currentBase === 'satelit' ? 'Esri' : currentBase === 'icgc' ? '© ICGC' : currentBase === 'topo' ? '© OpenTopoMap · OSM' : '© CARTO · © OpenStreetMap') : ''}`;
      ctx.fillText(txtCred, pad, fy + FH - 8 * u);
      if (totBase && fallBase > totBase * 0.2) { ctx.textAlign = 'right'; ctx.fillStyle = '#C8102E'; ctx.fillText('Atenció: part del mapa base no s\'ha pogut carregar', Wc - pad, fy + FH - 8 * u); }

      const nomBase = modOn ? `${modK()}_${mod.sel.endsWith(':h') ? 'pluja_h' : 'pluja_acum'}` : `echotops${satOn ? '_sat' : ''}${reflOn ? '_refl' : ''}`;
      return { cv, ms, TS, modOn, nomBase, clauMs: nowcClau(ms) };
    }
  }

  async function expGenera(x0, y0, x1, y1, cat){
    if (EXP.ocupat) return;
    EXP.ocupat = true; EXP.cat = !!cat;
    if (!EXP.caixa){ EXP.caixa = document.createElement('div'); EXP.caixa.id = 'exp-caixa'; map.getContainer().appendChild(EXP.caixa); }
    Object.assign(EXP.caixa.style, { left: x0 + 'px', top: y0 + 'px', width: (x1 - x0) + 'px', height: (y1 - y0) + 'px' });
    try{
      if (EXP.fmt === 'gif'){ await expGif(x0, y0, x1, y1); return; }
      const r = await expCompon(x0, y0, x1, y1, { cat: EXP.cat });
      expMissatge('<b>Desant…</b>');
      const blob = await new Promise(res => r.cv.toBlob(res, 'image/png'));
      if (!blob) throw new Error('canvas buit');
      expDesa(blob, r.modOn ? `${r.nomBase}_${r.clauMs}Z.png` : `${r.nomBase.replace('echotops', 'echotops_' + r.TS.replace('_', '') + 'Z')}.png`);
      expMissatge(`✓ <b>Imatge descarregada</b> (${r.cv.width}×${r.cv.height} px)`);
      setTimeout(() => { if (EXP.actiu) expAtura(); }, 1800);
    }catch(err){
      console.error(err);
      expMissatge('<b style="color:#C8102E">No s\'ha pogut generar la imatge.</b> ' + (err && err.message ? err.message : ''));
      EXP.ocupat = false;
      if (EXP.caixa){ EXP.caixa.remove(); EXP.caixa = null; }
    }
  }
  function expDesa(blob, nom){
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = nom;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 20000);
  }

  // ---- GIF animat: mateixa composició que la imatge, un fotograma per instant ----
  const EXP_GIF_MAX = 72;
  const expModActiu = () => !!(mod.sel && mod.overlay && map.hasLayer(mod.overlay) && mod.models[modK()]);
  async function expGif(x0, y0, x1, y1){
    const modo = expModActiu(), n = +(EXP.bar.querySelector('#exp-rang').value) || 3;
    expMissatge('<b>GIF…</b> carregant el codificador');
    const resp = await fetch('https://cdnjs.cloudflare.com/ajax/libs/gif.js/0.2.0/gif.worker.js');
    if (!resp.ok) throw new Error('no s\'ha pogut carregar el codificador de GIF');
    const wUrl = URL.createObjectURL(await resp.blob());
    const sig = () => [typeof currentOverlay !== 'undefined' && currentOverlay ? currentOverlay._url : '', refl.overlay ? refl.overlay._url : '', sat.capa ? 1 : 0, nowc.ts || ''].join('|');
    const espera = async () => { let a = sig(), est = 0; for (let i = 0; i < 40 && est < 2; i++){ await new Promise(r => setTimeout(r, 150)); const b = sig(); est = b === a ? est + 1 : 0; a = b; } };
    EXP.cache = new Map();
    const restaura = [];
    let gif = null, nFot = 0, nom = 'animacio';
    try{
      const frames = [];                                                  // funcions que posen el visor a cada instant
      if (modo){
        const m = mod.models[modK()], t0 = mod.t, ini = modMs(m), fi = ini + (m.passos - 1) * 3600000, orig = mod.t;
        for (let t = t0; t <= Math.min(fi, t0 + n * 3600000); t += 3600000) frames.push(async () => { mod.t = t; await modMostra(); });
        restaura.push(async () => { mod.t = orig; await modMostra(); });
      }else{
        const vt = visibleTimestamps, i1 = vt.indexOf(currentTs), orig = i1;
        if (i1 < 0) throw new Error('no hi ha cap fotograma seleccionat');
        const t1 = tsToDate(vt[i1]).getTime();
        for (let i = 0; i <= i1; i++) if (t1 - tsToDate(vt[i]).getTime() <= n * 3600000) frames.push(async () => { showFrame(i); await espera(); });
        restaura.push(async () => { showFrame(orig); });
      }
      let last = null, prev = null, dl = Math.round(1000 / (+(EXP.bar.querySelector('#exp-vel').value) || 4));
      for (let i = 0; i < frames.length && nFot < EXP_GIF_MAX; i++){
        expMissatge(`<b>Generant GIF…</b> fotograma ${i + 1} / ${frames.length}`);
        await frames[i]();
        const sg = sig() + '|' + (modo ? mod.t : '');
        if (sg === prev) continue; prev = sg;
        const r = await expCompon(x0, y0, x1, y1, { llarg: 1100, ample: 1100, sil: true, prog: () => {}, cat: EXP.cat });
        if (!gif) gif = new GIF({ workers: 3, quality: 5, globalPalette: true, width: r.cv.width, height: r.cv.height, workerScript: wUrl });
        if (last) last.delay = dl;
        last = { delay: dl };
        gif.addFrame(r.cv, { copy: true, delay: dl }); if (!nFot) nom = r.nomBase; nFot++;
        if (nFot === 1) EXP.gif0 = r.clauMs; EXP.gif1 = r.clauMs;
        EXP.ultim = r;
      }
      if (nFot < 2) throw new Error('hi ha menys de 2 fotogrames en aquest rang');
      gif.frames[gif.frames.length - 1].delay = 1500;                       // pausa al final
      expMissatge('<b>Codificant el GIF…</b> pot trigar una mica');
      const blob = await new Promise((res, rej) => { gif.on('finished', res); gif.on('abort', () => rej(new Error('codificació interrompuda'))); gif.render(); });
      expDesa(blob, `${nom}_${EXP.gif0}-${EXP.gif1}Z.gif`);
      expMissatge(`✓ <b>GIF descarregat</b> (${nFot} fotogrames, ${(blob.size / 1048576).toFixed(1)} MB)`);
      setTimeout(() => { if (EXP.actiu) expAtura(); }, 2200);
    }finally{
      for (const f of restaura) try{ await f(); }catch(_){}
      EXP.cache = null; URL.revokeObjectURL(wUrl);
    }
  }
  // Barra de colors amb etiquetes (a la frontera entre bandes o al centre de cada banda)
  function expLlegBandes(ctx, u, x, y, w, titol, cols, lbl, mode){
    const alt = mode === 'alterna';
    ctx.fillStyle = '#52606d'; ctx.font = `600 ${9.5 * u}px ${EXP_FONT}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(titol, x, y + (alt ? 3 : 5) * u);
    const bw = w / cols.length, by = y + (alt ? 18 : 13) * u, bh = (alt ? 9 : 11) * u;
    cols.forEach((c, i) => { ctx.fillStyle = c; ctx.fillRect(x + i * bw, by, bw + 0.5, bh); });
    if (alt){ ctx.strokeStyle = 'rgba(0,0,0,.3)'; ctx.lineWidth = Math.max(1, u * 0.3); ctx.strokeRect(x, by, w, bh); }
    ctx.fillStyle = '#243b53'; ctx.font = `400 ${(alt ? 8.5 : 9.5) * u}px ${EXP_MONO}`; ctx.textAlign = 'center';
    lbl.forEach((t, i) => { if (t) ctx.fillText(t, x + (mode === 'centre' ? (i + 0.5) : (i + 1)) * bw, alt ? (i % 2 === 0 ? by - 4.8 * u : by + bh + 5.5 * u) : by + 17 * u); });
    ctx.textAlign = 'left';
  }
  // ---- Pluviòmetres ACA (data/aca/pluja_hist.json, generat per aca_pluja.py): segueixen la barra de temps ----
  (function(){
    const COL = ['#888888', '#F2C200', '#F28C00', '#C8102E'];
    const NOM = ['', 'Prealerta', 'Avís taronja', 'Avís vermell'];
    const pane = map.createPane('acaPane'); pane.style.zIndex = 460;
    const grup = L.layerGroup();
    const stp = document.createElement('style');
    stp.textContent = '.aca-pill{position:absolute;transform:translate(-50%,-50%);white-space:nowrap;padding:2px 9px;border-radius:12px;border:2px solid #fff;' +
      'font:700 12px/1.25 var(--font-ui,sans-serif);box-shadow:0 1px 5px rgba(0,0,0,.55);cursor:pointer;letter-spacing:.01em;}' +
      '.aca-pill small{font-weight:400;font-size:10px;opacity:.92;margin-left:2px;}';
    document.head.appendChild(stp);
    const tog = document.getElementById('aca-toggle'), info = document.getElementById('aca-info');
    const hl = new Intl.DateTimeFormat('ca-ES', { timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    const f1 = x => (x === null || x === undefined) ? '—' : (Math.round(x * 10) / 10).toString().replace('.', ',');
    let H = null, ms0 = 0, ts = null, marcs = [], timer = null;

    // 1 groc = prealerta (intensitat > llindar) · 2 taronja = llindar baix en 30 min o 3 h · 3 vermell = llindar alt en 30 min o 3 h
    function nivell(a30, a3h, inten){
      const l30 = H.llindars['30min'], l3 = H.llindars['3h'], li = H.llindars.intensitat || 15;
      return (a30 > l30[1] || a3h > l3[1]) ? 3 : (a30 > l30[0] || a3h > l3[0]) ? 2 : (inten > li) ? 1 : 0;
    }
    function estat(a, k, base){                                  // estat de l'estació a l'índex de temps k
      let a30 = 0, a3 = 0, j0 = -1;
      for (let j = 0; j < 36 && k - j >= 0; j++) {
        const v = a[k - j];
        if (v === null || v === undefined) continue;
        a3 += v; if (j < 6) a30 += v;
        if (j < 6 && j0 < 0) j0 = j;                       // mesura més recent dins dels últims 30 min
      }
      if (j0 < 0) return { n: 0, i: null, a30: null, a3h: null, t: null };
      a30 /= 12; a3 /= 12;
      return { n: nivell(a30, a3, a[k - j0]), i: a[k - j0], a30, a3h: a3, t: base + (k - j0) * H.pas * 60000 };
    }
    function html(e){
      const c = e.cur, n = c.n;
      return `<div style="font:12px/1.5 var(--font-ui,sans-serif);min-width:190px;">` +
        `<b>${e.nom || e.id}</b>${e.comarca ? `<br><span style="opacity:.7">${e.comarca}</span>` : ''}` +
        (n ? `<div style="margin:4px 0;padding:2px 6px;background:${COL[n]};color:${n === 1 ? '#222' : '#fff'};display:table;border-radius:2px;font-weight:700;">${NOM[n]}</div>` : '') +
        `<br>Intensitat: <b>${f1(c.i)} mm/h</b><br>30 min: <b>${f1(c.a30)} mm</b> · 3 h: <b>${f1(c.a3h)} mm</b>` +
        `<br><span style="opacity:.7">${c.t ? 'Mesura de les ' + hl.format(new Date(c.t)) + ' h' : 'Sense dada en aquest instant'} · ACA</span></div>`;
    }
    function pinta(){
      if (!H) return;
      const msSel = ts ? nowcMs(ts.replace('_', '')) : null;
      let ar = null;                                       // font d'arxiu (dies/*.json) si l'instant queda fora de l'historic en viu
      if (msSel !== null && msSel < ms0 + 3 * 3600000) {
        ar = arxiuPer(msSel);
        if (!ar) { if (info) info.textContent = "Carregant l'arxiu dels pluviometres..."; return; }
      }
      const base = ar ? ar.ms0 : ms0;
      let k = ts ? Math.round((msSel - base) / (H.pas * 60000)) : H.estacions[0].i.length - 1;
      const nmax = ar ? ar.n - 1 : H.estacions[0].i.length - 1;
      if (k > nmax) k = nmax;
      let nav = 0;
      marcs.forEach(o => {
        const { e, m, p } = o;
        const serie = ar ? (ar.s[e.id] || null) : e.i;
        e.cur = (k < 0 || !serie) ? { n: 0, i: null, a30: null, a3h: null, t: null } : estat(serie, k, base);
        const n = e.cur.n;
        if (n) {                                            // en avís: etiqueta ovalada amb el valor que ha superat el llindar
          const l30 = H.llindars['30min'][0], l3 = H.llindars['3h'][0];
          const en30 = e.cur.a30 / l30 >= e.cur.a3h / l3;
          const txt = n === 1 ? `${Math.round(e.cur.i)}<small>mm/h</small>` : `${Math.round(en30 ? e.cur.a30 : e.cur.a3h)}<small>mm/${en30 ? '30′' : '3h'}</small>`;
          p.setIcon(L.divIcon({ className: '', iconSize: [0, 0],
            html: `<div class="aca-pill" style="background:${COL[n]};color:${n === 1 ? '#222' : '#fff'}">${txt}</div>` }));
          p.setZIndexOffset(1000 * n);
          if (grup.hasLayer(m)) grup.removeLayer(m);
          if (!grup.hasLayer(p)) grup.addLayer(p);
          nav++;
        } else {
          if (grup.hasLayer(p)) grup.removeLayer(p);
          if (!grup.hasLayer(m)) grup.addLayer(m);
        }
        if (p.isPopupOpen()) p.setPopupContent(html(e));
        if (m.isPopupOpen()) m.setPopupContent(html(e));
      });
      if (info) info.textContent = nav ? `${nav} pluviòmetre${nav > 1 ? 's' : ''} en avís (prealerta > ${H.llindars.intensitat || 15} mm/h · 30 min > ${H.llindars['30min'][0]} mm · 3 h > ${H.llindars['3h'][0]} mm)` :
                                         `${marcs.length} pluviòmetres · cap supera els llindars`;
    }
    const DIES = {};                                       // dia (AAAA-MM-DD) -> JSON | 'pend' | null (no existeix)
    let ARX = null;                                        // finestra d'arxiu: { key, ms0, n, s: {id: [...]} }
    const diaStr = ms => new Date(ms).toISOString().slice(0, 10);
    function arxiuPer(msSel){                              // dades de dies/*.json per a l'instant msSel (+3 h d'escalfament)
      const d0 = diaStr(msSel - 3 * 3600000), d1 = diaStr(msSel), key = d0 + '|' + d1;
      if (ARX && ARX.key === key) return ARX;
      const dies = d0 === d1 ? [d0] : [d0, d1];
      dies.forEach(dia => {
        if (dia in DIES) return;
        DIES[dia] = 'pend';
        fetch('data/aca/dies/' + dia + '.json').then(r => r.ok ? r.json() : null).catch(() => null)
          .then(j => { DIES[dia] = j; pinta(); });
      });
      if (dies.some(dia => DIES[dia] === 'pend')) return null;
      const n = dies.length * 288, s = {};
      dies.forEach((dia, q) => {
        const j = DIES[dia]; if (!j) return;
        Object.keys(j.v).forEach(id => {
          const arr = s[id] || (s[id] = new Array(n).fill(null));
          j.v[id].forEach((v, x) => { arr[q * 288 + x] = v; });
        });
      });
      ARX = { key: key, ms0: Date.parse(dies[0] + 'T00:00:00Z'), n: n, s: s };
      return ARX;
    }
    function dades(d){
      H = d; ms0 = Date.parse(d.t0);
      if (!marcs.length) {
        d.estacions.forEach(e => {
          e.cur = { n: 0 };
          const m = L.circleMarker([e.lat, e.lon], { pane: 'acaPane', radius: 4.5, color: '#777', weight: 0.8, opacity: 0.35, fillColor: COL[0], fillOpacity: 0.28 });
          m.bindPopup(() => html(e)); m.addTo(grup);
          const p = L.marker([e.lat, e.lon], { pane: 'acaPane', icon: L.divIcon({ className: '', iconSize: [0, 0], html: '' }) });
          p.bindPopup(() => html(e));
          marcs.push({ e, m, p });
        });
      } else {                                              // actualització: es conserven els marcadors i se'ls canvia la sèrie
        const per = {}; d.estacions.forEach(e => per[e.id] = e);
        marcs.forEach(o => { if (per[o.e.id]) o.e.i = per[o.e.id].i; });
      }
      pinta();
    }
    function carrega(){
      fetch('data/aca/pluja_hist.json?_=' + Date.now()).then(r => r.ok ? r.json() : Promise.reject()).then(dades)
        .catch(() => { if (info) info.textContent = 'Sense dades dels pluviòmetres'; });
    }
    function activa(on){
      if (on) { grup.addTo(map); carrega(); clearInterval(timer); timer = setInterval(carrega, 5 * 60 * 1000); }
      else { map.removeLayer(grup); clearInterval(timer); if (info) info.textContent = ''; }
    }
    window.acaMostra = t => { ts = t; if (tog && tog.checked) pinta(); };
    if (tog) { tog.addEventListener('change', () => activa(tog.checked)); activa(tog.checked); }
  })();
  // ---- fi Tempestes enganxades ----
