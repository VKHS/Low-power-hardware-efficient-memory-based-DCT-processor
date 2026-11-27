/* Results page: renders artifact data (evidence.json, the vector files) and re-runs the checks that
   can run in a browser.  Text from the data is always inserted with textContent. */
(() => {
'use strict';

const EV = JSON.parse(document.getElementById('evidence').textContent);
const VEC = JSON.parse(document.getElementById('vectors').textContent);
const FPGA = JSON.parse(document.getElementById('fpga').textContent);
if (FPGA) {                                         // measured Vivado figures present: claim C14 is no longer pending
  const c14 = EV.claims.find((c) => c.id === 'C14');
  if (c14) {
    c14.basis = 'measured';
    c14.claim = `Vivado results of this repository's RTL (${FPGA.device}, ${FPGA.tool}; ${FPGA.config}): ${FPGA.dsp} DSP, ${FPGA.lut} LUT, ${FPGA.ff} FF, ${Math.round(FPGA.fmax_mhz)} MHz maximum clock, ${FPGA.power_mw} mW.`;
    c14.evidence = 'artifact/data/fpga_measured.json, read from the Vivado reports';
  }
}
const SVGNS = 'http://www.w3.org/2000/svg';
const MODES = ['table1', 'cordic2x'];
const MODE_NAME = { table1: 'Table 1 micro-rotations', cordic2x: 'CORDIC-II unit' };
const MODE_SHORT = { table1: 'Table 1', cordic2x: 'CORDIC-II' };
const MODE_CLS = { table1: '1', cordic2x: '2' };

/* ---------------------------------------------------------------- DOM helpers ---------- */
function put(e, props, kids) {
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === 'class') e.setAttribute('class', v);
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return e;
}
const h = (tag, props, ...kids) => put(document.createElement(tag), props, kids);
const sv = (tag, props, ...kids) => put(document.createElementNS(SVGNS, tag), props, kids);
const $ = (id) => document.getElementById(id);

const fx = (x, d = 2) => Number(x).toFixed(d);
const int = (x) => Number(x).toLocaleString('en-US');
const pct = (x, d = 0) => `${(100 * x).toFixed(d)} %`;
const sci = (x) => Number(x).toExponential(2);
const sign = (x, d = 2) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
const SUP = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };
const pow10 = (v) => `10${String(Math.round(Math.log10(v))).split('').map((c) => SUP[c]).join('')}`;

const ICONS = {
  check: 'M3 8.5l3.3 3.3L13 4.6',
  cross: 'M4 4l8 8M12 4l-8 8',
  built: 'M3.5 3.5h9v9h-9z',
  live: 'M5 3.2l7.2 4.8L5 12.8z',
  ci: 'M8 3a5 5 0 100 10A5 5 0 008 3zM8 5.5V8l2 1.2',
  paper: 'M4.5 2.5h5l2.5 2.5v8.5h-7.5zM6.5 8h3.5M6.5 10.5h3.5',
  pending: 'M8 3a5 5 0 100 10A5 5 0 008 3zM8 5v3.2l2.2 1.3',
  run: 'M3 8a5 5 0 105-5',
};
function icon(name, fill) {
  return sv('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true' },
    sv('path', { d: ICONS[name], fill: fill ? 'currentColor' : 'none', stroke: 'currentColor',
                 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
}
const BASIS = {
  built: ['built', 'built here', false], live: ['live', 'live in this page', true],
  ci: ['ci', 'checked in CI', false], paper: ['paper', 'quoted from the paper', false],
  measured: ['built', 'measured with Vivado', true], pending: ['pending', 'pending', false],
};
function chip(kind, label) {
  const [ic, text, fill] = BASIS[kind];
  return h('span', { class: `chip ${kind}` }, icon(ic, fill), label || text);
}
function status(kind, text) {            // pass | fail | run | caught
  return h('span', { class: `st ${kind}` }, icon(kind === 'fail' ? 'cross' : kind === 'run' ? 'run' : 'check'), text);
}

/* ---------------------------------------------------------------- tooltip -------------- */
const tip = h('div', { class: 'tip', role: 'tooltip' });
document.body.append(tip);
function tipShow(x, y, head, rows) {
  tip.replaceChildren();
  if (head) tip.append(h('div', { class: 't-h', text: head }));
  for (const r of rows) {
    tip.append(h('div', { class: 't-r' },
      r.cls ? sv('svg', { width: 12, height: 4, 'aria-hidden': 'true' }, sv('line', { x1: 0, x2: 12, y1: 2, y2: 2, class: `ln ${r.cls}` })) : null,
      h('span', { text: r.name }), r.value !== undefined ? h('b', { text: r.value }) : null));
  }
  tip.classList.add('on');
  const w = tip.offsetWidth, hgt = tip.offsetHeight;
  let left = x + 14, top = y + 14;
  if (left + w > window.innerWidth - 8) left = x - w - 14;
  if (top + hgt > window.innerHeight - 8) top = y - hgt - 14;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}
const tipHide = () => tip.classList.remove('on');
const tipAtEl = (el, head, rows) => { const r = el.getBoundingClientRect(); tipShow(r.left + r.width / 2, r.top, head, rows); };

/* ---------------------------------------------------------------- scales and ticks ----- */
function niceStep(range, n) {
  const raw = range / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}
function ticksLinear(lo, hi, n) {
  const step = niceStep(hi - lo, n), out = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}
const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/* ---------------------------------------------------------------- figure + card -------- */
function figure(draw, minW = 280) {
  const box = h('div', { class: minW > 280 ? 'fig scroll' : 'fig' });
  let last = 0;
  const render = () => {
    const w = Math.floor(box.clientWidth);
    if (w < 40 || w === last) return;
    last = w;
    box.replaceChildren(draw(Math.max(minW, w)));
  };
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(render).observe(box);
  else window.addEventListener('resize', render);
  box.render = () => { last = 0; render(); };
  requestAnimationFrame(render);
  return box;
}
function tableEl(t, cls) {
  const ths = t.head.map((c, i) => h('th', { class: t.num && t.num.includes(i) ? 'n' : '' }, c));
  const rows = t.rows.map((r) => h('tr', { class: r.hl ? 'hl' : '' },
    (r.cells || r).map((c, i) => h('td', { class: t.num && t.num.includes(i) ? 'n' : '' }, c))));
  return h('div', { class: 'tw' }, h('table', { class: cls || '' }, h('thead', {}, h('tr', {}, ths)), h('tbody', {}, rows)));
}
/* card({title, sub, legend:[{cls,text,kind}], fig, table, note}) */
function card(o) {
  const body = o.fig || h('div');
  let view = null;
  const kids = [];
  const head = h('header', {}, h('div', {}, h('h3', { text: o.title }), o.sub ? h('div', { class: 'sub', text: o.sub }) : null));
  if (o.table && o.fig) {
    const btn = h('button', { class: 'btn', type: 'button', 'aria-pressed': 'false' }, 'Table view');
    view = tableEl(o.table);
    view.hidden = true;
    btn.addEventListener('click', () => {
      const on = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? 'Chart view' : 'Table view';
      view.hidden = !on;
      body.hidden = on;
      if (!on && body.render) body.render();
    });
    head.append(btn);
  }
  kids.push(head);
  if (o.legend) {
    kids.push(h('div', { class: 'legend' }, o.legend.map((l) => h('span', {},
      h('i', { class: `${l.kind || ''}`, style: l.kind ? `background:${l.color || 'var(--ink-2)'}` : `border-top-color:${l.color || 'var(--ink-2)'}` }, null),
      l.text))));
  }
  kids.push(body);
  if (view) kids.push(view);
  if (o.extra) kids.push(o.extra);
  if (o.note) kids.push(h('p', { class: 'note' }, o.note));
  return h('div', { class: 'card', id: o.id }, kids);
}
const legendKey = (cls, text, kind) => ({ text, kind, color: `var(--s${cls})` });

/* ---------------------------------------------------------------- chart primitives ----- */
function axes(svg, g) {
  /* g: {x0, x1, y0, y1 (pixel box), xt:[{v,label}], yt:[{v,label}], sx, sy, xTitle, yTitle} */
  for (const t of g.yt) {
    const y = g.sy(t.v);
    svg.append(sv('line', { x1: g.x0, x2: g.x1, y1: y, y2: y, class: 'gridline' }),
               sv('text', { x: g.x0 - 8, y: y + 4, 'text-anchor': 'end', class: 'chart-text', text: t.label }));
  }
  svg.append(sv('line', { x1: g.x0, x2: g.x1, y1: g.y1, y2: g.y1, class: 'axisline' }));
  for (const t of g.xt) {
    svg.append(sv('text', { x: g.sx(t.v), y: g.y1 + 18, 'text-anchor': 'middle', class: 'chart-text', text: t.label }));
  }
  if (g.xTitle) svg.append(sv('text', { x: (g.x0 + g.x1) / 2, y: g.y1 + 36, 'text-anchor': 'middle', class: 'chart-text', text: g.xTitle }));
  if (g.yTitle) svg.append(sv('text', { x: g.x0 - 8, y: g.y0 - 10, 'text-anchor': 'start', class: 'chart-text', text: g.yTitle }));
}

/* Line chart over a shared categorical/numeric x list.
   o: {xs, series:[{name, cls, values, width?, label?}], y:{min,max,fmt}, xTitle, yTitle, height, refs:[{y,label,cls}], xFmt, valFmt} */
function lineChart(o) {
  return (W) => {
    const H = o.height || 320, wide = W >= 560;
    const m = { l: 48, r: wide ? (o.rightPad || 112) : 14, t: 26, b: 44 };
    const x0 = m.l, x1 = W - m.r, y0 = m.t, y1 = H - m.b;
    const sx = lin(o.xs[0], o.xs[o.xs.length - 1], x0 + 6, x1 - 6), sy = lin(o.y.min, o.y.max, y1, y0);
    const svg = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || o.yTitle || 'chart', tabindex: 0 });
    axes(svg, {
      x0, x1, y0, y1, sx, sy, xTitle: o.xTitle, yTitle: o.yTitle,
      xt: o.xs.map((v) => ({ v, label: (o.xFmt || String)(v) })),
      yt: ticksLinear(o.y.min, o.y.max, 6).map((v) => ({ v, label: (o.y.fmt || String)(v) })),
    });
    for (const r of o.refs || []) {
      const right = r.side === 'r';
      svg.append(sv('line', { x1: x0, x2: x1, y1: sy(r.y), y2: sy(r.y), class: `ref ${r.cls}` }),
                 sv('text', { x: right ? x1 - 6 : x0 + 6, y: sy(r.y) - 5, 'text-anchor': right ? 'end' : 'start', class: 'chart-text', text: wide || !r.short ? r.label : r.short }));
    }
    for (const s of o.series) {
      const pts = s.values.map((v, i) => [sx(o.xs[i]), sy(v)]);
      svg.append(sv('polyline', { points: pts.map((p) => p.join(',')).join(' '), class: `ln ${s.cls}`, style: s.width ? `stroke-width:${s.width}` : null }));
      if (!s.noMarkers) for (const p of pts) svg.append(sv('circle', { cx: p[0], cy: p[1], r: 4, class: `${s.cls.replace('c', 'f')} ring` }));
      if (wide && s.label !== false) {
        const e = pts[pts.length - 1];
        svg.append(sv('text', { x: e[0] + 10, y: e[1] + 4, class: 'chart-text ink b', text: s.label || s.name }));
      }
    }
    const cross = sv('line', { y1: y0, y2: y1, class: 'cross', visibility: 'hidden' });
    svg.append(cross);
    let cur = -1;
    const show = (i, ev, el) => {
      cur = i;
      cross.setAttribute('x1', sx(o.xs[i])); cross.setAttribute('x2', sx(o.xs[i])); cross.setAttribute('visibility', 'visible');
      const rows = o.tipRows ? o.tipRows(i) : o.series.map((s) => ({ name: s.name, cls: s.cls, value: (o.valFmt || String)(s.values[i]) }));
      const head = `${o.xTitle ? o.xTitle + ' ' : ''}${(o.xFmt || String)(o.xs[i])}`;
      if (ev) tipShow(ev.clientX, ev.clientY, head, rows); else tipAtEl(svg, head, rows);
    };
    const hide = () => { cross.setAttribute('visibility', 'hidden'); tipHide(); cur = -1; };
    const hit = sv('rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: 'hit' });
    hit.addEventListener('pointermove', (ev) => {
      const r = svg.getBoundingClientRect(), px = ev.clientX - r.left;
      let best = 0, bd = 1e9;
      o.xs.forEach((v, i) => { const d = Math.abs(sx(v) - px); if (d < bd) { bd = d; best = i; } });
      show(best, ev);
    });
    hit.addEventListener('pointerleave', hide);
    svg.append(hit);
    svg.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowRight') show(Math.min(o.xs.length - 1, cur + 1), null);
      else if (ev.key === 'ArrowLeft') show(Math.max(0, cur < 0 ? 0 : cur - 1), null);
      else if (ev.key === 'Escape') hide();
      else return;
      ev.preventDefault();
    });
    svg.addEventListener('blur', hide);
    return svg;
  };
}

/* Grouped columns: o: {cats, series:[{name,cls,values}], y:{min,max,fmt}, yTitle, height, valFmt, catTitle} */
function groupedBars(o) {
  return (W) => {
    const H = o.height || 300, m = { l: 52, r: 14, t: 26, b: 44 };
    const x0 = m.l, x1 = W - m.r, y0 = m.t, y1 = H - m.b;
    const sy = lin(o.y.min, o.y.max, y1, y0);
    const slot = (x1 - x0) / o.cats.length, n = o.series.length;
    const bw = Math.min(16, Math.max(6, (slot - 14) / n - 2)), gap = 2;
    const svg = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || o.yTitle });
    axes(svg, { x0, x1, y0, y1, sx: (i) => x0 + slot * (i + 0.5), sy, yTitle: o.yTitle, xt: o.cats.map((c, i) => ({ v: i, label: c })), xTitle: o.catTitle,
                yt: ticksLinear(o.y.min, o.y.max, 5).map((v) => ({ v, label: (o.y.fmt || String)(v) })) });
    o.cats.forEach((c, i) => {
      const cx = x0 + slot * (i + 0.5), gw = n * bw + (n - 1) * gap;
      o.series.forEach((s, j) => {
        const v = s.values[i], top = sy(Math.max(o.y.min, v)), bx = cx - gw / 2 + j * (bw + gap), r = Math.min(4, bw / 2, y1 - top);
        const d = `M${bx},${y1}V${top + r}Q${bx},${top} ${bx + r},${top}H${bx + bw - r}Q${bx + bw},${top} ${bx + bw},${top + r}V${y1}Z`;
        svg.append(sv('path', { d, class: s.cls.replace('c', 'f') }));
      });
      const band = sv('rect', { x: cx - slot / 2, y: y0, width: slot, height: y1 - y0, class: 'hit mark', tabindex: 0, 'aria-label': `${c}: ` + o.series.map((s) => `${s.name} ${(o.valFmt || String)(s.values[i])}`).join(', ') });
      const rows = o.series.map((s) => ({ name: s.name, cls: s.cls, value: (o.valFmt || String)(s.values[i]) }));
      band.addEventListener('pointermove', (ev) => tipShow(ev.clientX, ev.clientY, c, rows));
      band.addEventListener('pointerleave', tipHide);
      band.addEventListener('focus', () => tipAtEl(band, c, rows));
      band.addEventListener('blur', tipHide);
      svg.append(band);
    });
    return svg;
  };
}

/* Scatter with a nearest-point hit layer.  o: {points:[{x,y,cls,r,shape,label,tip:{head,rows}}], x:{min,max,fmt,log}, y:{min,max,fmt,log}, ...} */
function scatter(o) {
  return (W) => {
    const H = o.height || 340, m = { l: 58, r: 16, t: 26, b: 46 };
    const x0 = m.l, x1 = W - m.r, y0 = m.t, y1 = H - m.b;
    const f = (a) => (a.log ? Math.log10 : (v) => v);
    const sx = lin(f(o.x)(o.x.min), f(o.x)(o.x.max), x0 + 6, x1 - 6), sy = lin(f(o.y)(o.y.min), f(o.y)(o.y.max), y1, y0);
    const px = (v) => sx(f(o.x)(v)), py = (v) => sy(f(o.y)(v));
    const svg = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || o.yTitle });
    const yt = o.y.log
      ? Array.from({ length: Math.log10(o.y.max / o.y.min) + 1 }, (_, i) => o.y.min * Math.pow(10, i)).map((v) => ({ v, label: o.y.fmt(v) }))
      : ticksLinear(o.y.min, o.y.max, 5).map((v) => ({ v, label: o.y.fmt(v) }));
    axes(svg, { x0, x1, y0, y1, sx: px, sy: py, xTitle: o.xTitle, yTitle: o.yTitle, xt: ticksLinear(o.x.min, o.x.max, 8).map((v) => ({ v, label: o.x.fmt(v) })), yt });
    for (const l of o.lines || []) {
      svg.append(sv('polyline', { points: l.pts.map((p) => `${px(p[0])},${py(p[1])}`).join(' '), class: `ln ${l.cls}`, style: 'stroke-width:1.5' }));
    }
    const pts = o.points.map((p) => ({ ...p, X: px(p.x), Y: py(p.y) }));
    for (const p of pts.filter((q) => !q.top)) svg.append(markOf(p));
    for (const p of pts.filter((q) => q.top)) svg.append(markOf(p));
    for (const p of pts.filter((q) => q.label)) {
      svg.append(sv('text', { x: p.X + (p.dx ?? 10), y: p.Y + (p.dy ?? 4), class: 'chart-text ink b', 'text-anchor': p.anchor || 'start', text: p.label }));
    }
    const hit = sv('rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: 'hit' });
    const ring = sv('circle', { r: 9, fill: 'none', class: 'ci-ink', 'stroke-width': 1.5, visibility: 'hidden', 'pointer-events': 'none' });
    hit.addEventListener('pointermove', (ev) => {
      const r = svg.getBoundingClientRect(), qx = ev.clientX - r.left, qy = ev.clientY - r.top;
      let best = null, bd = 1e9;
      for (const p of pts) { const d = (p.X - qx) ** 2 + (p.Y - qy) ** 2; if (d < bd) { bd = d; best = p; } }
      if (best && bd < 40 * 40) {
        ring.setAttribute('cx', best.X); ring.setAttribute('cy', best.Y); ring.setAttribute('visibility', 'visible');
        tipShow(ev.clientX, ev.clientY, best.tip.head, best.tip.rows);
      } else { ring.setAttribute('visibility', 'hidden'); tipHide(); }
    });
    hit.addEventListener('pointerleave', () => { ring.setAttribute('visibility', 'hidden'); tipHide(); });
    svg.append(ring, hit);
    return svg;
  };
  function markOf(p) {
    if (p.shape === 'diamond') {
      const r = p.r || 6;
      return sv('path', { d: `M${p.X},${p.Y - r}L${p.X + r},${p.Y}L${p.X},${p.Y + r}L${p.X - r},${p.Y}Z`, class: `${p.fill || 'fi'} ring` });
    }
    return sv('circle', { cx: p.X, cy: p.Y, r: p.r || 4, class: `${p.fill || 'fg'} ring`, style: p.opacity ? `opacity:${p.opacity}` : null });
  }
}

/* ================================================================================= live checks */
const VSETS = Object.keys(JSON.parse(VEC['manifest.json']));
const LIVE = { vectors: null, sets: {}, faults: [], ssLossy: {}, sched: null, schedFaults: [], digests: {}, ms: 0 };
const SUFFIX = { in: 'in.txt', out: 'out.txt', stim: 'stim.hex', expect: 'expect.hex' };
const tick = () => new Promise((r) => setTimeout(r, 0));

function cloneJson(o) { return JSON.parse(JSON.stringify(o)); }
const MAN = JSON.parse(VEC['manifest.json']);
const SCHED_JSON = JSON.parse(VEC['schedule.json']);

function arithmeticFaults() {
  const D = Model.DEFAULT_TABLES;
  const p1 = cloneJson(D.T1_P); p1[1] = [10, 3];
  const k2 = cloneJson(D.T1_K); k2[2] = k2[2].slice(0, 3);
  const c2 = cloneJson(D.CTRL); c2[2][4] = 0;
  const rs = cloneJson(D.RS_TERMS); rs[4][1] = 1;
  return [
    { kind: 'ss', name: 'safe-scaling unit rounds half to even instead of half to odd', over: { ssRound: Model.rne } },
    { kind: 'ss', name: 'safe-scaling unit rounds half up', over: { ssRound: Model.rnd } },
    { kind: 'ss', name: 'safe-scaling unit truncates (no rounding)', over: { ssRound: (z, s) => z >> s } },
    { kind: 't1', name: 'Table 1: rotation constant P1 = 10+j3 instead of 10+j2', over: { T1_P: p1 } },
    { kind: 't1', name: 'Table 1: radius scale-down K2 loses its last term', over: { T1_K: k2 } },
    { kind: 'c2', name: 'CORDIC-II: nano term n9 of angle 2 removed', over: { CTRL: c2 } },
    { kind: 'c2', name: 'CORDIC-II: sign of the last radius-scaling term flipped', over: { RS_TERMS: rs } },
    { kind: 'c2', name: 'CORDIC-II: friend-angle shift 2 instead of 3', over: { FA_SHIFT: 2 } },
  ];
}

function checkVectors() {
  const model = Model.make(), out = {};
  for (const name of VSETS) {
    const files = VEC.sets[name];
    const dig = {};
    let match = 0;
    for (const [k, suf] of Object.entries(SUFFIX)) {
      dig[suf] = Sha256.hex(files[k]);
      if (dig[suf] === EV.vectors.sets[name].files[suf].sha256) match++;
    }
    out[name] = { checks: Model.checkSet(model, MAN[name], files), digests: dig, match, nfiles: 4 };
  }
  return out;
}
function checkFaults() {
  return arithmeticFaults().map((f) => {
    const m = Model.make(f.over), failing = [];
    for (const name of VSETS) {
      let res;
      try { res = Model.checkSet(m, MAN[name], VEC.sets[name]); } catch (e) { failing.push(name); continue; }
      if (res.some((c) => !c.ok)) failing.push(name);
    }
    return { name: f.name, kind: f.kind, failing, caught: failing.length > 0 };
  });
}
/* safe-scaling shifts that drop a non-zero bit, per vector set: only there can a rounding fault show */
function ssLossy() {
  const out = {};
  for (const name of VSETS) {
    let n = 0;
    const m = Model.make({ ssRound: (z, s) => { if (s >= 1 && (z & ((1 << s) - 1)) !== 0) n++; return Model.rno(z, s); } });
    Model.checkSet(m, MAN[name], VEC.sets[name]);
    out[name] = n;
  }
  return out;
}
function schedInput() {
  const sj = cloneJson(SCHED_JSON);
  sj.ports = EV.schedule.ports;
  sj.utilisation = EV.schedule.utilisation;
  return sj;
}
async function runLive(onProgress) {
  const t0 = performance.now();
  onProgress && onProgress('hashing and replaying vector sets');
  await tick();
  LIVE.sets = checkVectors();
  for (const [k, suf] of [['manifest.json', 'manifest.json'], ['schedule.json', 'schedule.json']]) {
    LIVE.digests[k] = { got: Sha256.hex(VEC[k]), want: EV.vectors.files[suf].sha256 };
  }
  const allChecks = VSETS.flatMap((n) => LIVE.sets[n].checks);
  const words = VSETS.reduce((s, n) => s + EV.vectors.sets[n].words, 0);
  const goodSets = VSETS.filter((n) => LIVE.sets[n].checks.every((c) => c.ok) && LIVE.sets[n].match === 4).length;
  LIVE.vectors = {
    ok: goodSets === VSETS.length && Object.values(LIVE.digests).every((d) => d.got === d.want),
    sets: goodSets, total: VSETS.length, words, checks: allChecks.length,
  };
  onProgress && onProgress('injecting arithmetic faults');
  await tick();
  LIVE.faults = checkFaults();
  LIVE.ssLossy = ssLossy();
  onProgress && onProgress('checking the schedule');
  await tick();
  const sj = schedInput();
  const checks = Sched.check(sj);
  const ties = [];
  for (const [n, m] of Object.entries(MAN)) if (m.kind === 'dct8') ties.push(m.first_out_cycle === sj.t0 + 1);
  LIVE.sched = { checks, ok: checks.every((c) => c.ok), tie: ties.every(Boolean), nTie: ties.length };
  LIVE.schedFaults = Sched.controls(sj);
  LIVE.ms = performance.now() - t0;
  const pass = LIVE.vectors.ok && LIVE.sched.ok && LIVE.sched.tie
    && LIVE.faults.every((f) => f.caught) && LIVE.schedFaults.every((f) => f.detected);
  LIVE.pass = pass;
  document.body.dataset.live = pass ? 'pass' : 'fail';
  return LIVE;
}

/* ================================================================================= sections */
const A1 = EV.accuracy_1d, A2 = EV.accuracy_2d, AL = EV.paper_alignment, OV = EV.overflow, SCH = EV.schedule;
const WS = [8, 9, 10, 11, 12, 13, 14, 15, 16];
const best1 = (mode, w) => A1.rows.find((r) => r.mode === mode && r.w === w && r.best);
const row2 = (mode, w) => A2.rows.find((r) => r.mode === mode && r.w === w);
const code = (t) => h('code', { text: t });
const countBasis = (b) => EV.claims.filter((c) => c.basis === b).length;

/* ---- hero -------------------------------------------------------------------------------- */
function renderHero() {
  $('cite').append(`${EV.paper.citation}. `,
    h('a', { href: `https://doi.org/${EV.paper.doi}`, rel: 'noopener' }, `doi:${EV.paper.doi}`), ' · ',
    h('a', { href: EV.meta.repository, rel: 'noopener' }, 'github.com/VKHS/memory-based-dct8'));
  const words = VSETS.reduce((s, n) => s + EV.vectors.sets[n].words, 0);
  const num = h('div', { class: 'hero-num', text: '…' });
  const tiles = [
    ['vec', 'golden vector sets reproduced'], ['sch', 'schedule checks hold'], ['flt', 'injected faults caught'],
    ['ovf', 'configurations scanned for overflow'],
  ].map(([id, label]) => h('div', { class: 'stat' }, h('b', { id: `stat-${id}`, text: '…' }), h('span', { text: label })));
  $('hero').append(
    h('div', {}, num, h('div', { class: 'hero-cap', text: `of ${int(words)} output words reproduced bit for bit in this browser, by code that shares nothing with the Python models` })),
    ...tiles);
  const nb = countBasis('built'), nc = countBasis('ci'), np = countBasis('paper'), nm = countBasis('measured'), nq = countBasis('pending');
  $('hero-lede').textContent = `${EV.claims.length} claims, each with its evidence and the command that reproduces it: ${nb} computed in this build, ${nc} checked by CI jobs, ${np} quoted from the paper${nm ? `, ${nm} measured with Vivado` : ''}${nq ? `, ${nq} pending a measurement (the repository's own FPGA figures)` : ''}.`;
  return () => {
    const L = LIVE;
    const okWords = VSETS.filter((n) => L.sets[n].checks.every((c) => c.ok) && L.sets[n].match === 4).reduce((a, n) => a + EV.vectors.sets[n].words, 0);
    num.textContent = int(okWords);
    $('stat-vec').textContent = `${L.vectors.sets} / ${L.vectors.total}`;
    $('stat-sch').textContent = `${L.sched.checks.filter((c) => c.ok).length} / ${L.sched.checks.length}`;
    $('stat-flt').textContent = `${L.faults.filter((f) => f.caught).length + L.schedFaults.filter((f) => f.detected).length} / ${L.faults.length + L.schedFaults.length}`;
    $('stat-ovf').textContent = `${OV.configs - OV.failures} / ${OV.configs}`;
  };
}

/* ---- claims ------------------------------------------------------------------------------ */
function renderClaims() {
  const host = $('claims-card');
  const liveChips = [];
  const tbody = h('tbody');
  let cur = 'all';
  const matches = (c) => cur === 'all' || c.basis === cur || (cur === 'live' && c.live);
  const fill = () => {
    tbody.replaceChildren();
    liveChips.length = 0;
    for (const c of EV.claims.filter(matches)) {
      const pend = c.basis === 'pending';
      const chips = [BASIS[c.basis] ? chip(c.basis) : status('fail', c.basis)];
      if (c.live) { const lc = chip('live'); liveChips.push([lc, c.live]); chips.push(lc); }
      tbody.append(h('tr', {},
        h('td', { class: 'nowrap', text: c.id }),
        h('td', { class: `claim${pend ? ' pending-ink' : ''}`, text: c.claim }),
        h('td', {}, h('div', { class: 'row' }, chips)),
        h('td', { class: 'small', 'data-label': 'Evidence', text: c.evidence }),
        h('td', { class: 'cmd small', 'data-label': 'Run' }, code(c.reproduce))));
    }
    paintLive();
  };
  const buttons = ['all', 'built', 'live', 'ci', 'paper', 'measured', 'pending'].filter((k) => k === 'all' || k === 'live' || countBasis(k) > 0).map((k) => {
    const n = k === 'all' ? EV.claims.length : k === 'live' ? EV.claims.filter((c) => c.live).length : countBasis(k);
    const b = h('button', { class: 'btn', type: 'button', 'aria-pressed': String(k === 'all'), onclick: () => {
      cur = k;
      buttons.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      fill();
    } }, `${k === 'all' ? 'All' : BASIS[k][1]} (${n})`);
    return b;
  });
  host.append(h('div', { class: 'row' }, buttons),
    h('div', { class: 'tw' }, h('table', { class: 'fixed' },
      h('colgroup', {}, ['46px', '38%', '150px', '22%', 'auto'].map((w) => h('col', { style: `width:${w}` }))),
      h('thead', {}, h('tr', {}, ['ID', 'Claim', 'Basis', 'Evidence', 'Reproduce'].map((t) => h('th', { text: t })))), tbody)));
  function paintLive() {
    for (const [el, kind] of liveChips) {
      const res = !LIVE.vectors ? null : kind === 'vectors' ? LIVE.vectors.ok : LIVE.sched.ok && LIVE.sched.tie;
      el.replaceChildren(icon(res === false ? 'cross' : 'live', res !== false), res === null ? 'live: running' : res ? 'live: pass' : 'live: FAIL');
      el.className = `chip live${res === false ? ' pending' : ''}`;
    }
  }
  fill();
  return paintLive;
}

/* ---- verification panel ------------------------------------------------------------------- */
function renderVerify() {
  const host = $('verify-body');
  const prog = h('span', { class: 'sub' });
  const btn = h('button', { class: 'btn', type: 'button' }, 'Run again');
  const vec = h('div'), flt = h('div'), sch = h('div'), sflt = h('div'), tie = h('p', { class: 'note' });
  host.append(
    h('div', { class: 'row', style: 'margin-bottom:12px' }, btn, prog),
    h('div', { class: 'card' }, h('header', {}, h('div', {}, h('h3', { text: 'Golden vector sets' }),
      h('div', { class: 'sub', text: 'The files the RTL, HLS and MATLAB test benches read. SHA-256 is computed here and compared with the digest recorded when the page was built; then the model replays every block.' }))), vec),
    h('div', { class: 'card' }, h('header', {}, h('div', {}, h('h3', { text: 'Can the vectors fail? Deliberate arithmetic faults' }),
      h('div', { class: 'sub', text: 'Each fault changes one rounding rule or constant in the JavaScript model; the vectors must notice.' }))), flt),
    h('div', { class: 'card' }, h('header', {}, h('div', {}, h('h3', { text: 'Schedule checks' }),
      h('div', { class: 'sub', text: 'Derived from vectors/schedule.json alone: operation times, lifetimes, register sharing, memory words, ports, control words.' }))), sch, tie),
    h('div', { class: 'card' }, h('header', {}, h('div', {}, h('h3', { text: 'Can the schedule checks fail? Deliberate faults' }),
      h('div', { class: 'sub', text: 'Each fault is applied to a copy of the schedule; the named check must reject it.' }))), sflt));
  const fill = () => {
    vec.replaceChildren(tableEl({
      head: ['Set', 'Configuration', 'Blocks', 'Words', 'SHA-256', 'Replay'], num: [2, 3],
      rows: VSETS.map((n) => {
        const s = LIVE.sets[n], e = EV.vectors.sets[n];
        const ok = s.checks.every((c) => c.ok);
        return [code(n), h('span', { class: 'small', text: e.config }), int(e.blocks), int(e.words),
                status(s.match === 4 ? 'pass' : 'fail', `${s.match}/4 files`),
                status(ok ? 'pass' : 'fail', s.checks.find((c) => c.id === 'functional').detail)];
      }),
    }));
    const sameSet = (x, y) => x.length === y.length && x.every((v) => y.includes(v));
    const lossySets = VSETS.filter((n) => LIVE.ssLossy[n] > 0);
    const t1Sets = VSETS.filter((n) => MAN[n].mr_mode === 'table1'), c2Sets = VSETS.filter((n) => MAN[n].mr_mode === 'cordic2x');
    const exercised = { ss: lossySets, t1: t1Sets, c2: c2Sets };
    const exact = LIVE.faults.every((f) => sameSet(f.failing, exercised[f.kind]));
    flt.replaceChildren(tableEl({
      head: ['Fault', 'Vector sets that fail', 'Verdict'],
      rows: LIVE.faults.map((f) => [f.name, h('span', { class: 'small', text: `${f.failing.length} of ${VSETS.length}: ${f.failing.join(', ')}` }),
                                    status(f.caught ? 'caught' : 'fail', f.caught ? 'caught' : 'not noticed')]),
    }), h('p', { class: 'note' },
      `A rounding fault can only show where a safe-scaling shift drops a non-zero bit; the constants of a rotation set only in the sets that use it. `,
      `Shifts that drop a non-zero bit per set: ${VSETS.map((n) => `${n} ${int(LIVE.ssLossy[n])}`).join(' · ')}. Sets using Table 1: ${t1Sets.length}; using the CORDIC-II unit: ${c2Sets.length}. `,
      exact ? 'Every fault is noticed by exactly the sets that exercise the element it changes.' : 'Some fault is noticed by sets other than those that exercise it, or missed by one that does.'));
    sch.replaceChildren(tableEl({
      head: ['Check', 'Result', 'Verdict'],
      rows: LIVE.sched.checks.map((c) => [c.text, h('span', { class: 'small', text: c.detail }), status(c.ok ? 'pass' : 'fail', c.ok ? 'holds' : 'violated')]),
    }));
    tie.replaceChildren(status(LIVE.sched.tie ? 'pass' : 'fail',
      `The first output cycle in the manifest is ${SCHED_JSON.t0 + 1} = t0 + 1 for all ${LIVE.sched.nTie} one-dimensional sets, which ties the schedule to the vectors the RTL is tested with.`));
    sflt.replaceChildren(tableEl({
      head: ['Fault', 'Where', 'Must be caught by', 'Checks that failed', 'Verdict'],
      rows: LIVE.schedFaults.map((f) => [f.fault, h('span', { class: 'small', text: f.where || '' }), code(f.expected),
                                         h('span', { class: 'small', text: f.failed.join(', ') }), status(f.detected ? 'caught' : 'fail', f.detected ? 'caught' : 'missed')]),
    }));
    prog.textContent = `${LIVE.pass ? 'all checks pass' : 'a check failed'} · ${LIVE.ms.toFixed(0)} ms`;
  };
  return { fill, prog, btn };
}

/* ---- accuracy ---------------------------------------------------------------------------- */
function renderAccuracy() {
  const host = $('accuracy-body');
  const lim = A1.limit_sqnr_db;
  const gap12 = Math.max(...WS.filter((w) => w <= 12).map((w) => best1('table1', w).sqnr_exact_rot - best1('cordic2x', w).sqnr));
  const wSat = WS.find((w) => lim.table1 - best1('table1', w).sqnr < 0.01);

  /* 1-D SQNR */
  const sqnr = card({
    title: '1-D SQNR against word length',
    sub: `${int(A1.n_vectors)} random 8-bit input vectors (seed ${A1.seed}); best safe-scaling choice at each W; thin lines: floating-point limit of each rotation set`,
    legend: [legendKey(1, MODE_NAME.table1), legendKey(2, MODE_NAME.cordic2x), { text: 'datapath with exact rotations', color: 'var(--ink-2)' }],
    fig: figure(lineChart({
      xs: WS, y: { min: 30, max: 90, fmt: String }, xTitle: 'W', yTitle: 'SQNR (dB)', height: 430, aria: 'SQNR against word length',
      series: [
        { name: MODE_NAME.table1, cls: 'c1', label: 'Table 1', values: WS.map((w) => best1('table1', w).sqnr) },
        { name: MODE_NAME.cordic2x, cls: 'c2', label: 'CORDIC-II', values: WS.map((w) => best1('cordic2x', w).sqnr) },
        { name: 'exact rotations (datapath only)', cls: 'cg', label: 'exact rotations', values: WS.map((w) => best1('table1', w).sqnr_exact_rot) },
      ],
      refs: [{ y: lim.table1, cls: 'c1', side: 'r', short: `${fx(lim.table1)} dB`, label: `limit of the Table 1 constants: ${fx(lim.table1)} dB` },
             { y: lim.cordic2x, cls: 'c2', side: 'l', short: `${fx(lim.cordic2x)} dB`, label: `limit of the CORDIC-II unit: ${fx(lim.cordic2x)} dB` }],
      valFmt: (v) => `${fx(v)} dB`,
    })),
    table: { head: ['W', 'SS (best)', 'Table 1 (dB)', 'CORDIC-II (dB)', 'exact rotations (dB)'], num: [0, 2, 3, 4],
             rows: WS.map((w) => [w, best1('table1', w).ss.join(''), fx(best1('table1', w).sqnr), fx(best1('cordic2x', w).sqnr), fx(best1('table1', w).sqnr_exact_rot)]) },
    note: h('span', {}, h('b', { text: 'Reading: ' }), `with Table 1 constants the curve flattens at ${fx(lim.table1)} dB from W = ${wSat}: the same flow graph evaluated in floating point with the realised rotation coefficients gives ${fx(lim.table1)} dB, so the plateau is the angle and gain error of the three Gaussian integers, not the word length. The CORDIC-II unit stays within ${fx(gap12, 1)} dB of the exact-rotation datapath up to W = 12 and ends ${fx(lim.cordic2x - best1('cordic2x', 16).sqnr, 2)} dB below its own limit at W = 16.`),
  });

  /* per output */
  const po = A1.rms_per_output_w14;
  const perOutNote = () => {
    const names = ['Y0', 'Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Y6', 'Y7'];
    const zero = names.filter((_, i) => po.table1[i] === 0 && po.cordic2x[i] === 0 && po.exact_rotations[i] === 0);
    const w3 = EV.flowgraph.find((f) => f.name === 'W3').outs.slice().sort();
    const top2 = names.map((n, i) => [n, po.table1[i]]).sort((a, b) => b[1] - a[1]).slice(0, 2).map((x) => x[0]).sort();
    const big = EV.rotations.table1.slice().sort((a, b) => Math.abs(b.angle_err_rad) - Math.abs(a.angle_err_rad)).slice(0, 2).map((r) => r.k).sort();
    let t = zero.length ? `${zero.join(' and ')} come out of the flow graph without a rotation and carry no error. ` : '';
    if (top2.join() === w3.join() && big.join() === '2,3') {
      t += `With Table 1 the largest errors are on ${w3.join(' and ')}, which pass through the two rotations with the largest angle errors (k = 2, then k = 3; see the rotation table below).`;
    }
    return t;
  };
  const outs = ['Y0', 'Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Y6', 'Y7'];
  const mx = Math.max(...po.table1), mz = Math.max(...po.cordic2x, ...po.exact_rotations);
  const zoomMax = Math.ceil(mz * 100) / 100;
  const perOut = card({
    title: 'Error by output at W = 14',
    sub: `rms error of each coefficient, same ${int(A1.n_vectors)} vectors`,
    legend: [legendKey(1, 'Table 1', 'box'), legendKey(2, 'CORDIC-II', 'box'), { text: 'exact rotations', kind: 'box', color: 'var(--ink-2)' }],
    fig: h('div', {},
      figure(groupedBars({
        cats: outs, y: { min: 0, max: Math.ceil(mx * 10) / 10, fmt: (v) => fx(v, 1) }, yTitle: 'rms error', height: 250,
        aria: 'rms error by output, all three variants', valFmt: (v) => fx(v, 4),
        series: [{ name: 'Table 1', cls: 'c1', values: po.table1 }, { name: 'CORDIC-II', cls: 'c2', values: po.cordic2x }, { name: 'exact rotations', cls: 'cg', values: po.exact_rotations }],
      })),
      h('div', { class: 'sub', style: 'margin-top:10px', text: `Same data, CORDIC-II and exact rotations only, on their own scale (up to ${fx(zoomMax, 2)}):` }),
      figure(groupedBars({
        cats: outs, y: { min: 0, max: zoomMax, fmt: (v) => fx(v, 2) }, yTitle: 'rms error', height: 210,
        aria: 'rms error by output, CORDIC-II and exact rotations', valFmt: (v) => fx(v, 4),
        series: [{ name: 'CORDIC-II', cls: 'c2', values: po.cordic2x }, { name: 'exact rotations', cls: 'cg', values: po.exact_rotations }],
      }))),
    table: { head: ['Output', 'Table 1', 'CORDIC-II', 'exact rotations'], num: [1, 2, 3], rows: po.table1.map((_, i) => [outs[i], fx(po.table1[i], 4), fx(po.cordic2x[i], 4), fx(po.exact_rotations[i], 4)]) },
    note: perOutNote(),
  });
  host.append(h('div', { class: 'grid2 split' }, sqnr, perOut));

  /* 2-D PSNR: repository and paper Table 3 on one y scale */
  const t3 = EV.paper.table3, wl = [...t3.wl].reverse();
  const others = Object.keys(t3.rows).filter((k) => k !== 'Proposed');
  const psnrRepo = card({
    title: 'This repository: 8×8 PSNR against the double-precision DCT',
    sub: `mean over ${Object.keys(A2.images).length} scikit-image test images, both passes at W`,
    legend: [legendKey(1, MODE_NAME.table1), legendKey(2, MODE_NAME.cordic2x)],
    fig: figure(lineChart({
      xs: WS, y: { min: 0, max: 90, fmt: String }, xTitle: 'W', yTitle: 'PSNR (dB)', height: 330, aria: 'PSNR of this repository',
      series: MODES.map((m) => ({ name: MODE_NAME[m], cls: `c${MODE_CLS[m]}`, label: MODE_SHORT[m], values: WS.map((w) => row2(m, w).mean) })),
      tipRows: (i) => MODES.map((m) => { const r = row2(m, WS[i]); return { name: `${MODE_SHORT[m]} (min ${fx(r.min, 1)}, max ${fx(r.max, 1)})`, cls: `c${MODE_CLS[m]}`, value: `${fx(r.mean)} dB` }; }),
    })),
    table: { head: ['W', 'Table 1 mean (min – max)', 'CORDIC-II mean (min – max)'], num: [0],
             rows: WS.map((w) => [w, ...MODES.map((m) => { const r = row2(m, w); return `${fx(r.mean)} (${fx(r.min, 1)} – ${fx(r.max, 1)})`; })]) },
  });
  const psnrPaper = card({
    title: 'Paper, Table 3: PSNR on BSD-100 (quoted)',
    sub: `${t3.dataset}; reference: ${t3.reference}`,
    legend: [{ text: 'proposed method', color: 'var(--ink)' }, { text: `${others.length} other methods [16]–[24]`, color: 'var(--ink-2)' }],
    fig: figure(lineChart({
      xs: wl, y: { min: 0, max: 90, fmt: String }, xTitle: 'WL', yTitle: 'PSNR (dB)', height: 330, aria: 'PSNR quoted from paper Table 3', valFmt: (v) => `${fx(v)} dB`,
      series: [...others.map((k, i) => ({ name: k, cls: 'cm', noMarkers: true, width: 1.25, label: i === 0 ? '9 other methods' : false, values: [...t3.rows[k]].reverse() })),
               { name: 'Proposed', cls: 'ck', label: 'proposed', values: [...t3.rows.Proposed].reverse() }],
      tipRows: (i) => {
        const col = others.map((k) => [...t3.rows[k]].reverse()[i]);
        return [{ name: 'proposed', cls: 'ck', value: `${fx(t3.rows.Proposed[t3.wl.length - 1 - i])} dB` },
                { name: `other methods, min – max`, cls: 'cm', value: `${fx(Math.min(...col))} – ${fx(Math.max(...col))}` }];
      },
    })),
    table: { head: ['Method', ...wl.map((v) => `WL ${v}`)], num: wl.map((_, i) => i + 1),
             rows: Object.entries(t3.rows).map(([k, v]) => ({ cells: [k, ...[...v].reverse().map((x) => fx(x))], hl: k === 'Proposed' })) },
  });
  host.append(h('div', { class: 'grid2' }, psnrRepo, psnrPaper));

  const eq = AL.repo;
  const lowest = Math.min(...MODES.map((m) => row2(m, 8).mean));
  const outside = t3.wl.filter((v, i) => t3.rows.Proposed[i] < lowest);
  host.append(card({
    title: 'Reading Table 3 next to these curves',
    sub: 'what the quoted table fixes and what it leaves open',
    fig: null,
    extra: h('div', {},
      tableEl({
        head: ['Paper WL', 'Paper PSNR (dB)', 'W here for equal PSNR, Table 1', 'WL − W', 'W here for equal PSNR, CORDIC-II', 'WL − W'], num: [0, 1, 2, 3, 4, 5],
        rows: eq.table1.equal_psnr.map((o, i) => [o.paper_wl, fx(o.paper_psnr), fx(o.repo_w), fx(o.offset_bits), fx(eq.cordic2x.equal_psnr[i].repo_w), fx(eq.cordic2x.equal_psnr[i].offset_bits)]),
      }, 'compact'),
      h('p', { class: 'note' }, h('b', { text: 'Facts. ' }),
        `At each WL the ten methods of Table 3 lie within ${fx(AL.max_spread_db)} dB of each other (spread at WL ${t3.wl.join(', ')}: ${AL.spread_db_per_wl.map((v) => fx(v)).join(', ')} dB), while the PSNR of the proposed method changes by ${fx(AL.paper_slope_db_per_bit, 1)} dB per bit of WL between WL ${t3.wl[t3.wl.length - 1]} and ${t3.wl[0]}. In Table 3 the PSNR is therefore set by the word length and hardly at all by the method. ${t3.format_stated ? '' : 'The paper does not state the integer/fraction split of WL. '}Here the slope between W = 8 and 12 is ${fx(eq.table1.slope_db_per_bit_w8_12, 1)} dB per bit (Table 1) and ${fx(eq.cordic2x.slope_db_per_bit_w8_12, 1)} dB per bit (CORDIC-II). Equal-PSNR word lengths are interpolated on the curves above, so only the paper WL whose PSNR falls inside them are listed${outside.length ? `; the PSNR at WL ${outside.join(', ')} is below the W = 8 point here (${fx(lowest)} dB)` : ''}.`)),
  }));

  /* zonal compression */
  const zr = EV.compression;
  const images = Object.keys(A2.images), ratios = zr.ratios;
  host.append(card({
    title: 'Zonal compression through the bit-accurate 2-D processor',
    sub: `PSNR (dB) after keeping the first ${ratios.map((r) => r.split(':')[1]).join(', ')} zig-zag coefficients of each 8×8 block. Row core: ${zr.row}. Column core: ${zr.col}.`,
    fig: null,
    extra: h('div', {}, tableEl({
      head: ['Image', ...ratios, 'largest difference to the double-precision DCT'], num: [1, 2, 3, 4, 5],
      rows: images.map((im) => {
        const rr = zr.rows.filter((r) => r.image === im);
        return [im, ...ratios.map((rt) => fx(rr.find((r) => r.ratio === rt).psnr_hw)), `${fx(Math.max(...rr.map((r) => r.abs_diff_db)), 4)} dB`];
      }),
    }, 'compact')),
    note: `Over all ${zr.rows.length} image and ratio pairs the processor and the double-precision DCT give the same PSNR to within ${fx(zr.max_abs_diff_db, 4)} dB.`,
  }));

  /* rotation sets */
  const R1 = EV.rotations.table1, R2 = EV.rotations.cordic2x;
  host.append(card({
    title: 'Angle and gain of the two rotation sets',
    sub: 'what each micro-rotation unit realises for the three merging angles k·π/16',
    fig: null,
    extra: tableEl({
      head: ['k', 'target', 'Table 1: realised', 'angle error (rad)', 'gain', 'CORDIC-II: realised', 'angle error (rad)', 'gain'], num: [0, 1, 2, 3, 4, 5, 6, 7],
      rows: R1.map((r, i) => [r.k, `${fx(r.target_deg, 4)}°`, `${fx(r.realised_deg, 4)}°`, sci(r.angle_err_rad), fx(r.gain, 6),
                              `${fx(R2[i].realised_deg, 4)}°`, sci(R2[i].angle_err_rad), fx(R2[i].gain, 6)]),
    }),
    note: `Table 1 uses the Gaussian integers ${EV.rotations.table1_constants.map((c) => c.P).join(', ')} and a radius scale-down of a few signed powers of two per angle; the CORDIC-II unit combines a friend angle (7+j or 5+5j), two unscaled-radius rotations (2⁻³, 2⁻⁵), a nano rotation (2⁻⁷, 2⁻⁹) and one radius scaling.`,
  }));
}

/* ---- range ------------------------------------------------------------------------------- */
function renderRange() {
  const host = $('range-body');
  const combos = ['000', '001', '010', '011', '100', '101', '110', '111'];
  const maxR = Math.max(...OV.rows.map((r) => r.max_mr_ratio));
  const scale = 0.5;
  function heat(mode) {
    const rows = OV.rows.filter((r) => r.mode === mode);
    const head = h('tr', {}, h('th', { text: 'W \\ SS' }), combos.map((c) => h('th', { text: c })));
    const body = WS.map((w) => h('tr', {}, h('th', { text: String(w) }), combos.map((c) => {
      const r = rows.find((q) => q.w === w && q.ss.join('') === c);
      if (!r) return h('td', { class: 'cell na', text: '–', title: 'not allowed: the input does not fit with these headroom bits' });
      const t = Math.min(1, r.max_mr_ratio / scale);
      const td = h('td', { class: `cell ${t > 0.5 ? 'hi' : 'lo'}`, text: pct(r.max_mr_ratio),
        style: `background: color-mix(in oklab, var(--seq-hi) ${(t * 100).toFixed(0)}%, var(--seq-lo))`, tabindex: 0 });
      const rowsT = [{ name: 'largest CORDIC register fill', value: pct(r.max_mr_ratio, 1) }, { name: 'tightest node', value: r.tightest_node },
                     { name: 'its slack to the limit', value: `${r.min_node_slack_lsb} LSB` }];
      const head2 = `${MODE_SHORT[mode]}, W = ${w}, SS = ${c}`;
      td.addEventListener('pointermove', (ev) => tipShow(ev.clientX, ev.clientY, head2, rowsT));
      td.addEventListener('pointerleave', tipHide);
      td.addEventListener('focus', () => tipAtEl(td, head2, rowsT));
      td.addEventListener('blur', tipHide);
      return td;
    })));
    return h('div', { class: 'tw' }, h('table', { class: 'heat' }, h('thead', {}, head), h('tbody', {}, body)));
  }
  const tight = {};
  for (const r of OV.rows) tight[r.tightest_node] = (tight[r.tightest_node] || 0) + 1;
  const ctl = OV.control;
  const allTight = OV.rows.every((r) => r.min_node_slack_lsb === 0);
  const slackMin = Math.min(...OV.rows.map((r) => r.min_node_slack_lsb)), slackMax = Math.max(...OV.rows.map((r) => r.min_node_slack_lsb));
  host.append(
    h('div', { class: 'grid2' },
      card({ title: MODE_NAME.table1, sub: 'largest fill of any CORDIC register, per word length W and safe-scaling choice SS', fig: null, extra: heat('table1') }),
      card({ title: MODE_NAME.cordic2x, sub: 'same scale: 0 % to 50 % of the register range', fig: null, extra: heat('cordic2x') })),
    card({
      title: 'What was scanned',
      sub: `${OV.configs} configurations × ${int(OV.inputs_per_config)} inputs`,
      fig: null,
      extra: h('div', {},
        h('dl', { class: 'kv' },
          h('dt', { text: 'Inputs' }), h('dd', { text: OV.input_sets.join('; ') }),
          h('dt', { text: 'Result' }), h('dd', {}, status(OV.failures === 0 ? 'pass' : 'fail', OV.failures === 0 ? 'no flow-graph node and no CORDIC register leaves its range' : `${OV.failures} configurations overflow`)),
          h('dt', { text: 'Tightest node' }), h('dd', { text: `${allTight ? 'at its limit exactly (slack 0 LSB) in every configuration' : `slack between ${slackMin} and ${slackMax} LSB`}: ${Object.entries(tight).map(([k, v]) => `${k} in ${v}`).join(', ')}` }),
          h('dt', { text: 'Largest CORDIC fill' }), h('dd', { text: `${pct(maxR, 1)} of the register range over all ${OV.configs} configurations` }),
          h('dt', { text: 'Control' }), h('dd', {}, status(ctl.detected ? 'caught' : 'fail', `${ctl.fault}: ${ctl.nodes_out_of_range} of ${ctl.nodes_total} nodes leave the range (${ctl.config})`))),
        h('details', { style: 'margin-top:10px' }, h('summary', { text: 'CORDIC registers at W = 14, SS = 000: peak value against register limit' }),
          tableEl({ head: ['Mode', 'Register word', 'Peak', 'Limit', 'Fill'], num: [2, 3, 4],
                    rows: OV.mr_words_w14.map((r) => [MODE_SHORT[r.mode], r.word, int(r.peak), int(r.limit), pct(r.ratio, 1)]) }))),
      note: `This is a test, not a formal proof. Every node is a linear function of the input up to rounding, so its extremes lie at or next to the corners of the input cube; the scan concentrates on the corners and their neighbours and adds random inputs. ${allTight ? `The word lengths are tight rather than padded: the tightest node reaches its limit exactly in every configuration, and aligning the input one bit higher (the control) makes ${ctl.nodes_out_of_range} of ${ctl.nodes_total} nodes leave their range.` : ''}`,
    }));
}

/* ---- schedule ---------------------------------------------------------------------------- */
function renderSchedule() {
  const host = $('schedule-body');
  const sj = SCHED_JSON, T = Sched.timeline(sj), t0 = sj.t0, P = Sched.PERIOD;
  const NB = 3, END = Math.max(Math.max(...T.map((o) => o.end)), t0 + 1 + P) + (NB - 1) * P;
  const LANES = ['input bus', 'BF0', 'BF1', 'CORDIC stage A', 'CORDIC stage B', 'output bus'];

  const gantt = (W) => {
    const m = { l: 104, r: 12, t: 50, b: 10 }, rowH = 28, H = m.t + LANES.length * rowH + m.b;
    const sx = lin(0, END, m.l, W - m.r), cw = (W - m.l - m.r) / END;
    const svg = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Operations of three consecutive blocks on the processing elements' });
    for (let c = 0; c <= END; c += 2) {
      svg.append(sv('line', { x1: sx(c), x2: sx(c), y1: m.t - 4, y2: H - m.b, class: 'gridline' }));
      if (c !== t0 + 1) svg.append(sv('text', { x: sx(c), y: m.t - 10, 'text-anchor': 'middle', class: 'chart-text', text: String(c) }));
    }
    svg.append(sv('text', { x: m.l - 8, y: m.t - 10, 'text-anchor': 'end', class: 'chart-text', text: 'clock' }));
    LANES.forEach((l, i) => svg.append(sv('text', { x: m.l - 8, y: m.t + i * rowH + rowH / 2 + 4, 'text-anchor': 'end', class: 'chart-text ink', text: l })));
    const bar = (lane, c, label, solid, kls, head, rows) => {
      const x = sx(c) + 1, w = Math.max(2, cw - 2), y = m.t + lane * rowH + 3;
      const g = sv('g', { class: `op ${kls}${solid ? '' : ' ghost'}`, tabindex: 0, 'aria-label': `${head}: ${rows.map((r) => `${r.name} ${r.value}`).join(', ')}` });
      g.append(sv('rect', { x, y, width: w, height: rowH - 6, rx: 3 }));
      if (w >= 15) g.append(sv('text', { x: x + w / 2, y: y + (rowH - 6) / 2 + 4, 'text-anchor': 'middle', text: label }));
      g.addEventListener('pointermove', (ev) => tipShow(ev.clientX, ev.clientY, head, rows));
      g.addEventListener('pointerleave', tipHide);
      g.addEventListener('focus', () => tipAtEl(g, head, rows));
      g.addEventListener('blur', tipHide);
      svg.append(g);
    };
    for (let b = NB - 1; b >= 0; b--) {
      const off = b * P, solid = b === 0, blk = `block ${b === 0 ? 'n' : 'n+' + b}`;
      for (let n = 0; n < 8; n++) {
        bar(0, off + n, `x${n}`, solid, 'io', `x${n} on the input bus · ${blk}`,
            [{ name: 'clock', value: String(off + n) }, { name: n % 2 ? 'odd sample' : 'even sample', value: n % 2 ? 'used directly' : 'stored in IB' }]);
        bar(5, off + t0 + 1 + n, `Y${n}`, solid, 'io', `Y${n} on the output bus · ${blk}`, [{ name: 'valid in clock', value: String(off + t0 + 1 + n) }, { name: 'read from OB in clock', value: String(off + t0 + n) }]);
      }
      for (const o of T) {
        const rows = [{ name: 'inputs', value: o.ins.join(', ') }, { name: 'outputs', value: o.outs.join(', ') },
                      { name: 'issues at clock', value: String(off + o.start) }, { name: 'phase (clock mod 8)', value: String(o.start % P) }];
        if (o.unit === 'BF') bar(o.lane === 'BF0' ? 1 : 2, off + o.start, o.name, solid, 'bf', `${o.name} on ${o.lane} · ${blk}`, rows);
        else {
          bar(3, off + o.start, o.name, solid, 'mr', `${o.name} in CORDIC stage A · ${blk}`, rows);
          bar(4, off + o.start + 1, o.name, solid, 'mr', `${o.name} in CORDIC stage B · ${blk}`, rows);
        }
      }
    }
    svg.append(sv('line', { x1: sx(t0 + 1), x2: sx(t0 + 1), y1: 20, y2: H - m.b, class: 'cross' }),
               sv('text', { x: sx(t0 + 1) + 5, y: 16, class: 'chart-text ink b', text: `first output at clock ${t0 + 1}` }));
    return svg;
  };
  const sched1 = card({
    title: 'Three consecutive blocks on the processing elements',
    sub: 'block n solid, blocks n+1 and n+2 outlined; a new block starts every 8 clocks',
    legend: [legendKey(1, 'butterfly (1 clock)', 'box'), legendKey(2, 'CORDIC rotation: stage A, then stage B', 'box'), { text: 'input and output bus', kind: 'box', color: 'var(--ink-2)' }],
    fig: figure(gantt, 800),
    table: {
      head: ['Operation', 'Unit', 'Clocks in block n', 'Phase', 'Inputs', 'Outputs'], num: [],
      rows: [
        ['x0 … x7', 'input bus', `0 … ${P - 1}`, 'every', '–', 'x0 … x7'],
        ...[...T].sort((a, b) => a.start - b.start || a.name.localeCompare(b.name)).map((o) => [
          o.name, o.unit === 'BF' ? o.lane : 'CORDIC', o.unit === 'BF' ? String(o.start) : `${o.start} (stage A), ${o.start + 1} (stage B)`,
          String(o.start % P), o.ins.join(', '), o.outs.join(', ')]),
        ['Y0 … Y7', 'output bus', `${t0 + 1} … ${t0 + P}`, 'every', 'OB', 'Y0 … Y7'],
      ],
    },
    note: `Every lane holds at most one operation per clock, so the CORDIC unit takes one rotation per clock into stage A while the previous one is in stage B. The input bus is busy every clock from 0; from clock ${t0 + 1} the output bus delivers one coefficient per clock, in natural order (Y0 first).`,
  });

  /* modulo reservation table */
  const slots = (lane, f) => Array.from({ length: P }, (_, ph) => T.filter((o) => o.lane === lane && f(o, ph)).map((o) => o.name).join(' ') || '–');
  const issue = (o, ph) => o.start % P === ph;
  const busy = (o, ph) => (o.start + 1) % P === ph;
  const res = card({
    title: 'Modulo reservation table',
    sub: 'which operation a unit starts in each phase (clock mod 8); every operation belongs to exactly one phase',
    fig: null,
    extra: tableEl({
      head: ['Unit', ...Array.from({ length: P }, (_, i) => `phase ${i}`)], num: [],
      rows: [['BF0 starts', ...slots('BF0', issue)], ['BF1 starts', ...slots('BF1', issue)], ['CORDIC starts', ...slots('MR', issue)], ['CORDIC second clock', ...slots('MR', busy)]],
    }),
    note: `Butterfly units: ${T.filter((o) => o.unit === 'BF').length} operations in ${2 * P} slots. CORDIC unit: ${T.filter((o) => o.unit === 'MR').length} rotations in ${P} start slots; a rotation is in stage A in its start clock and in stage B in the next, so each stage is busy ${T.filter((o) => o.unit === 'MR').length} of ${P} clocks.`,
  });
  host.append(sched1, res);

  /* lifetimes */
  const vals = Object.values(sj.values);
  const producer = {}, consumer = {};
  for (const o of Sched.OPS) { producer[o[4]] = o[0]; producer[o[5]] = o[0]; consumer[o[2]] = o[0]; consumer[o[3]] = o[0]; }
  const life = (W) => {
    const m = { l: 74, r: 12, t: 28, b: 8 }, rowH = 20, hdr = 24;
    const rowsOf = Sched.BANKS.map((b) => ({ b, n: sj.nregs[b] }));
    const H = m.t + rowsOf.reduce((s, r) => s + hdr + r.n * rowH, 0) + m.b;
    const sx = lin(0, P, m.l, W - m.r), cw = (W - m.l - m.r) / P;
    const svg = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Lifetime of every stored value within the 8-cycle period' });
    for (let c = 0; c <= P; c++) {
      svg.append(sv('line', { x1: sx(c), x2: sx(c), y1: m.t - 6, y2: H - m.b, class: 'gridline' }));
      if (c < P) svg.append(sv('text', { x: sx(c + 0.5), y: m.t - 12, 'text-anchor': 'middle', class: 'chart-text', text: String(c) }));
    }
    svg.append(sv('text', { x: m.l - 8, y: 12, 'text-anchor': 'end', class: 'chart-text', text: 'phase' }));
    let y = m.t;
    for (const { b, n } of rowsOf) {
      svg.append(sv('text', { x: 4, y: y + 16, class: 'chart-text ink b', text: `${b}  ·  ${n} word${n > 1 ? 's' : ''}` }));
      y += hdr;
      for (let r = 0; r < n; r++) {
        svg.append(sv('text', { x: m.l - 8, y: y + rowH / 2 + 4, 'text-anchor': 'end', class: 'chart-text', text: `${b}[${r}]` }),
                   sv('line', { x1: m.l, x2: W - m.r, y1: y + rowH, y2: y + rowH, class: 'gridline' }));
        for (const v of vals.filter((q) => q.bank === b && q.reg === r)) {
          const len = v.last - v.avail + 1, p0 = v.avail % P;
          const segs = p0 + len <= P ? [[p0, len]] : [[p0, P - p0], [0, p0 + len - P]];
          const rows = [{ name: 'storage', value: `${b}[${r}]` }, { name: 'available at clock', value: String(v.avail) }, { name: 'last read at clock', value: String(v.last) },
                        { name: 'lives', value: `${len} clock${len > 1 ? 's' : ''}` }, { name: 'written by', value: producer[v.name] || 'input bus' }, { name: 'read by', value: consumer[v.name] || 'output bus' }];
          segs.forEach(([s0, l], k) => {
            const g = sv('g', { class: 'life', tabindex: 0, 'aria-label': `${v.name}: ${rows.map((q) => `${q.name} ${q.value}`).join(', ')}` });
            const x = sx(s0) + 1, w = l * cw - 2;
            g.append(sv('rect', { x, y: y + 2, width: w, height: rowH - 4, rx: 3 }));
            if (k === 0 && w >= 26) g.append(sv('text', { x: x + 6, y: y + rowH / 2 + 4, text: v.name }));
            g.addEventListener('pointermove', (ev) => tipShow(ev.clientX, ev.clientY, v.name, rows));
            g.addEventListener('pointerleave', tipHide);
            g.addEventListener('focus', () => tipAtEl(g, v.name, rows));
            g.addEventListener('blur', tipHide);
            svg.append(g);
          });
        }
        y += rowH;
      }
    }
    return svg;
  };
  host.append(card({
    title: 'Where every value lives',
    sub: `${vals.length} values in ${Sched.BANKS.reduce((s, b) => s + sj.nregs[b], 0)} words, drawn modulo the period; a value that wraps past phase 7 continues at phase 0`,
    fig: figure(life, 560),
    table: {
      head: ['Value', 'Storage', 'Available at clock', 'Last read at clock', 'Lives (clocks)', 'Written by', 'Read by'], num: [2, 3, 4],
      rows: [...vals].sort((a, b) => Sched.BANKS.indexOf(a.bank) - Sched.BANKS.indexOf(b.bank) || a.reg - b.reg || a.avail - b.avail)
        .map((v) => [v.name, `${v.bank}[${v.reg}]`, v.avail, v.last, v.last - v.avail + 1, producer[v.name] || 'input bus', consumer[v.name] || 'output bus']),
    },
    note: 'Two values share a word only if their bars never overlap in a row. Every value is read once and lives at most 8 clocks, so a word is rewritten before the next block needs it, and every address is a function of the 3-bit phase counter.',
  }));

  /* ports and control words */
  const maxlive = sj.maxlive;
  const fmtReg = (r) => (r[0] === 'IN' ? 'in' : `${r[0]}[${r[1]}]`);
  const ctl = sj.phase_table.map((p) => [String(p.phase), p.ib_w === null ? '–' : `IB[${p.ib_w}]`,
    ...[0, 1].map((u) => { const b = p.bf[u]; return b ? `${b.op}: ${b.src.map(fmtReg).join(', ')} → ${b.dst.map(fmtReg).join(', ')} (stage ${b.stage})` : '–'; }),
    p.mr_issue ? `${p.mr_issue.op} (k=${p.mr_issue.k}): ${p.mr_issue.src.map(fmtReg).join(', ')}` : '–',
    p.mr_done ? `${p.mr_done.op} → ${p.mr_done.dst.map(fmtReg).join(', ')}` : '–',
    p.ob_r === null ? '–' : `OB[${p.ob_r}] → Y${p.out_k}`]);
  host.append(card({
    title: 'Ports and control words',
    sub: 'the schedule file is the source of the 3-bit-phase decoders in rtl/dct8_ctrl.v and hls/src/dct8_sched.h',
    fig: null,
    extra: h('div', {},
      tableEl({ head: ['Bank', 'Words', 'Peak live values', 'Read ports', 'Write ports'], num: [1, 2, 3, 4],
                rows: [...Sched.BANKS.map((b) => [b, sj.nregs[b], maxlive[b], SCH.ports[`${b}.rd`], SCH.ports[`${b}.wr`]]),
                       { cells: ['total', Sched.BANKS.reduce((s, b) => s + sj.nregs[b], 0), '', '', ''], hl: true }] }, 'compact'),
      h('details', { style: 'margin-top:10px' }, h('summary', { text: 'Control word of each phase' }),
        tableEl({ head: ['Phase', 'IB write', 'BF0', 'BF1', 'CORDIC start', 'CORDIC result', 'OB read'], rows: ctl }))),
  }));
}

/* ---- cost -------------------------------------------------------------------------------- */
function renderCost() {
  const host = $('cost-body');
  const C = EV.cost;
  const rowsW = (mode) => C.rows.filter((r) => r.mode === mode);
  const bd = (mode) => {
    const b = C.breakdown_w14[mode];
    const tot = (o) => Object.values(o).reduce((s, v) => s + v, 0);
    return h('div', {},
      tableEl({ head: ['Operators', 'Two-input adders', 'Adder bits'], num: [1, 2],
                rows: [...Object.keys(b.adders).map((k) => [k, b.adders[k], b.adder_bits[k]]), { cells: ['total', tot(b.adders), tot(b.adder_bits)], hl: true }] }),
      tableEl({ head: ['Storage', 'Register bits'], num: [1],
                rows: [...Object.keys(b.register_bits).map((k) => [k, b.register_bits[k]]), { cells: ['total', tot(b.register_bits)], hl: true }] }));
  };
  host.append(h('div', { class: 'grid2' },
    card({ title: `${MODE_NAME.table1}, W = 14`, sub: 'counted from the RTL structure; no multipliers', fig: null, extra: bd('table1') }),
    card({ title: `${MODE_NAME.cordic2x}, W = 14`, sub: 'counted from the RTL structure; no multipliers', fig: null, extra: bd('cordic2x') })));
  host.append(card({
    title: 'Cost against word length',
    sub: `${C.basis}`,
    fig: null,
    extra: tableEl({
      head: ['W', 'Table 1 adders', 'adder bits', 'rounding +1', 'register bits', 'CORDIC-II adders', 'adder bits', 'rounding +1', 'register bits', 'memory words', 'multipliers'], num: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      rows: WS.map((w) => { const a = rowsW('table1').find((r) => r.w === w), b = rowsW('cordic2x').find((r) => r.w === w);
        return [w, a.adders, a.adder_bits, a.rounding_increments, a.register_bits, b.adders, b.adder_bits, b.rounding_increments, b.register_bits, a.memory_words, a.multipliers]; }),
    }),
  }));

  /* design space */
  const D = EV.design_space.designs;
  const front = D.filter((d) => d.front).sort((a, b) => a.adders - b.adders || a.max_err - b.max_err);
  const chosen = D.find((d) => d.chosen), t1 = D.find((d) => d.family === 'paper Table 1');
  const nxt = front.find((d) => d.adders > chosen.adders);
  const c14 = (m) => C.rows.find((r) => r.mode === m && r.w === 14).adders;
  const bfAdd = c14('table1') - t1.adders === c14('cordic2x') - chosen.adders ? c14('table1') - t1.adders : 0;
  const lo = Math.pow(10, Math.floor(Math.log10(Math.min(...D.map((d) => d.max_err))))), hi = Math.pow(10, Math.ceil(Math.log10(Math.max(...D.map((d) => d.max_err)))));
  const pt = (d, extra) => ({ x: d.adders, y: d.max_err, tip: { head: d.name, rows: [{ name: 'family', value: d.family }, { name: 'adders (rotation unit)', value: String(d.adders) }, { name: 'worst-case error', value: sci(d.max_err) + ' rad' }] }, ...extra });
  host.append(card({
    title: `Design space of the rotation unit: ${D.length} designs`,
    sub: 'adders of the rotation unit against worst-case error (angle error + gain spread + radius-scaling error)',
    legend: [{ text: 'explored design', kind: 'dot', color: 'var(--ink-2)' }, legendKey(1, 'Pareto front', 'dot'), legendKey(2, 'CORDIC-II unit used here', 'dot'), { text: 'paper Table 1', kind: 'diamond', color: 'var(--ink)' }],
    fig: figure(scatter({
      x: { min: 6, max: 34, fmt: String }, y: { min: lo, max: hi, log: true, fmt: pow10 }, xTitle: 'two-input adders in the rotation unit', yTitle: 'worst-case error (rad)', height: 360, aria: 'design space of the rotation unit',
      lines: [{ cls: 'c1', pts: front.map((d) => [d.adders, d.max_err]) }],
      points: [
        ...D.filter((d) => !d.front && !d.chosen).map((d) => pt(d, { fill: 'fg', opacity: 0.5, r: 3.5 })),
        ...front.filter((d) => !d.chosen && d !== t1).map((d) => pt(d, { fill: 'f1', r: 5, top: true })),
        pt(chosen, { fill: 'f2', r: 7, top: true, label: `CORDIC-II unit, ${chosen.adders} adders`, dx: 12, dy: -8 }),
        pt(t1, { shape: 'diamond', r: 7, top: true, label: `Table 1, ${t1.adders} adders`, dx: -12, dy: 20, anchor: 'end' }),
      ],
    })),
    table: { head: ['Design', 'Family', 'Adders', 'Worst-case error (rad)', 'Pareto', 'Used'], num: [2, 3],
             rows: [...D].sort((a, b) => a.adders - b.adders || a.max_err - b.max_err).map((d) => [d.name, d.family, d.adders, sci(d.max_err), d.front ? 'yes' : '', d.chosen ? 'yes' : '']) },
    note: `${bfAdd ? `The rotation unit alone is counted here; the processor totals of the cost table add the two butterfly datapaths (${bfAdd} adders). ` : ''}Against Table 1 the CORDIC-II unit uses ${chosen.adders - t1.adders} more adders and has ${fx(t1.max_err / chosen.max_err, 0)} times less worst-case error.${nxt ? ` Beyond it the front improves by only ${fx(100 * (1 - nxt.max_err / chosen.max_err), 0)} % (${sci(nxt.max_err)} rad at ${nxt.adders} adders).` : ''}`,
  }));

  /* 16-point */
  const d16 = EV.dct16;
  host.append(card({
    title: '16-point extension',
    sub: `${d16.config}; ${int(d16.n_vectors)} random 9-bit vectors (seed ${d16.seed}); error against the double-precision 16-point DCT`,
    fig: null,
    extra: tableEl({ head: ['Rotation set', 'rms error', 'largest error'], num: [1, 2], rows: d16.rows.map((r) => [MODE_NAME[r.mode], fx(r.rms, 4), fx(r.max, 3)]) }, 'compact'),
    note: 'The extension adds a stage-1 butterfly row, two 8-point engines and an array of CORDIC rotations with the paper’s Table 5 Gaussian integers.',
  }));
}

/* ---- hardware ---------------------------------------------------------------------------- */
function renderHardware() {
  const host = $('hardware-body');
  const hw = EV.paper.hardware, t2 = hw.table2, t4 = hw.table4;
  const pend = (t) => h('span', { class: 'pending-ink', text: t || 'pending' });
  const rows = [
    [chip('paper'), `${hw.device}, ${hw.tool}`, hw.wl, t2.dsp, t2.lut, t2.ff, t2.msps, t2.power_mw, 'paper, Table 2'],
    FPGA ? [chip('measured'), `${FPGA.device}, ${FPGA.tool}; ${FPGA.config}`, FPGA.wl, FPGA.dsp, FPGA.lut, FPGA.ff, fx(FPGA.fmax_mhz, 0), FPGA.power_mw, 'artifact/data/fpga_measured.json']
         : [chip('pending'), `${hw.device}`, pend(), pend(), pend(), pend(), pend(), pend(), 'scripts/vivado_synth.tcl'],
  ];
  host.append(card({
    title: 'Resources, throughput and power on the Artix-7 XC7A25T',
    sub: 'the proposed design at WL 14; the repository RTL takes one sample per clock, so its throughput in Msps equals its clock in MHz',
    fig: null,
    extra: h('div', {},
      tableEl({ head: ['Source', 'Device, tool', 'WL', 'DSP', 'LUT', 'FF', 'Throughput (Msps)', 'Power (mW)', 'File'], num: [2, 3, 4, 5, 6, 7], rows }),
      h('p', { class: 'note' }, h('b', { text: 'Quoted: ' }), `the first row is the paper’s Table 2; per its caption, ${hw.note}. Table 4 of the paper lists, for the proposed method, ${t4.additions} additions, ${t4.cordic_units} in its multiplication/CORDIC column, ${t4.m_b} M_B, ${t4.shifts} shifts and ${t4.muxes} MUX/DEMUX.`),
      h('p', { class: 'note' }, h('b', { text: FPGA ? 'Measured: ' : 'Pending: ' }), FPGA
        ? 'values read from the Vivado reports of this repository’s RTL.'
        : 'the synthesis flow is in the repository (scripts/vivado_synth.tcl: synthesis, place and route, utilisation, timing and power reports) and has not been run for these figures. The cells turn into measured values when artifact/data/fpga_measured.json (template: fpga_measured.template.json) is filled in and the page is rebuilt.')),
  }));
}

/* ---- reproduce --------------------------------------------------------------------------- */
function renderReproduce() {
  const host = $('reproduce-body');
  const cmds = [
    ['pip install -e "python[test]"', 'install the package and the test dependencies'],
    ['pytest -q python/tests', 'unit tests: rounding, flow graph, both rotation units, range scan, schedule, cycle models, generated files up to date'],
    ['python3 scripts/report.py > docs/results.md', 'regenerate the results report (byte-identical to the committed file)'],
    ['python3 scripts/make_artifact.py --check', 'recompute every number of this page and compare with the committed data and page'],
    ['node artifact/tests/selfcheck.js', 'the JavaScript model, schedule checker and SHA-256 against the vectors, without a browser'],
    ['make rtl hls matlab', 'Verilog (two adder styles), HLS C simulation (two header sets) and MATLAB/Octave against the same vectors'],
    ['vivado -mode batch -source scripts/vivado_synth.tcl', 'FPGA resources, timing and power (needs Vivado)'],
  ];
  const digestRows = [];
  const live = [];
  for (const n of VSETS) {
    for (const suf of Object.values(SUFFIX)) {
      const f = EV.vectors.sets[n].files[suf];
      const st = h('span', { class: 'st run' }, '…');
      live.push([st, n, suf]);
      digestRows.push([code(`${n}_${suf}`), int(f.bytes), h('span', { class: 'mono small', text: f.sha256 }), st]);
    }
  }
  for (const fn of ['manifest.json', 'schedule.json']) {
    const f = EV.vectors.files[fn], st = h('span', { class: 'st run' }, '…');
    live.push([st, null, fn]);
    digestRows.push([code(fn), int(f.bytes), h('span', { class: 'mono small', text: f.sha256 }), st]);
  }
  const env = EV.meta.environment;
  host.append(
    card({ title: 'Commands', sub: 'from the repository root', fig: null, extra: tableEl({ head: ['Command', 'What it does'], rows: cmds.map(([c, d]) => [h('span', { class: 'cmd-row' }, code(c)), d]) }) }),
    card({
      title: 'This build', fig: null,
      extra: h('div', {}, h('dl', { class: 'kv' },
        h('dt', { text: 'Source digest' }), h('dd', {}, h('span', { class: 'mono', text: EV.meta.source.sha256 }), ` (${EV.meta.source.n_files} files: python/dct8/*.py and vectors/*)`),
        h('dt', { text: 'Computed with' }), h('dd', { text: `Python ${env.python}, NumPy ${env.numpy}${env['scikit-image'] ? ', scikit-image ' + env['scikit-image'] : ''}` }),
        h('dt', { text: 'Test images' }), h('dd', { text: Object.entries(A2.images).map(([k, v]) => `${k} ${v[0]}×${v[1]}`).join(', ') }),
        h('dt', { text: 'Python cross-checks' }), h('dd', {}, h('div', {}, EV.cross_checks.map((c) => h('div', {}, status(c.ok ? 'pass' : 'fail', c.text), h('span', { class: 'muted small', text: `  ${c.detail}` }))))))),
      note: 'The digest changes with any edit of the model sources or the vectors, so a page built from other sources can be told apart. python3 scripts/make_artifact.py --check fails when evidence.json or index.html no longer match.',
    }),
    card({
      title: 'Vector files', sub: 'SHA-256 of the files embedded in this page, recomputed in the browser and compared with the digest recorded at build time', fig: null,
      extra: h('details', {}, h('summary', { text: `${digestRows.length} files` }), tableEl({ head: ['File', 'Bytes', 'SHA-256', 'Match'], num: [1], rows: digestRows })),
    }));
  return () => {
    for (const [st, n, suf] of live) {
      const ok = n ? LIVE.sets[n].digests[suf] === EV.vectors.sets[n].files[suf].sha256 : LIVE.digests[suf].got === LIVE.digests[suf].want;
      st.replaceChildren(icon(ok ? 'check' : 'cross'), ok ? 'match' : 'differs');
      st.className = `st ${ok ? 'pass' : 'fail'}`;
    }
  };
}

/* ---- theme and start --------------------------------------------------------------------- */
function setupTheme() {
  const btn = $('theme'), order = ['auto', 'light', 'dark'];
  let cur = 'auto';
  try { cur = localStorage.getItem('dct8-theme') || 'auto'; } catch (e) { /* storage unavailable */ }
  const apply = () => {
    if (cur === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.dataset.theme = cur;
    btn.textContent = `Theme: ${cur}`;
  };
  btn.addEventListener('click', () => {
    cur = order[(order.indexOf(cur) + 1) % order.length];
    try { localStorage.setItem('dct8-theme', cur); } catch (e) { /* storage unavailable */ }
    apply();
  });
  apply();
}

async function init() {
  setupTheme();
  const heroUpdate = renderHero();
  const paintClaims = renderClaims();
  const verify = renderVerify();
  renderAccuracy();
  renderRange();
  renderSchedule();
  renderCost();
  renderHardware();
  const reproUpdate = renderReproduce();
  $('foot').append(`Built from source digest ${EV.meta.source.sha256.slice(0, 12)} · `,
    h('a', { href: EV.meta.repository, rel: 'noopener' }, EV.meta.repository.replace('https://', '')), ' · ',
    h('a', { href: `https://doi.org/${EV.paper.doi}`, rel: 'noopener' }, `doi:${EV.paper.doi}`));
  const run = async () => {
    verify.prog.textContent = 'running …';
    await runLive((s) => { verify.prog.textContent = `${s} …`; });
    heroUpdate(); paintClaims(); verify.fill(); reproUpdate();
  };
  verify.btn.addEventListener('click', run);
  await run();
}
init().catch((e) => {
  document.body.dataset.live = 'fail';
  document.body.prepend(h('pre', { class: 'pending-ink', style: 'padding:12px;white-space:pre-wrap', text: `Page error: ${e && e.stack || e}` }));
  throw e;
});
})();
