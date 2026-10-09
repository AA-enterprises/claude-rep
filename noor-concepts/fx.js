/*
  Fireworks engine. Draws on transparent canvases.
  One shared animation loop drives every sky, and a sky only animates while it is on screen.
*/
(function () {
  const PAL = {
    gold: ['#ffd27a', '#ffb000', '#fff1c8'],
    silver: ['#ffffff', '#e3e9ff', '#c4d0ff'],
    pink: ['#ff2e88', '#ff8fc0', '#ffd1e6'],
    green: ['#3cf09a', '#b9ffd9', '#ffffff'],
    violet: ['#b28cff', '#e0ccff', '#ff9ee6'],
    blue: ['#4fb6ff', '#bfe6ff', '#ffffff'],
    red: ['#ff3b3b', '#ff8a6a', '#ffe0d0'],
    flag: ['#1f9a5a', '#38c27a', '#f2f5f3'],
    reveal: ['#ff6fb0', '#ff9ccb', '#7ec8ff'],
    mix: ['#ff2e88', '#ffb000', '#4fb6ff', '#3cf09a', '#b28cff']
  };
  const RANDOM_PALS = Object.keys(PAL).filter(k => k !== 'flag' && k !== 'reveal');
  const R = (a, b) => a + Math.random() * (b - a);
  const P = a => a[Math.random() * a.length | 0];

  /* Shared loop */
  const skies = new Set();
  let looping = false;
  let pageVisible = !document.hidden;
  document.addEventListener('visibilitychange', () => { pageVisible = !document.hidden; });
  function tick() {
    if (pageVisible) skies.forEach(s => { if (s.visible && !s.paused) { s.step(); s.onframe && s.onframe(); } });
    requestAnimationFrame(tick);
  }
  const io = new IntersectionObserver(entries => entries.forEach(e => { e.target.__sky.visible = e.isIntersecting; }), { rootMargin: '80px' });
  let resizeTimer;
  addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => skies.forEach(s => s.fit()), 120); });

  function makeSky(cv, fade = 0.2) {
    const ctx = cv.getContext('2d');
    let W = 0, H = 0;
    const rk = [], sp = [];
    const S = (x, y, vx, vy, o) => sp.push(Object.assign({ x, y, vx, vy, l: 1, d: R(.008, .016), g: .045, dr: .985, z: 1.6, c: '#fff', t: [] }, o));

    const fx = {
      peony(x, y, c, s) { const n = 90 * s; for (let i = 0; i < n; i++) { const a = i / n * 6.283, v = R(2.6, 3.2) * s; S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(c) }); } },
      chrysanthemum(x, y, c, s) { for (let i = 0; i < 110 * s; i++) { const a = R(0, 6.283), v = R(.5, 3.4) * s; S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(c), d: R(.007, .012), tl: 6 }); } },
      willow(x, y, c, s) { for (let i = 0; i < 70 * s; i++) { const a = R(0, 6.283), v = R(1, 2.6) * s; S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(PAL.gold), d: R(.004, .006), g: .03, dr: .97, tl: 14, z: 1.3 }); } },
      crossette(x, y, c, s) { for (let i = 0; i < 8; i++) { const a = i / 8 * 6.283; S(x, y, Math.cos(a) * 2.4 * s, Math.sin(a) * 2.4 * s, { c: P(c), d: .025, split: c, tl: 4 }); } },
      ring(x, y, c, s) { const n = 60 * s, k = R(.3, .6), r = R(0, 3.14); for (let i = 0; i < n; i++) { const a = i / n * 6.283, vx = Math.cos(a) * 3 * s, vy = Math.sin(a) * 3 * s * k; S(x, y, vx * Math.cos(r) - vy * Math.sin(r), vx * Math.sin(r) + vy * Math.cos(r), { c: P(c), d: .013 }); } },
      crackle(x, y, c, s) { for (let i = 0; i < 80 * s; i++) { const a = R(0, 6.283), v = R(1, 3) * s; S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(PAL.silver), strobe: 1, d: R(.01, .018), z: 1.8 }); } }
    };

    const api = {
      fx, cv, paused: false, visible: false,
      fit() {
        const d = Math.min(devicePixelRatio || 1, 2), r = cv.getBoundingClientRect();
        W = r.width; H = r.height; cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0);
      },
      size: () => ({ W, H }),
      launch(tx, ty, type, pal, s = 1) {
        type = type || P(Object.keys(fx));
        const c = PAL[pal] || PAL[P(RANDOM_PALS)];
        rk.push({ x: tx + R(-30, 30), y: H, tx, ty, vy: -Math.sqrt(2 * .06 * Math.max(40, H - ty)) * 1.02, type, c, s });
      },
      fountain(x, y, c, n = 10) { for (let i = 0; i < n; i++) { const a = -1.5708 + R(-.22, .22), v = R(2.2, 4.2); S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(PAL[c]), d: R(.018, .03), g: .07, z: 1.2, tl: 3 }); } },
      mine(x, y, c) { for (let i = 0; i < 24; i++) { const a = -1.5708 + R(-.7, .7), v = R(2.5, 5); S(x, y, Math.cos(a) * v, Math.sin(a) * v, { c: P(PAL[c]), d: R(.015, .025), g: .07, z: 1.8, tl: 4 }); } },
      roman(x, y, c) { S(x, y, R(-.3, .3), -R(4.2, 5), { c: P(PAL[c]), d: .012, g: .06, z: 2.6, tl: 6 }); },
      rocket(x, y, c) { api.launch(x, y * .25 + R(0, y * .15), 'peony', c, .6); },
      wheel(x, y, c, t) { for (let i = 0; i < 4; i++) { const a = t * .25 + i * 1.57; S(x + Math.cos(a) * 10, y + Math.sin(a) * 10, -Math.sin(a) * 3, Math.cos(a) * 3, { c: P(PAL[c]), d: .04, g: .02, z: 1.4, tl: 3 }); } },
      smoke(x, y, c = 'flag') { for (let i = 0; i < 2; i++) S(x + R(-6, 6), y, R(-.4, .4), -R(.6, 1.2), { c: P(PAL[c]), d: R(.006, .01), g: -.004, dr: .99, z: R(9, 15), op: .3, soft: 1 }); },
      step() {
        ctx.globalCompositeOperation = 'destination-out'; ctx.fillStyle = `rgba(0,0,0,${fade})`; ctx.fillRect(0, 0, W, H);
        ctx.globalCompositeOperation = 'lighter';
        for (let i = rk.length - 1; i >= 0; i--) {
          const r = rk[i]; r.vy += .06; r.y += r.vy; r.x += (r.tx - r.x) * .02;
          ctx.fillStyle = 'rgba(255,230,180,.95)'; ctx.beginPath(); ctx.arc(r.x, r.y, 1.7, 0, 7); ctx.fill();
          if (Math.random() < .6) S(r.x, r.y + 2, R(-.3, .3), R(.2, .8), { c: '#ffb000', d: .05, z: 1, g: .02 });
          if (r.vy >= -.4 || r.y <= r.ty) { fx[r.type](r.x, r.y, r.c, r.s); sp.push({ flash: 1, x: r.x, y: r.y, l: 1 }); rk.splice(i, 1); }
        }
        for (let i = sp.length - 1; i >= 0; i--) {
          const p = sp[i];
          if (p.flash) { ctx.fillStyle = `rgba(255,240,220,${p.l * .1})`; ctx.beginPath(); ctx.arc(p.x, p.y, 36 * p.l, 0, 7); ctx.fill(); p.l -= .08; if (p.l <= 0) sp.splice(i, 1); continue; }
          if (p.tl) { p.t.push(p.x, p.y); if (p.t.length > p.tl * 2) p.t.splice(0, 2); }
          p.vx *= p.dr; p.vy = p.vy * p.dr + p.g; p.x += p.vx; p.y += p.vy; p.l -= p.d;
          if (p.split && p.l < .55) { fx.peony(p.x, p.y, p.split, .35); p.l = 0; }
          if (p.l <= 0) { sp.splice(i, 1); continue; }
          const a = p.strobe ? (Math.random() < .5 ? p.l : 0) : p.l;
          if (p.soft) ctx.globalCompositeOperation = 'source-over';
          ctx.globalAlpha = Math.max(0, a) * (p.op || 1); ctx.fillStyle = p.c;
          if (p.t.length > 2) { ctx.strokeStyle = p.c; ctx.lineWidth = p.z * .8; ctx.beginPath(); ctx.moveTo(p.t[0], p.t[1]); for (let k = 2; k < p.t.length; k += 2) ctx.lineTo(p.t[k], p.t[k + 1]); ctx.lineTo(p.x, p.y); ctx.stroke(); }
          ctx.beginPath(); ctx.arc(p.x, p.y, p.z, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
          if (p.soft) ctx.globalCompositeOperation = 'lighter';
        }
      },
      still(n) { for (let i = 0; i < n; i++) api.step(); },
      run() {
        skies.add(api);
        if (!looping) { looping = true; requestAnimationFrame(tick); }
      }
    };
    cv.__sky = api;
    api.fit();
    io.observe(cv);
    return api;
  }

  /* Ground effects stream; aerial ones burst */
  function play(s, kind, c, x, y, t) {
    if (kind === 'fountain') s.fountain(x, y, c);
    else if (kind === 'mine') s.mine(x, y, c);
    else if (kind === 'roman') s.roman(x, y, c);
    else if (kind === 'smoke') s.smoke(x, y, c);
    else if (kind === 'wheel') s.wheel(x, y * .82, c, t);
    else if (kind === 'rocket') s.rocket(x, y, c);
    else s.fx[kind](x, y * .45, PAL[c], .55);
  }
  const RATE = { fountain: 60, mine: 900, roman: 700, smoke: 90, wheel: 40, rocket: 1100 };

  window.Fireworks = { PAL, makeSky, play, RATE };
})();
