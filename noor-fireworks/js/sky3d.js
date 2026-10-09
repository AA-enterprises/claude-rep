/*
  3D fireworks sky for the hero.
  Shells launch from the shore at different depths and burst into true 3D spheres and rings.
  The camera sways on its own and follows the mouse (or the phone's tilt), so bursts
  turn in space; the water below reflects them and the skyline layers move at different speeds.
*/
(function () {
  function sky3d(cv, opts) {
    const PAL = opts.palettes;
    const reduce = opts.reduce;
    const ctx = cv.getContext('2d');
    let W = 0, H = 0, F = 600, HZ = 0;          // focal length and horizon line (px)
    const shells = [], sparks = [], stars = [];
    const cam = { yaw: 0, pitch: 0, ty: 0, tp: 0, h: 22 };
    const R = (a, b) => a + Math.random() * (b - a);
    const P = a => a[Math.random() * a.length | 0];
    const NAMES = ['gold', 'pink', 'violet', 'blue', 'green', 'silver', 'red'];

    function fit() {
      const d = Math.min(devicePixelRatio || 1, 2), r = cv.getBoundingClientRect();
      W = r.width; H = r.height; cv.width = W * d; cv.height = H * d; ctx.setTransform(d, 0, 0, d, 0, 0);
      F = Math.max(W, H) * .62; HZ = H * (W < 700 ? .9 : .86);
    }
    for (let i = 0; i < 220; i++) stars.push({ x: R(-4000, 4000), y: R(300, 2600), z: R(2500, 4200), a: R(.25, .8) });

    /* World to screen. Ground is y = 0, camera sits at height cam.h looking along +z. */
    function project(x, y, z) {
      const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
      const rx = x * cy - z * sy, rz = x * sy + z * cy;
      if (rz < 20) return null;
      const ry = (y - cam.h) - rz * cam.pitch;
      const k = F / rz;
      return { x: W / 2 + rx * k, y: HZ - ry * k, k };
    }

    const S = (x, y, z, vx, vy, vz, o) => sparks.push(Object.assign({ x, y, z, vx, vy, vz, l: 1, d: R(.008, .014), g: .035, dr: .975, c: '#fff', s: 2.4 }, o));
    const burst = {
      peony(sh) { const n = 140; for (let i = 0; i < n; i++) { const u = R(-1, 1), t = R(0, 6.283), r = Math.sqrt(1 - u * u), v = R(3.6, 4.2); S(sh.x, sh.y, sh.z, r * Math.cos(t) * v, u * v, r * Math.sin(t) * v, { c: P(sh.c) }); } },
      chrysanthemum(sh) { for (let i = 0; i < 160; i++) { const u = R(-1, 1), t = R(0, 6.283), r = Math.sqrt(1 - u * u), v = R(1, 4.6); S(sh.x, sh.y, sh.z, r * Math.cos(t) * v, u * v, r * Math.sin(t) * v, { c: P(sh.c), d: R(.006, .01) }); } },
      willow(sh) { for (let i = 0; i < 120; i++) { const u = R(-1, 1), t = R(0, 6.283), r = Math.sqrt(1 - u * u), v = R(2, 3.6); S(sh.x, sh.y, sh.z, r * Math.cos(t) * v, u * v, r * Math.sin(t) * v, { c: P(PAL.gold), d: R(.0035, .005), g: .022, dr: .965, s: 2 }); } },
      ring(sh) {
        const n = 90, a1 = R(0, 3.14), a2 = R(0, 3.14);
        for (let i = 0; i < n; i++) {
          const t = i / n * 6.283; let x = Math.cos(t) * 4, y = Math.sin(t) * 4, z = 0;
          let y2 = y * Math.cos(a1) - z * Math.sin(a1); z = y * Math.sin(a1) + z * Math.cos(a1); y = y2;
          const x2 = x * Math.cos(a2) + z * Math.sin(a2); z = -x * Math.sin(a2) + z * Math.cos(a2); x = x2;
          S(sh.x, sh.y, sh.z, x, y, z, { c: P(sh.c), d: .011 });
        }
      }
    };
    const TYPES = Object.keys(burst);

    function launch(x, z, type, pal) {
      const top = R(320, 560);
      shells.push({ x, y: 0, z, vy: Math.sqrt(2 * .06 * top), top, type: type || P(TYPES), c: PAL[pal || P(NAMES)] });
    }
    function randomLaunch() { launch(R(-700, 700), R(700, 1700)); }

    /* Skyline: two layers of flat towers at fixed depths, so they shift by different amounts as the camera turns */
    const layers = [1, 2].map(n => {
      const z = n === 1 ? 2600 : 1500, out = [];
      for (let x = -3200; x < 3200;) {
        const w = R(26, 70) * n, h = Math.random() < .12 ? R(110, 190) : R(18, n === 1 ? 110 : 60), win = [];
        for (let k = 0; k < (w * h) / 900; k++) if (Math.random() < .3) win.push([R(.12, .88), R(.1, .9)]);
        out.push({ x, w, h, win }); x += w + R(2, 24);
      }
      return { z, out, col: n === 1 ? '#15112a' : '#0a0812' };
    });

    function drawSkyline() {
      layers.forEach(L => {
        ctx.fillStyle = L.col; ctx.beginPath();
        L.out.forEach(b => {
          const p1 = project(b.x, 0, L.z), p2 = project(b.x + b.w, b.h, L.z);
          if (!p1 || !p2) return;
          ctx.rect(p1.x, p2.y, Math.max(1, p2.x - p1.x), p1.y - p2.y + 1);
        });
        ctx.fill();
        ctx.fillStyle = 'rgba(255,194,61,.55)';
        L.out.forEach(b => b.win.forEach(([u, v]) => { const p = project(b.x + b.w * u, b.h * v, L.z); if (p) ctx.fillRect(p.x, p.y, 1.4, 1.4); }));
      });
    }

    function frame(fade) {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = `rgba(0,0,0,${fade})`; ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
      /* stars */
      stars.forEach(s => { const p = project(s.x, s.y, s.z); if (p && p.y < HZ) { ctx.globalAlpha = s.a * .5; ctx.fillStyle = '#fff'; ctx.fillRect(p.x, p.y, 1.2, 1.2); } });
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'lighter';
      /* rising shells */
      for (let i = shells.length - 1; i >= 0; i--) {
        const s = shells[i]; s.vy -= .06; s.y += s.vy;
        const p = project(s.x, s.y, s.z);
        if (p) { ctx.fillStyle = 'rgba(255,214,150,.9)'; ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(.8, 3 * p.k), 0, 7); ctx.fill(); }
        if (Math.random() < .5) S(s.x, s.y, s.z, R(-.2, .2), R(-.6, -.2), R(-.2, .2), { c: '#ffb000', d: .06, s: 1.6, g: .01 });
        if (s.vy <= 0) { burst[s.type](s); sparks.push({ flash: 1, x: s.x, y: s.y, z: s.z, l: 1 }); shells.splice(i, 1); }
      }
      /* sparks and their reflections in the water */
      for (let i = sparks.length - 1; i >= 0; i--) {
        const s = sparks[i];
        if (s.flash) {
          const p = project(s.x, s.y, s.z);
          if (p) { ctx.globalAlpha = s.l * .12; ctx.fillStyle = '#fff1d6'; ctx.beginPath(); ctx.arc(p.x, p.y, Math.min(60, 60 * p.k) * s.l + 4, 0, 7); ctx.fill(); }
          s.l -= .07; if (s.l <= 0) sparks.splice(i, 1); continue;
        }
        s.vx *= s.dr; s.vy = s.vy * s.dr - s.g; s.vz *= s.dr;
        s.x += s.vx; s.y += s.vy; s.z += s.vz; s.l -= s.d;
        if (s.l <= 0 || s.y < 0) { sparks.splice(i, 1); continue; }
        const p = project(s.x, s.y, s.z); if (!p) continue;
        const r = Math.min(3.4, Math.max(.6, s.s * p.k * 2.6));
        ctx.fillStyle = s.c;
        ctx.globalAlpha = s.l; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 7); ctx.fill();
        const m = project(s.x, -s.y, s.z);
        if (m && m.y < H) { ctx.globalAlpha = s.l * .22; ctx.beginPath(); ctx.ellipse(m.x, m.y, r * 1.6, r * .7, 0, 0, 7); ctx.fill(); }
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      drawSkyline();
      /* shoreline glow */
      const g = ctx.createLinearGradient(0, HZ - 2, 0, HZ + 6); g.addColorStop(0, 'rgba(255,176,0,0)'); g.addColorStop(.5, 'rgba(255,176,0,.18)'); g.addColorStop(1, 'rgba(255,176,0,0)');
      ctx.fillStyle = g; ctx.fillRect(0, HZ - 2, W, 8);
    }

    /* Camera control */
    let t = 0;
    const onMove = e => { const r = cv.getBoundingClientRect(); cam.ty = ((e.clientX - r.left) / r.width - .5) * .7; cam.tp = ((e.clientY - r.top) / r.height - .5) * -.12; };
    const onTilt = e => { if (e.gamma == null) return; cam.ty = Math.max(-.45, Math.min(.45, e.gamma / 60)); };

    const api = {
      fit,
      launchAt(clientX, clientY) {
        const r = cv.getBoundingClientRect(), z = 1100;
        const sx = clientX - r.left - W / 2;
        const x = sx * z / F * Math.cos(cam.yaw) + z * Math.sin(cam.yaw);
        launch(x, z * Math.cos(cam.yaw), P(TYPES));
      },
      start() {
        fit(); addEventListener('resize', fit);
        if (reduce) {
          [[-380, 1100, 'peony', 'gold'], [260, 1300, 'ring', 'pink'], [40, 900, 'willow', 'gold'], [620, 1500, 'chrysanthemum', 'violet']].forEach(([x, z, type, pal]) => {
            const sh = { x, y: R(380, 500), z, c: PAL[pal] }; burst[type](sh);
          });
          for (let i = 0; i < 26; i++) frame(i < 25 ? 0 : 0);
          return;
        }
        let visible = true;
        new IntersectionObserver(e => { visible = e[0].isIntersecting; }).observe(cv);
        addEventListener('pointermove', onMove, { passive: true });
        addEventListener('deviceorientation', onTilt, { passive: true });
        launch(-260, 1000, 'chrysanthemum', 'gold'); launch(320, 1300, 'peony', 'pink');
        let next = 0;
        const loop = now => {
          if (visible && !document.hidden) {
            t += 1;
            const drift = Math.sin(t / 420) * .12;
            cam.yaw += (cam.ty + drift - cam.yaw) * .04;
            cam.pitch += (cam.tp - cam.pitch) * .04;
            if (now > next) { randomLaunch(); if (Math.random() < .35) randomLaunch(); next = now + R(700, 1500); }
            frame(.22);
          }
          requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
      }
    };
    return api;
  }
  window.Sky3D = sky3d;
})();
