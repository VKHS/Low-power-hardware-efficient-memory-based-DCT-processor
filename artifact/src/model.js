/* Second implementation of the bit-accurate DCT processor arithmetic, in JavaScript.
 *
 * It is written against the arithmetic definition (rounding primitives, flow graph, rotation
 * unit, 2-D scaling) and shares no code with python/dct8.  All tables are transcribed again
 * here.  Its job is to reproduce the committed golden vectors word for word: the page runs it
 * on load, and artifact/tests/selfcheck.js runs it on the files in vectors/.
 *
 * All values stay far below 2^31, so the 32-bit shift operators are exact.
 */
const Model = (() => {
  'use strict';

  /* ---- rounding primitives --------------------------------------------------------- */
  const rnd = (z, s) => (s === 0 ? z : (z + (1 << (s - 1))) >> s);              // half up
  const rne = (z, s) => {                                                         // half to even
    if (s === 0) return z;
    const q = z >> s, r = z - (q << s), half = 1 << (s - 1);
    return (r > half || (r === half && (q & 1))) ? q + 1 : q;
  };
  const rno = (z, s) => {                                                         // half to odd
    if (s === 0) return z;
    if (s === 1) return (z >> 1) | (z & 1);                                       // von Neumann
    const q = z >> s, r = z - (q << s), half = 1 << (s - 1);
    return r > half ? q + 1 : (r === half ? (q | 1) : q);
  };
  const wrap = (z, w) => (z << (32 - w)) >> (32 - w);                             // w-bit two's complement
  const fits = (z, w) => z >= -(1 << (w - 1)) && z < (1 << (w - 1));
  const shiftRound = (z, s) => (s >= 1 ? rne(z, s) : z << -s);
  const toHex = (z, w) => (z & ((1 << w) - 1)).toString(16).padStart((w + 3) >> 2, '0');
  const fromHex = (s, w) => wrap(parseInt(s, 16), w);

  /* ---- flow graph: [name, unit, in0, in1, out0, out1, parameter] -------------------- */
  const OPS = [
    ['S0', 'BF', 'x0', 'x1', 'L0', 'H0', 1], ['S1', 'BF', 'x2', 'x3', 'L1', 'H1', 1],
    ['S2', 'BF', 'x4', 'x5', 'L2', 'H2', 1], ['S3', 'BF', 'x6', 'x7', 'L3', 'H3', 1],
    ['T0', 'BF', 'L0', 'L1', 'LL0', 'LH0', 2], ['T1', 'BF', 'L2', 'L3', 'LL1', 'LH1', 2],
    ['T2', 'BF', 'H0', 'H1', 'HH0', 'HL0', 2], ['T3', 'BF', 'H2', 'H3', 'HH1', 'HL1', 2],
    ['U0', 'BF', 'LL0', 'LL1', 'Y0', 'D', 3], ['U1', 'BF', 'LH0', 'LH1', 'Sp', 'Dp', 3],
    ['U2', 'BF', 'HL0', 'HL1', 'Y4', 'DB', 3], ['U3', 'BF', 'HH0', 'HH1', 'SBp', 'DBp', 3],
    ['V0', 'MR', 'Sp', 'D', 'A3', 'A1', 2], ['V1', 'MR', 'SBp', 'DB', 'B3', 'B1', 2],
    ['W1', 'MR', 'B3', 'A1', 'Y7', 'Y1', 1], ['W2', 'MR', 'DBp', 'Dp', 'Y6', 'Y2', 2],
    ['W3', 'MR', 'B1', 'A3', 'Y5', 'Y3', 3],
  ];
  const OUTPUTS = ['Y0', 'Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Y6', 'Y7'];

  /* ---- rotation unit tables (paper Table 1 and the CORDIC-II unit) ------------------ */
  const DEFAULT_TABLES = {
    T1_P: { 1: [10, 2], 2: [50, 21], 3: [50, 33] },                               // a + jb
    T1_K: { 1: [[3, 1], [5, -1], [8, 1], [11, 1]],                                // [shift, sign]
            2: [[6, 1], [8, 1], [10, -1], [13, -1]],
            3: [[6, 1], [10, 1], [13, 1], [15, -1]] },
    CTRL: { 1: [0, 0, 1, -1, 0], 2: [0, 1, 0, 0, 1], 3: [1, -1, 1, -1, -1] },     // f, s3, s5, n7, n9
    FA_SHIFT: 3,
    RS_TERMS: [[0, 1], [3, 1], [6, -1], [8, 1], [11, -1]],
    ssRound: rno,                                                                 // safe-scaling unit
  };

  function make(over) {
    const T = Object.assign({}, DEFAULT_TABLES, over || {});

    const usr = (x, y, s, k) => (s
      ? [x - rnd(x, 2 * k) - s * rnd(y, k - 1), y - rnd(y, 2 * k) + s * rnd(x, k - 1)]
      : [x + rnd(x, 2 * k), y + rnd(y, 2 * k)]);
    const csd = (x, terms) => terms.reduce((acc, [sh, sg]) => acc + sg * (sh === 0 ? x : rnd(x, sh)), 0);

    function stageA(u, v, k, guard, mode) {
      const x0 = u << guard, y0 = v << guard;
      if (mode === 'table1') {
        const [a, b] = T.T1_P[k];
        return [a * x0 - b * y0, b * x0 + a * y0];
      }
      const [f, s3] = T.CTRL[k];
      const x1 = f ? rnd(5 * (x0 - y0), T.FA_SHIFT) : rnd(7 * x0 - y0, T.FA_SHIFT);
      const y1 = f ? rnd(5 * (x0 + y0), T.FA_SHIFT) : rnd(x0 + 7 * y0, T.FA_SHIFT);
      return usr(x1, y1, s3, 3);
    }
    function stageB(x, y, k, guard, mode) {
      if (mode === 'table1') return [rne(csd(x, T.T1_K[k]), guard), rne(csd(y, T.T1_K[k]), guard)];
      const [, , s5, n7, n9] = T.CTRL[k];
      const [x3, y3] = usr(x, y, s5, 5);
      const x4 = x3 - n7 * rnd(y3, 7) - n9 * rnd(y3, 9);
      const y4 = y3 + n7 * rnd(x3, 7) + n9 * rnd(x3, 9);
      return [rne(csd(x4, T.RS_TERMS), guard), rne(csd(y4, T.RS_TERMS), guard)];
    }
    const rotate = (u, v, k, guard, mode) => {
      const [xa, ya] = stageA(u, v, k, guard, mode);
      return stageB(xa, ya, k, guard, mode);
    };

    /* One 8-point block: x = 8 integers, cfg = {bIn, w, guard, ss:[a,b,c], mode} */
    function dct8(x, cfg) {
      const sum = cfg.ss[0] + cfg.ss[1] + cfg.ss[2];
      const f = cfg.w - cfg.bIn - (3 - sum);
      const val = {};
      for (let n = 0; n < 8; n++) {
        if (!fits(x[n], cfg.bIn)) throw new Error(`input ${x[n]} does not fit in ${cfg.bIn} bits`);
        val['x' + n] = x[n] << f;
      }
      for (const [, unit, i0, i1, o0, o1, par] of OPS) {
        const p = val[i0], q = val[i1];
        if (unit === 'BF') {
          const s = cfg.ss[par - 1];
          val[o0] = wrap(T.ssRound(p + q, s), cfg.w);
          val[o1] = wrap(T.ssRound(p - q, s), cfg.w);
        } else {
          const [u, v] = rotate(p, q, par, cfg.guard, cfg.mode);
          val[o0] = wrap(u, cfg.w);
          val[o1] = wrap(v, cfg.w);
        }
      }
      return OUTPUTS.map((y) => val[y]);
    }

    /* 8x8 block, row-major in, X[u][v] row-major out */
    function dct2d(block, c) {
      const yr = [];                                                              // [r][v]
      for (let r = 0; r < 8; r++) yr.push(dct8(block.slice(8 * r, 8 * r + 8), c.row));
      const yc = [];                                                              // [v][u]
      for (let v = 0; v < 8; v++) yc.push(dct8(yr.map((row) => row[v]), c.col));
      const shift = eOut(c.row) + eOut(c.col) + 3 - c.outFrac;
      const out = new Array(64);
      for (let u = 0; u < 8; u++) {
        for (let v = 0; v < 8; v++) out[8 * u + v] = wrap(shiftRound(yc[v][u], shift), c.outW);
      }
      return out;
    }
    return { dct8, dct2d, rotate, stageA, stageB };
  }

  /* derived quantities */
  const headroom = (c) => 3 - (c.ss[0] + c.ss[1] + c.ss[2]);
  const fIn = (c) => c.w - c.bIn - headroom(c);
  const eOut = (c) => fIn(c) - (c.ss[0] + c.ss[1] + c.ss[2]);

  /* Configurations from the manifest parameters (the generics of the RTL test benches). */
  const MODES = ['table1', 'cordic2x'];
  function cfg1d(p) {
    return { bIn: p.B_IN, w: p.W, guard: p.G, ss: [p.SS1, p.SS2, p.SS3], mode: MODES[p.MR_MODE] };
  }
  function cfg2d(p) {
    return {
      row: { bIn: p.B_IN, w: p.W_ROW, guard: p.G_ROW, ss: [p.SS1_ROW, p.SS2_ROW, p.SS3_ROW], mode: MODES[p.MR_MODE] },
      col: { bIn: p.W_ROW, w: p.W_COL, guard: p.G_COL, ss: [p.SS1_COL, p.SS2_COL, p.SS3_COL], mode: MODES[p.MR_MODE] },
      outW: p.OUT_W, outFrac: p.OUT_FRAC,
    };
  }

  /* ---- vector files -------------------------------------------------------------------- */
  const lines = (s) => s.split('\n').filter((l) => l.length > 0);
  const ints = (s) => lines(s).map((l) => l.trim().split(/\s+/).map(Number));

  /* Check one vector set with the model `m` (from make()).  `files` = {in, out, stim, expect}
     (text), `man` = its manifest entry.  Returns a list of named checks. */
  function checkSet(m, man, files) {
    const checks = [];
    const add = (id, ok, detail) => checks.push({ id, ok: !!ok, detail });
    const ins = ints(files.in), outs = ints(files.out);
    const hexes = lines(files.expect), stim = lines(files.stim);
    const is2d = man.kind === 'dct2d';
    const c = is2d ? cfg2d(man.params) : cfg1d(man.params);
    const bIn = is2d ? c.row.bIn : c.bIn;
    const outW = is2d ? c.outW : c.w;

    /* derived constants against the manifest */
    if (is2d) {
      add('derived', man.derived.OUT_SHIFT === eOut(c.row) + eOut(c.col) + 3 - c.outFrac,
          `OUT_SHIFT ${eOut(c.row) + eOut(c.col) + 3 - c.outFrac}`);
    } else {
      add('derived', man.derived.H === headroom(c) && man.derived.F === fIn(c) && man.derived.E === eOut(c),
          `H ${headroom(c)}, F ${fIn(c)}, E ${eOut(c)}`);
    }

    /* the stimulus file: valid samples, in order, are the input blocks */
    const vbit = 1 << bIn, valid = [];
    for (const h of stim) {
      const z = parseInt(h, 16);
      if (z & vbit) valid.push(wrap(z & (vbit - 1), bIn));
    }
    const flat = ins.reduce((a, r) => a.concat(r), []);
    add('stimulus', valid.length === flat.length && valid.every((v, i) => v === flat[i]),
        `${stim.length} clocks, ${valid.length} valid samples`);

    /* the model against the expected outputs */
    let bad = 0;
    const words = [];
    for (let b = 0; b < ins.length; b++) {
      const y = is2d ? m.dct2d(ins[b], c) : m.dct8(ins[b], c);
      for (let i = 0; i < y.length; i++) if (y[i] !== outs[b][i]) bad++;
      if (is2d) {                                                                 // hardware order: v-major
        for (let v = 0; v < 8; v++) for (let u = 0; u < 8; u++) words.push(y[8 * u + v]);
      } else {
        for (const v of y) words.push(v);
      }
    }
    add('functional', bad === 0, `${ins.length} blocks, ${words.length} words, ${bad} differ`);
    const hexOk = hexes.length === words.length && hexes.every((h, i) => fromHex(h, outW) === words[i]);
    add('expect-hex', hexOk, `${hexes.length} words of ${outW} bits`);
    add('counts', ins.length === man.n_blocks && hexes.length === man.n_expect && stim.length === man.n_stim,
        `${ins.length} blocks, ${stim.length} clocks, ${hexes.length} words`);
    return checks;
  }

  return { make, rnd, rne, rno, wrap, fits, shiftRound, toHex, fromHex, OPS, OUTPUTS, DEFAULT_TABLES,
           cfg1d, cfg2d, headroom, fIn, eOut, checkSet, lines, ints, MODES };
})();
if (typeof module !== 'undefined') module.exports = Model;
