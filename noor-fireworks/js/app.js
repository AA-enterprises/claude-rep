/* Pak Fireworks: page behaviour, shop and cart. Data lives in config.js. */
(function () {
  const { business: BIZ, promo: PROMO, cities: CITIES, showrooms: ROOMS, categories: CATS, items: ITEMS } = window.NOOR;
  const PHOTOS = window.NOOR.photos || {};
  const photoFor = it => it.img || PHOTOS[it.k] || PHOTOS[CATS[0][0]];
  const SOCIAL = window.NOOR.social || {};
  const { PAL, makeSky, play, RATE } = window.Fireworks;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = v => 'PKR ' + Math.round(v).toLocaleString('en-US');
  const scrollToEl = el => el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
  const waLink = text => `https://wa.me/${BIZ.whatsapp}?text=${encodeURIComponent(text)}`;
  function openWhatsApp(text) {
    const a = document.createElement('a');
    a.href = waLink(text); a.target = '_blank'; a.rel = 'noopener';
    document.body.appendChild(a); a.click(); a.remove();
  }
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: cart lasts for this visit */ } }
  };

  /* ---------- Business details from config ---------- */
  const telHref = 'tel:' + BIZ.phone.replace(/[^\d+]/g, '');
  $$('[data-phone]').forEach(el => { el.textContent = BIZ.phone; });
  $$('[data-tel]').forEach(el => { el.href = telHref; });
  $$('[data-email]').forEach(el => { el.href = 'mailto:' + BIZ.email; el.textContent = BIZ.email; });
  $$('[data-hours]').forEach(el => { el.textContent = BIZ.hours; });
  $('#waFloat').href = waLink(`Assalam o Alaikum ${BIZ.name}, I have a question.`);
  $('#yr').textContent = new Date().getFullYear();
  $('#rooms').innerHTML = ROOMS.map(r => `<div class="room" style="--c:${r.color}"><h3>${esc(r.city)}</h3><p>${esc(r.area)}</p><p>${esc(r.hours)}</p><a href="tel:${r.phone.replace(/[^\d+]/g, '')}">${esc(r.phone)}</a>${r.map ? `<a class="dir" href="${esc(r.map)}" target="_blank" rel="noopener">Get directions</a>` : ''}</div>`).join('');
  $$('[data-social]').forEach(el => { const url = SOCIAL[el.dataset.social]; if (url) el.href = url; else el.hidden = true; });

  /* ---------- Toast ---------- */
  let toastTimer;
  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
  }

  /* ---------- Video hero ---------- */
  const BRAND = 'PAK', SUB = 'FIREWORKS';
  (function videoHero() {
    const sec = $('#top'), vid = $('#heroVid'), btn = $('#vidBtn'), cv = $('#nameFx');
    const setHH = () => document.documentElement.style.setProperty('--hh', ($('header.site').offsetHeight + ($('.promo') ? $('.promo').offsetHeight : 0)) + 'px');
    setHH(); addEventListener('resize', setHH);
    const PAUSE = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" rx="1"/><rect x="9.5" y="2" width="3.5" height="12" rx="1"/></svg>';
    const PLAY = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2l10 6-10 6z"/></svg>';
    let userPaused = reduce;
    vid.pause();
    const sync = () => { btn.innerHTML = vid.paused ? PLAY : PAUSE; btn.setAttribute('aria-label', vid.paused ? 'Play video' : 'Pause video'); };
    vid.addEventListener('play', sync); vid.addEventListener('pause', sync);
    btn.addEventListener('click', () => { if (vid.paused) { userPaused = false; vid.play().catch(() => {}); } else { userPaused = true; vid.pause(); } });
    const tryPlay = () => { if (!userPaused) vid.play().catch(() => {}); };
    tryPlay();
    new IntersectionObserver(e => { if (!e[0].isIntersecting) vid.pause(); else tryPlay(); }, { threshold: .25 }).observe($('#vidFig'));
    sync();

    /* Brand name formed by sparks: three rockets rise, burst, and their stars settle into the letters */
    if (reduce) { sec.classList.add('formed'); return; }
    const g = cv.getContext('2d'), brand = $('#brand');
    let W = 0, H = 0, pts = [], stars = [], rockets = [], t0 = 0, t0f = 0, phase = 0, raf = 0;
    function sample() {
      /* Draw each word of the name off-screen in the same font, then every few solid pixels becomes a spark */
      const s = sec.getBoundingClientRect(), out = [];
      brand.querySelectorAll('span').forEach((w, wi) => {
        const r = w.getBoundingClientRect(), cs = getComputedStyle(w), fs = parseFloat(cs.fontSize);
        if (!r.width) return;
        const c = document.createElement('canvas'); c.width = Math.ceil(r.width + fs); c.height = Math.ceil(r.height);
        const x = c.getContext('2d'); x.font = `${cs.fontWeight} ${fs}px ${cs.fontFamily}`; x.letterSpacing = cs.letterSpacing;
        const m = x.measureText(w.textContent), asc = m.fontBoundingBoxAscent || fs * .8, des = m.fontBoundingBoxDescent || fs * .2;
        x.fillStyle = '#fff'; x.fillText(w.textContent, 0, (r.height - asc - des) / 2 + asc);
        const d = x.getImageData(0, 0, c.width, c.height).data, step = Math.max(3, Math.round(fs / 30));
        const pal = wi ? [[255, 236, 160], [244, 182, 60]] : [[150, 255, 196], [40, 200, 110]];
        for (let y = 0; y < c.height; y += step) for (let xx = 0; xx < c.width; xx += step) if (d[(y * c.width + xx) * 4 + 3] > 140) {
          const k = y / c.height; out.push([r.left - s.left + xx, r.top - s.top + y, k, pal[0].map((v, i) => Math.round(v + (pal[1][i] - v) * k))]);
        }
      });
      return out;
    }
    const COL = k => { const a = [[255, 247, 214], [255, 212, 92], [255, 154, 60], [255, 79, 154]]; const f = Math.min(.999, Math.max(0, k)) * (a.length - 1), i = f | 0, u = f - i; return a[i].map((v, j) => Math.round(v + (a[i + 1][j] - v) * u)); };
    function fit() { const dpr = Math.min(devicePixelRatio || 1, 2), r = sec.getBoundingClientRect(); W = r.width; H = r.height; cv.width = W * dpr; cv.height = H * dpr; g.setTransform(dpr, 0, 0, dpr, 0, 0); }
    const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    function start() {
      fit(); pts = sample(); if (!pts.length) { sec.classList.add('formed'); return; }
      sec.classList.add('forming');
      const xs = [W * .3, W * .5, W * .7], ty = pts.reduce((a, p) => a + p[1], 0) / pts.length - 20;
      rockets = xs.map((x, i) => ({ x: x + (Math.random() - .5) * 40, y: H + 10, tx: x, ty, d: 300 + i * 260, b: false }));
      stars = pts.map(p => ({ r: rockets[Math.min(2, Math.floor(p[0] / W * 3))], tx: p[0], ty: p[1], k: p[2], col: p[3], a: Math.random() * 6.283, sp: .6 + Math.random() * 1.4, ph: Math.random() * 6.283, x: 0, y: 0 }));
      t0 = performance.now(); phase = 1; cancelAnimationFrame(raf); raf = requestAnimationFrame(frame);
    }
    function frame(now) {
      const t = now - t0; g.clearRect(0, 0, W, H); g.globalCompositeOperation = 'lighter';
      rockets.forEach(r => {
        const u = Math.min(1, Math.max(0, (t - r.d) / 900)); if (u <= 0 || r.b) return;
        const y = r.y + (r.ty - r.y) * (1 - Math.pow(1 - u, 2.2)), x = r.x + (r.tx - r.x) * u;
        for (let k = 0; k < 10; k++) { g.fillStyle = `rgba(255,${190 - k * 10},${120 - k * 8},${.9 - k * .08})`; g.beginPath(); g.arc(x + (Math.random() - .5) * 2, y + k * 7, 2.2 - k * .15, 0, 7); g.fill(); }
        if (u >= 1) { r.b = true; r.bt = t; }
      });
      let settled = 0;
      stars.forEach(s => {
        const r = s.r; if (!r.b) return; const u = (t - r.bt) / 1700;
        const rr = Math.min(W, H) * .22 * s.sp * Math.sqrt(s.sp / 2);
        const ox = r.tx + Math.cos(s.a) * rr * Math.min(1, u * 3), oy = r.ty + Math.sin(s.a) * rr * Math.min(1, u * 3) + u * u * 30;
        const k = ease(Math.min(1, Math.max(0, (u - .28) / .72)));
        s.x = ox + (s.tx - ox) * k; s.y = oy + (s.ty - oy) * k; if (k >= 1) settled++;
        const c = s.col ? s.col.map(v => Math.min(255, v + (255 - v) * .3)) : COL(s.k), tw = k >= 1 ? .55 + .45 * Math.sin(now / 170 * s.sp + s.ph) : 1;
        g.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${.9 * tw})`; g.beginPath(); g.arc(s.x, s.y, k >= 1 ? 1.7 : 2.2, 0, 7); g.fill();
        if (k < 1) { g.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},.18)`; g.beginPath(); g.arc(s.x, s.y, 5, 0, 7); g.fill(); }
      });
      rockets.forEach(r => { if (r.b) { const u = (t - r.bt) / 260; if (u < 1) { g.fillStyle = `rgba(255,240,210,${.35 * (1 - u)})`; g.beginPath(); g.arc(r.tx, r.ty, 90 * u + 10, 0, 7); g.fill(); } } });
      if (settled === stars.length && phase === 1) { phase = 2; t0f = now; sec.classList.remove('forming'); sec.classList.add('formed'); }
      if (phase === 2) { const f = Math.min(1, (now - t0f) / 1400); cv.style.opacity = String(1 - f); if (f >= 1) { g.clearRect(0, 0, W, H); cv.style.opacity = '1'; phase = 0; return; } }
      raf = requestAnimationFrame(frame);
    }
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => setTimeout(start, 600));
    addEventListener('resize', () => { if (phase === 0) return; cancelAnimationFrame(raf); phase = 0; g.clearRect(0, 0, W, H); sec.classList.remove('forming'); sec.classList.add('formed'); });
  })();

  /* ---------- Hero video: play while on screen, still frame for reduced motion ---------- */
  const heroBg = $('#heroBg');
  if (reduce) { heroBg.removeAttribute('autoplay'); heroBg.pause(); }
  else new IntersectionObserver(e => { if (e[0].isIntersecting) heroBg.play().catch(() => {}); else heroBg.pause(); }).observe(heroBg);

  /* Animate a small sky on a timer while it is on screen */
  function animateTile(s, kind, pal, yFactor, chance, hoverEl) {
    const r = RATE[kind] || 1300;
    if (reduce) { const { W, H } = s.size(); for (let i = 0; i < 24; i++) { play(s, kind, pal, W / 2, H * yFactor, i); s.step(); } return; }
    s.run();
    let t = 0, hov = false;
    if (hoverEl) { hoverEl.addEventListener('pointerenter', () => { hov = true; }); hoverEl.addEventListener('pointerleave', () => { hov = false; }); }
    setInterval(() => { if (!s.visible) return; const { W, H } = s.size(); if (hov || r < 200 || Math.random() < chance) play(s, kind, pal, W / 2, H * yFactor, t++); }, r);
  }

  /* Category tiles rest on a still of their effect and only animate while hovered or focused */
  /* Ground effects start above the tile's label; aerial ones burst in the upper half */
  const baseY = (kind, H) => ['fountain', 'mine', 'roman', 'smoke'].includes(kind) ? H * .5 : H * .7;
  function restFrame(s, kind, pal) {
    s.fit(); const { W, H } = s.size(); if (!W) return;
    const y = baseY(kind, H);
    if (kind === 'rocket') { s.rocket(W / 2, y, pal); s.still(80); }
    else if (RATE[kind]) for (let i = 0; i < 24; i++) { play(s, kind, pal, W / 2, y, i); s.step(); }
    else { play(s, kind, pal, W / 2, y, 0); s.still(22); }
  }
  const resting = [];
  function fireOnHover(s, kind, pal, el) {
    const rest = () => restFrame(s, kind, pal);
    resting.push(rest); requestAnimationFrame(rest);
    if (reduce) return;
    let timer = 0, settle = 0, t = 0;
    const r = RATE[kind] || 900;
    const start = () => {
      clearTimeout(settle); if (timer) return;
      s.paused = false; s.run();
      const fire = () => { const { W, H } = s.size(); play(s, kind, pal, W / 2, baseY(kind, H), t++); };
      fire(); timer = setInterval(fire, Math.max(r, 40));
    };
    const stop = () => {
      clearInterval(timer); timer = 0;
      settle = setTimeout(() => { s.paused = true; rest(); }, 1600);
    };
    el.addEventListener('pointerenter', start); el.addEventListener('pointerleave', stop);
    el.addEventListener('focus', start); el.addEventListener('blur', stop);
  }
  let restTimer;
  addEventListener('resize', () => { clearTimeout(restTimer); restTimer = setTimeout(() => resting.forEach(f => f()), 200); });

  /* ---------- Categories ---------- */
  const state = { cat: 'All', q: '', sort: 'pop', all: false };
  const mega = $('#mega'), foot = $('#footCats'), catsEl = $('#cats');
  CATS.forEach(([name, desc, col, kind, pal, dark]) => {
    const n = ITEMS.filter(it => name === 'Low noise' ? it.low : it.k === name).length;
    const b = document.createElement('button'); b.type = 'button'; b.className = 'cat'; b.style.setProperty('--c', col);
    b.innerHTML = `${PHOTOS[name] ? `<img src="${esc(PHOTOS[name])}" alt="" loading="lazy">` : ''}<em>${n ? `${n} product${n > 1 ? 's' : ''}` : 'Coming soon'}</em><b>${esc(name)}</b><span>${esc(desc)}</span>`;
    b.addEventListener('click', () => pickCat(name));
    catsEl.appendChild(b);
    const a = document.createElement('a'); a.href = '#shop'; a.innerHTML = `<i style="background:${col}"></i>${esc(name)}`;
    a.addEventListener('click', e => { e.preventDefault(); pickCat(name); }); mega.appendChild(a);
    const li = document.createElement('li'); li.innerHTML = `<a href="#shop">${esc(name)}</a>`;
    li.firstChild.addEventListener('click', e => { e.preventDefault(); pickCat(name); }); foot.appendChild(li);
  });
  function pickCat(n) { state.cat = n; state.all = true; render(); closeMenu(); scrollToEl($('#shop')); }
  $$('[data-cat]').forEach(a => a.addEventListener('click', () => { state.cat = a.dataset.cat; state.all = true; render(); closeMenu(); }));

  /* ---------- Products ---------- */
  const STK = { ok: ['In stock', 'ok'], few: ['Only a few left', 'few'], pre: ['Pre-order, ships 15 Dec', 'pre'], out: ['Sold out', 'out'] };
  const CAKE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 2v5M12 17v5M2 12h5M17 12h5M5 5l3.5 3.5M15.5 15.5L19 19M19 5l-3.5 3.5M8.5 15.5L5 19"/></svg>';
  const BOX_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 8l9-5 9 5v9l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v9"/></svg>';
  const PRODUCTS = {};
  ITEMS.forEach(it => { PRODUCTS[it.id] = it; });

  const grid = $('#grid');
  ITEMS.forEach(it => {
    it.off = it.was ? Math.round((1 - it.pv / it.was) * 100) : 0;
    const el = document.createElement('article'); el.className = 'card'; it.el = el;
    const flag = it.pro ? '<span class="flag lic">Licensed only</span>' : it.bogo ? '<span class="flag bogo">Buy 1 get 1 free</span>' : it.off ? `<span class="flag">${it.off}% off</span>` : '';
    const btn = it.pro ? '<button class="add q" type="button">Request a quote</button>'
      : it.st === 'out' ? '<button class="add" type="button" disabled>Sold out</button>'
      : `<button class="add" type="button">${it.st === 'pre' ? 'Pre-order' : 'Add to cart'}</button>`;
    el.innerHTML = `<div class="art"><img src="${esc(photoFor(it))}" alt="" loading="lazy">${flag}${it.low ? '<span class="lown">Low noise</span>' : ''}</div>
      <div class="body"><h3>${esc(it.n)}</h3><dl class="specs"><div><dt>Shots</dt><dd>${esc(it.q)}</dd></div><div><dt>Duration</dt><dd>${esc(it.d)}</dd></div><div><dt>Keep back</dt><dd>${esc(it.x)}</dd></div></dl>
      <p class="stock ${STK[it.st][1]}">${STK[it.st][0]}</p>
      <div class="buyrow"><span class="p ${it.pro ? 'req' : ''}">${it.was ? `<s>${fmt(it.was)}</s>` : ''}${it.pro ? 'Price on request' : fmt(it.pv)}</span>${btn}</div></div>`;
    grid.appendChild(el);
    const add = el.querySelector('.add');
    add.addEventListener('click', () => {
      if (it.pro) {
        setType('Wholesale order');
        $('#f-msg').value = `Licensed order: ${it.n}. Licence number: `;
        scrollToEl($('#contact'));
        setTimeout(() => $('#f-msg').focus({ preventScroll: true }), reduce ? 0 : 500);
        toast('Add your licence number and we will send trade prices');
      } else addToCart(it.id, add);
    });
  });
  const empty = document.createElement('div'); empty.className = 'empty'; empty.hidden = true;
  empty.innerHTML = 'Nothing matches that search. <button class="btn btn-ink" type="button" style="margin-left:8px;padding:10px 14px" id="clearF">Clear filters</button>';
  grid.appendChild(empty);
  $('#clearF').addEventListener('click', () => { state.cat = 'All'; state.q = ''; $('#q').value = ''; $('#q2').value = ''; render(); });

  const pills = $('#pills');
  ['All', ...CATS.map(c => c[0])].forEach(n => {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'pill'; b.textContent = n;
    b.addEventListener('click', () => { state.cat = n; state.all = n !== 'All' || state.all; render(); });
    pills.appendChild(b);
  });

  function render() {
    const q = state.q.trim().toLowerCase();
    const match = it => (state.cat === 'All' || (state.cat === 'Low noise' ? it.low : it.k === state.cat)) && (!q || (it.n + ' ' + it.k).toLowerCase().includes(q));
    const list = ITEMS.filter(match).sort((a, b) =>
      state.sort === 'asc' ? ((a.pro ? 1 : 0) - (b.pro ? 1 : 0) || a.pv - b.pv)
        : state.sort === 'desc' ? ((a.pro ? 1 : 0) - (b.pro ? 1 : 0) || b.pv - a.pv)
          : state.sort === 'off' ? b.off - a.off : b.pop - a.pop);
    const limit = (state.all || q || state.cat !== 'All') ? 99 : 8;
    ITEMS.forEach(it => { it.el.hidden = true; });
    list.slice(0, limit).forEach(it => { it.el.hidden = false; grid.insertBefore(it.el, empty); });
    empty.hidden = list.length > 0;
    $('#showAll').hidden = list.length <= limit; $('#showAll').textContent = `Show all ${list.length} products`;
    pills.querySelectorAll('.pill').forEach(b => b.setAttribute('aria-pressed', b.textContent === state.cat));
    $('#status').textContent = `Showing ${Math.min(limit, list.length)} of ${list.length} products` + (state.cat !== 'All' ? ` in ${state.cat}` : '') + (q ? ` matching "${state.q.trim()}"` : '');
  }
  $('#showAll').addEventListener('click', () => { state.all = true; render(); });
  $('#sort').addEventListener('change', e => { state.sort = e.target.value; render(); });
  ['#q', '#q2'].forEach(id => $(id).addEventListener('input', e => {
    state.q = e.target.value; render();
    if (state.q.length === 1) scrollToEl($('#shop'));
  }));
  render();

  function watch(it) {
    const s = it.s;
    if (['fountain', 'mine', 'roman', 'smoke', 'wheel'].includes(it.fx)) {
      let t = 0; const n = it.fx === 'roman' || it.fx === 'mine' ? 6 : 70;
      const go = () => {
        const { W, H } = s.size(); play(s, it.fx, it.c, W / 2, H * .9, t); if (it.fx === 'fountain') play(s, it.fx, it.c, W / 2, H * .9, t);
        if (reduce) s.step();
        if (++t < n) reduce ? go() : setTimeout(go, RATE[it.fx] > 200 ? 350 : 40);
      };
      go();
    } else for (let i = 0; i < 3; i++) setTimeout(() => {
      const { W, H } = s.size();
      if (it.fx === 'rocket') s.rocket(W * (.3 + i * .2), H * .9, it.c); else s.fx[it.fx](W * (.3 + i * .2), H * (.3 + Math.random() * .15), PAL[it.c], .7);
      if (reduce) s.still(30);
    }, reduce ? 0 : i * 380);
  }

  /* ---------- Cart ---------- */
  let cart = store.get('noor-cart', {});            // { id: qty }
  let codeOn = store.get('noor-code', false);
  const buyer = store.get('noor-buyer', {});
  Object.keys(cart).forEach(id => { if (!PRODUCTS[id] || PRODUCTS[id].pro) delete cart[id]; });

  const count = () => Object.values(cart).reduce((a, b) => a + b, 0);

  /* Totals. Buy one get one: across all offer cakes, every second unit (cheapest first) is free. */
  function totals() {
    const lines = Object.entries(cart).map(([id, qty]) => ({ p: PRODUCTS[id], qty, id }));
    const subtotal = lines.reduce((a, l) => a + l.p.pv * l.qty, 0);
    const units = [];
    lines.forEach(l => { if (l.p.bogo) for (let i = 0; i < l.qty; i++) units.push(l.p.pv); });
    units.sort((a, b) => b - a);
    let bogo = 0; for (let i = 1; i < units.length; i += 2) bogo += units[i];
    const afterBogo = subtotal - bogo;
    const code = codeOn ? Math.round(afterBogo * PROMO.percent / 100) : 0;
    const total = afterBogo - code;
    return { lines, subtotal, bogo, code, total, gift: total >= PROMO.freeGiftAt, freeUnits: Math.floor(units.length / 2) };
  }

  function saveCart() { store.set('noor-cart', cart); store.set('noor-code', codeOn); }

  function updateBadge(bump) {
    const n = count(), b = $('#cartBtn');
    $('#cartN').textContent = n;
    b.setAttribute('aria-label', `Open cart, ${n} item${n === 1 ? '' : 's'}`);
    if (bump && !reduce) { b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump'); }
  }

  function addToCart(id, btn) {
    cart[id] = (cart[id] || 0) + 1; saveCart(); updateBadge(true); renderCart();
    const p = PRODUCTS[id];
    if (!p.bogo) toast(`${p.n} added to your cart`);
    else toast(cakeUnits() % 2 === 0 ? `${p.n} added. Your free cake is applied.` : `${p.n} added. Add one more offer cake and the cheaper one is free.`);
    if (btn) { const old = btn.textContent; btn.textContent = 'Added'; btn.classList.add('in'); setTimeout(() => { btn.textContent = old; btn.classList.remove('in'); }, 1400); }
  }
  const cakeUnits = () => Object.entries(cart).reduce((a, [id, q]) => a + (PRODUCTS[id].bogo ? q : 0), 0);

  function setQty(id, q) {
    if (q <= 0) delete cart[id]; else cart[id] = Math.min(99, q);
    saveCart(); updateBadge(false); renderCart();
  }

  const body = $('#cartBody'), foot2 = $('#cartFoot');
  function renderCart() {
    const t = totals();
    if (!t.lines.length) {
      body.innerHTML = `<div class="d-empty"><b>Your cart is empty</b><p>Pick a cake, a box of sparklers or a pack of rockets.</p><button class="btn btn-hot" type="button" data-go="#shop">Browse fireworks</button></div>`;
      foot2.innerHTML = '';
      return;
    }
    const toGift = Math.max(0, PROMO.freeGiftAt - t.total);
    body.innerHTML = `
      <ul class="lines">${t.lines.map(l => `
        <li class="line">
          <span class="sw" style="--bg:${l.p.bg && l.p.bg.startsWith('#') ? l.p.bg : 'var(--violet)'}">${l.p.combo ? BOX_ICON : CAKE_ICON}</span>
          <div><h3>${esc(l.p.n)}</h3><p class="meta">${fmt(l.p.pv)} each${l.p.st === 'pre' ? ', pre-order' : ''}</p>
            <div class="qty"><button type="button" data-dec="${l.id}" aria-label="Remove one ${esc(l.p.n)}">−</button><output aria-live="polite" aria-label="Quantity">${l.qty}</output><button type="button" data-inc="${l.id}" aria-label="Add one more ${esc(l.p.n)}">+</button></div></div>
          <div><p class="amt">${fmt(l.p.pv * l.qty)}</p><button class="rm" type="button" data-rm="${l.id}">Remove</button></div>
        </li>`).join('')}
        ${t.gift ? `<li class="line"><span class="sw" style="--bg:var(--saffron)">${CAKE_ICON}</span><div><h3>${esc(PROMO.freeGift)}</h3><p class="free">Free with orders over ${fmt(PROMO.freeGiftAt)}</p></div><p class="amt">Free</p></li>` : ''}
      </ul>
      ${t.gift ? '' : `<div class="gift">Add ${fmt(toGift)} more for a ${esc(PROMO.freeGift.toLowerCase())}.<div class="meter" aria-hidden="true"><i style="width:${Math.min(100, t.total / PROMO.freeGiftAt * 100)}%"></i></div></div>`}
      <form class="code" id="codeForm"><label class="sr" for="codeIn">Discount code</label><input id="codeIn" placeholder="Discount code" autocomplete="off" value="${codeOn ? PROMO.code : ''}" ${codeOn ? 'disabled' : ''}><button class="btn btn-ink" type="submit">${codeOn ? 'Remove' : 'Apply'}</button></form>
      <p class="code-msg ok" id="codeMsg" ${codeOn ? '' : 'hidden'}>${codeOn ? `${PROMO.code} applied: ${PROMO.percent}% off` : ''}</p>
      <dl class="sum">
        <div><dt>Subtotal</dt><dd>${fmt(t.subtotal)}</dd></div>
        ${t.bogo ? `<div class="save"><dt>Buy 1 get 1 free (${t.freeUnits} cake${t.freeUnits > 1 ? 's' : ''})</dt><dd>− ${fmt(t.bogo)}</dd></div>` : ''}
        ${t.code ? `<div class="save"><dt>${PROMO.code} (${PROMO.percent}% off)</dt><dd>− ${fmt(t.code)}</dd></div>` : ''}
        <div class="total"><dt>Total</dt><dd>${fmt(t.total)}</dd></div>
        <div class="note"><dt>Delivery</dt><dd>Confirmed on WhatsApp by city</dd></div>
        <div class="note"><dt>Advance to pay</dt><dd>${fmt(Math.ceil(t.total / 2))} (half)</dd></div>
      </dl>
      <form class="checkout" id="checkout" novalidate>
        <h3>Delivery details</h3>
        <div class="f"><label for="c-name">Full name</label><input id="c-name" autocomplete="name" required value="${esc(buyer.name || '')}" aria-describedby="c-name-err"><p class="err" id="c-name-err" hidden>Add your name.</p></div>
        <div class="row2">
          <div class="f"><label for="c-phone">Phone</label><input id="c-phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="03xx xxxxxxx" required value="${esc(buyer.phone || '')}" aria-describedby="c-phone-err"><p class="err" id="c-phone-err" hidden>Add a phone number, for example 0300 1234567.</p></div>
          <div class="f"><label for="c-city">City</label><select id="c-city" required>${CITIES.map(c => `<option${buyer.city === c ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select></div>
        </div>
        <div class="f"><label for="c-addr">Delivery address</label><textarea id="c-addr" autocomplete="street-address" rows="2" style="min-height:70px" required aria-describedby="c-addr-err" placeholder="House, street, area">${esc(buyer.addr || '')}</textarea><p class="err" id="c-addr-err" hidden>Add the address we should deliver to.</p></div>
        <label class="check"><input type="checkbox" id="c-age" required aria-describedby="c-age-err"> I am 18 or older and will follow the safety label on every item.</label>
        <p class="err" id="c-age-err" hidden>Fireworks are sold to adults only. Tick the box to continue.</p>
      </form>`;
    foot2.innerHTML = `<button class="btn btn-wa" type="submit" form="checkout"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><use href="#i-wa"/></svg>Send order on WhatsApp</button><small>We reply with delivery charge and payment details. Nothing is charged online.</small>`;
  }

  /* Cart events (delegated, so they survive re-renders) */
  body.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.inc) { setQty(b.dataset.inc, cart[b.dataset.inc] + 1); focusAgain(`[data-inc="${b.dataset.inc}"]`); }
    else if (b.dataset.dec) { const id = b.dataset.dec; setQty(id, cart[id] - 1); focusAgain(cart[id] ? `[data-dec="${id}"]` : null); }
    else if (b.dataset.rm) { const p = PRODUCTS[b.dataset.rm]; setQty(b.dataset.rm, 0); toast(`${p.n} removed`); focusAgain(null); }
    else if (b.dataset.go) { closeCart(); scrollToEl($(b.dataset.go)); }
  });
  function focusAgain(sel) { const el = sel && body.querySelector(sel); (el || $('#cartClose')).focus(); }
  body.addEventListener('input', e => {
    if (['c-name', 'c-phone', 'c-city', 'c-addr'].includes(e.target.id)) {
      store.set('noor-buyer', { name: $('#c-name').value, phone: $('#c-phone').value, city: $('#c-city').value, addr: $('#c-addr').value });
      Object.assign(buyer, store.get('noor-buyer', {}));
      clearErr(e.target);
    }
    if (e.target.id === 'c-age') clearErr(e.target);
  });
  body.addEventListener('submit', e => {
    e.preventDefault();
    if (e.target.id === 'codeForm') {
      const inp = $('#codeIn'), msg = $('#codeMsg');
      if (codeOn) { codeOn = false; saveCart(); renderCart(); $('#codeIn').focus(); return; }
      if (inp.value.trim().toUpperCase() === PROMO.code) { codeOn = true; saveCart(); renderCart(); toast(`${PROMO.code} applied`); $('#codeForm button').focus(); }
      else { msg.hidden = false; msg.className = 'code-msg bad'; msg.textContent = inp.value.trim() ? `"${inp.value.trim()}" is not a valid code. Try ${PROMO.code}.` : 'Type a code first.'; inp.focus(); }
    }
    if (e.target.id === 'checkout') sendOrder();
  });

  const phoneOk = v => v.replace(/\D/g, '').length >= 10;
  function showErr(input, show) { input.setAttribute('aria-invalid', show ? 'true' : 'false'); const m = document.getElementById(input.id + '-err'); if (m) m.hidden = !show; }
  function clearErr(input) { if (input.getAttribute('aria-invalid') === 'true') showErr(input, false); }

  function sendOrder() {
    const name = $('#c-name'), phone = $('#c-phone'), city = $('#c-city'), addr = $('#c-addr'), age = $('#c-age');
    const bad = [];
    showErr(name, !name.value.trim()); if (!name.value.trim()) bad.push(name);
    showErr(phone, !phoneOk(phone.value)); if (!phoneOk(phone.value)) bad.push(phone);
    showErr(addr, !addr.value.trim()); if (!addr.value.trim()) bad.push(addr);
    showErr(age, !age.checked); if (!age.checked) bad.push(age);
    if (bad.length) { bad[0].focus(); return; }
    const t = totals();
    const L = [`Assalam o Alaikum ${BIZ.name}, I would like to order:`, ''];
    t.lines.forEach(l => L.push(`• ${l.qty} × ${l.p.n} = ${fmt(l.p.pv * l.qty)}${l.p.st === 'pre' ? ' (pre-order)' : ''}`));
    if (t.gift) L.push(`• ${PROMO.freeGift} = Free`);
    L.push('', `Subtotal: ${fmt(t.subtotal)}`);
    if (t.bogo) L.push(`Buy 1 get 1 free: −${fmt(t.bogo)}`);
    if (t.code) L.push(`${PROMO.code} (${PROMO.percent}% off): −${fmt(t.code)}`);
    L.push(`Total before delivery: ${fmt(t.total)}`, '');
    L.push(`Name: ${name.value.trim()}`, `Phone: ${phone.value.trim()}`, `City: ${city.value}`, `Address: ${addr.value.trim()}`, '', 'I confirm I am 18 or older.');
    openWhatsApp(L.join('\n'));
    toast('WhatsApp is open with your order. Press send there to place it.');
  }

  /* Drawer open/close with focus handling */
  const drawer = $('#cart'), scrim = $('#scrim'), cartBtn = $('#cartBtn');
  let lastFocus = null;
  function openCart() {
    lastFocus = document.activeElement; renderCart();
    drawer.hidden = false; scrim.hidden = false; document.body.classList.add('locked');
    requestAnimationFrame(() => { drawer.classList.add('show'); scrim.classList.add('show'); });
    $('#cartClose').focus();
  }
  function closeCart() {
    drawer.classList.remove('show'); scrim.classList.remove('show'); document.body.classList.remove('locked');
    setTimeout(() => { drawer.hidden = true; scrim.hidden = true; }, reduce ? 0 : 300);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }
  cartBtn.addEventListener('click', openCart);
  $('#cartClose').addEventListener('click', closeCart);
  scrim.addEventListener('click', closeCart);
  document.addEventListener('keydown', e => {
    if (drawer.hidden) return;
    if (e.key === 'Escape') closeCart();
    if (e.key === 'Tab') {
      const f = [...drawer.querySelectorAll('button:not([disabled]),input:not([disabled]),select,textarea,a[href]')].filter(el => el.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  updateBadge(false);

  /* ---------- Reviews: shown only when real figures are set in config.js ---------- */
  const RV = window.NOOR.reviews;
  if (RV && RV.sources && RV.sources.length) {
    const el = $('#reviews');
    el.innerHTML = `<div class="wrap rv-in">${RV.customers ? `<p class="rv-big"><b>${esc(RV.customers)}</b> happy customers</p>` : ''}<ul class="rv-list">${RV.sources.map(r => `<li><a href="${esc(r.url || '#')}" target="_blank" rel="noopener"><b>${esc(r.name)}</b><span class="rv-stars" aria-hidden="true" style="--r:${Math.max(0, Math.min(5, r.rating))}"></span><span>Rated ${esc(r.rating)} of 5${r.count ? ` from ${esc(r.count)} reviews` : ''}</span></a></li>`).join('')}</ul></div>`;
    el.hidden = false;
  }
  $('#orderWa').href = waLink(`Assalam o Alaikum ${BIZ.name}, I would like help choosing fireworks.`);

  /* ---------- 3D: cards lean toward the pointer; picture panels turn flat as they scroll in ---------- */
  if (!reduce && matchMedia('(hover: hover) and (pointer: fine)').matches) {
    const tiltable = '.card, .offer, .cat';
    document.addEventListener('pointermove', e => {
      const el = e.target.closest(tiltable); if (!el) return;
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      el.style.setProperty('--rx', `${(-y * 8).toFixed(2)}deg`); el.style.setProperty('--ry', `${(x * 10).toFixed(2)}deg`);
      el.classList.add('tilting');
    }, { passive: true });
    document.addEventListener('pointerout', e => {
      const el = e.target.closest(tiltable); if (el && !el.contains(e.relatedTarget)) { el.classList.remove('tilting'); el.style.removeProperty('--rx'); el.style.removeProperty('--ry'); }
    });
  }
  if (!reduce) {
    const panels = $$('.zig-media');
    panels.forEach(p => p.classList.add('turn'));
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .2 });
    panels.forEach(p => io.observe(p));
  }

  /* ---------- Misc ---------- */
  $('#copyCode').addEventListener('click', e => {
    const b = e.currentTarget;
    const done = () => { b.textContent = 'Copied'; setTimeout(() => { b.textContent = 'Copy code'; }, 1600); };
    if (navigator.clipboard) navigator.clipboard.writeText(PROMO.code).then(done).catch(selectCode); else selectCode();
    function selectCode() { const r = document.createRange(); r.selectNodeContents($('#codeTxt')); getSelection().removeAllRanges(); getSelection().addRange(r); toast('Code selected. Copy it from here.'); }
  });
  const nav = $('#mainNav'), mb = $('#menuBtn');
  mb.addEventListener('click', () => { const o = nav.classList.toggle('open'); mb.setAttribute('aria-expanded', o); });
  function closeMenu() { nav.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); }
  nav.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));

  function setType(v) { const s = $('#f-type'); [...s.options].forEach(o => { if (o.text === v) s.value = o.value; }); }
  $$('[data-type]').forEach(a => a.addEventListener('click', () => setType(a.dataset.type)));

  /* Contact form: validates, then opens WhatsApp with the message written out */
  const enq = $('#enq');
  enq.addEventListener('input', e => clearErr(e.target));
  enq.addEventListener('submit', e => {
    e.preventDefault();
    const n = $('#f-name'), p = $('#f-phone');
    showErr(n, !n.value.trim()); showErr(p, !phoneOk(p.value));
    if (!n.value.trim()) return n.focus();
    if (!phoneOk(p.value)) return p.focus();
    const date = $('#f-date').value, msg = $('#f-msg').value.trim();
    const text = [`Assalam o Alaikum ${BIZ.name},`, '', `I'm interested in: ${$('#f-type').value}`, date ? `Date: ${date}` : '', msg ? `Details: ${msg}` : '', '', `Name: ${n.value.trim()}`, `Phone: ${p.value.trim()}`].filter((l, i, a) => l || a[i - 1]).join('\n');
    openWhatsApp(text);
    let d = enq.querySelector('.sent');
    if (!d) { d = document.createElement('div'); d.className = 'sent'; d.setAttribute('role', 'status'); enq.querySelector('.f-foot').before(d); }
    d.textContent = `Thanks, ${n.value.trim().split(' ')[0]}. WhatsApp is open with your message. Press send there and we reply within one working day.`;
  });
})();
