/* Mela pop theme: decorative only. Sparks follow the mouse, every click or tap pops a tiny firework,
   and a rainbow line along the top shows how far down the page you are. Nothing here changes content. */
(() => {
  const meter = document.createElement('div'); meter.className = 'fx-meter'; meter.setAttribute('aria-hidden', 'true');
  document.body.appendChild(meter);
  let mt = false;
  const meterUpdate = () => { mt = false; const h = document.documentElement.scrollHeight - innerHeight; meter.style.transform = `scaleX(${h > 0 ? Math.min(1, scrollY / h) : 0})`; };
  addEventListener('scroll', () => { if (!mt) { mt = true; requestAnimationFrame(meterUpdate); } }, { passive: true });
  meterUpdate();

  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const cv = document.createElement('canvas'); cv.id = 'fxSky'; cv.setAttribute('aria-hidden', 'true'); document.body.appendChild(cv);
  const g = cv.getContext('2d'), COLS = ['#ff4fa3', '#ffd23f', '#3be8ff', '#b8ff3c', '#fff7ea'];
  let W = 0, H = 0, dpr = 1, parts = [], raf = 0, last = 0;
  const fit = () => { dpr = Math.min(devicePixelRatio || 1, 2); W = innerWidth; H = innerHeight; cv.width = W * dpr; cv.height = H * dpr; g.setTransform(dpr, 0, 0, dpr, 0, 0); };
  fit(); addEventListener('resize', fit);
  const pick = () => COLS[(Math.random() * COLS.length) | 0];
  function spawn(x, y, n, speed, life, size) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 6.283, v = speed * (.35 + Math.random() * .65);
      parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, t: 0, life: life * (.7 + Math.random() * .5), s: size * (.6 + Math.random() * .6), c: pick() });
    }
    if (parts.length > 400) parts.splice(0, parts.length - 400);
    if (!raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
  }
  function tick(now) {
    const dt = Math.min(40, now - last) / 16.7; last = now;
    g.clearRect(0, 0, W, H); g.globalCompositeOperation = 'lighter';
    parts = parts.filter(p => (p.t += dt * 16.7) < p.life);
    parts.forEach(p => {
      p.vx *= .965; p.vy = p.vy * .965 + .06 * dt; p.x += p.vx * dt; p.y += p.vy * dt;
      const k = 1 - p.t / p.life; g.globalAlpha = k; g.fillStyle = p.c;
      g.beginPath(); g.arc(p.x, p.y, p.s * (.4 + k * .6), 0, 6.283); g.fill();
    });
    g.globalAlpha = 1;
    raf = parts.length ? requestAnimationFrame(tick) : 0;
    if (!raf) g.clearRect(0, 0, W, H);
  }
  /* a soft trail of sparks behind the mouse (not on touch screens) */
  let lx = 0, ly = 0;
  addEventListener('pointermove', e => {
    if (e.pointerType !== 'mouse') return;
    const d = Math.hypot(e.clientX - lx, e.clientY - ly); if (d < 14) return;
    lx = e.clientX; ly = e.clientY; spawn(lx, ly, 2, 1.2, 650, 2.2);
  }, { passive: true });
  /* click or tap anywhere: a little burst */
  addEventListener('pointerdown', e => spawn(e.clientX, e.clientY, 26, 4.2, 900, 2.6), { passive: true });
})();
