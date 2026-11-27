/* Checks of the modulo schedule (vectors/schedule.json), derived from the published schedule alone.
 *
 * The scheduler of python/dct8 is not used: lifetimes, register sharing, memory words, port use
 * and the control words are re-derived here from the operation times, and compared with what
 * the schedule file (and the README) publish.  dct8.evidence.check_schedule is the same list of
 * checks in Python; the two must agree, check by check, including the text of each result.
 */
const Sched = (() => {
  'use strict';
  const PERIOD = 8;
  const BANKS = ['IB', 'BM', 'MM', 'OB'];
  const OPS = Model_ops();

  function Model_ops() {                                    // [name, unit, in0, in1, out0, out1, param]
    return (typeof Model !== 'undefined' ? Model : require('./model.js')).OPS;
  }
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const maxOf = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity);
  const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  /* sj: parsed schedule.json plus {ports, utilisation} as published.  Returns [{id, text, ok, detail}] */
  function check(sj, ops) {
    ops = ops || OPS;
    const t = sj.op_times, units = sj.bf_units, vals = sj.values, table = sj.phase_table;
    const bfLat = sj.bf_latency, mrLat = sj.mr_latency;
    const producer = {}, consumer = {};
    for (const o of ops) { producer[o[4]] = o; producer[o[5]] = o; consumer[o[2]] = o; consumer[o[3]] = o; }
    const ins = (o) => [o[2], o[3]], outs = (o) => [o[4], o[5]];
    const lat = (o) => (o[1] === 'BF' ? bfLat : mrLat);
    const checks = [];
    const add = (id, text, ok, detail) => checks.push({ id, text, ok: !!ok, detail });

    /* 1 -- operands are ready when an operation issues */
    let bad = [], total = 0;
    for (const o of ops) for (const v of ins(o)) {
      total++;
      let ok;
      if (v[0] === 'x') {
        const n = parseInt(v.slice(1), 10);
        ok = n % 2 ? t[o[0]] === n : t[o[0]] >= n + 1;       // odd samples: direct from the bus
      } else {
        const p = producer[v];
        ok = t[o[0]] >= t[p[0]] + lat(p);
      }
      if (!ok) bad.push(`${o[0]}<-${v}`);
    }
    add('operands', 'every operand is ready when its operation issues', bad.length === 0,
        `${total - bad.length}/${total} operands` + (bad.length ? `; violated: ${bad.join(', ')}` : ''));

    /* 2 -- resource slots modulo the period */
    const slots = {};
    for (const o of ops) (slots[`${o[1]}|${((t[o[0]] % PERIOD) + PERIOD) % PERIOD}`] ||= []).push(o[0]);
    let bfOk = true, mrOk = true;
    for (const [key, v] of Object.entries(slots)) {
      if (key.startsWith('BF|')) {
        const us = new Set(v.map((n) => units[n]));
        bfOk = bfOk && v.length <= 2 && us.size === v.length && [...us].every((u) => u === 0 || u === 1);
      } else if (key.startsWith('MR|')) mrOk = mrOk && v.length <= 1;
    }
    const stage1Ok = [0, 1, 2, 3].every((n) => units['S' + n] === 0);
    const nBf = ops.filter((o) => o[1] === 'BF').length, nMr = ops.filter((o) => o[1] === 'MR').length;
    add('units', 'at most two butterflies and one rotation start per phase; stage 1 on the input-bypass datapath',
        bfOk && stage1Ok && mrOk, `${nBf} butterflies in ${2 * PERIOD} slots, ${nMr} rotations in ${PERIOD} slots`);

    /* 3 -- lifetimes, banks, latency */
    const t0 = maxOf([0, 1, 2, 3, 4, 5, 6, 7].map((k) => {
      const p = producer['Y' + k];
      return t[p[0]] + lat(p) - k;
    }));
    const exp = {};
    for (let n = 0; n < 8; n += 2) exp['x' + n] = [n + 1, t[consumer['x' + n][0]], 'IB'];
    for (const o of ops) for (const v of outs(o)) {
      const last = v[0] === 'Y' ? t0 + parseInt(v.slice(1), 10) : t[consumer[v][0]];
      const bank = v[0] === 'Y' ? 'OB' : (consumer[v][1] === 'MR' ? 'MM' : 'BM');
      exp[v] = [t[o[0]] + lat(o), last, bank];
    }
    const got = {};
    for (const [k, r] of Object.entries(vals)) got[k] = [r.avail, r.last, r.bank];
    const keys = Object.keys(exp).sort();
    const same = sameJson(keys, Object.keys(got).sort()) && keys.every((k) => sameJson(exp[k], got[k]));
    const longest = maxOf(Object.values(exp).map(([a, l]) => l - a + 1));
    add('lifetimes', 'every stored value is read once and lives at most one period (8 cycles)',
        same && longest <= PERIOD && t0 === sj.t0 && sj.period === PERIOD,
        `${keys.length} values, longest ${longest} cycles`);

    /* 4 -- registers shared by values must not be occupied in the same phase */
    const occ = (a, l) => { let m = 0; for (let c = a; c <= l; c++) m |= 1 << (((c % PERIOD) + PERIOD) % PERIOD); return m; };
    const used = {};
    let clashes = 0;
    for (const r of Object.values(vals)) {
      const m = occ(r.avail, r.last), key = `${r.bank}|${r.reg}`;
      if ((used[key] || 0) & m) clashes++;
      used[key] = (used[key] || 0) | m;
    }
    add('registers', 'values that share a register are never live in the same phase', clashes === 0,
        `${Object.keys(used).length} registers, ${clashes} clashes`);

    /* 5 -- memory words: registers used = peak number of live values */
    const live = {}, rd = {}, wr = {};
    for (const b of BANKS) { live[b] = new Array(PERIOD).fill(0); rd[b] = new Array(PERIOD).fill(0); wr[b] = new Array(PERIOD).fill(0); }
    for (const r of Object.values(vals)) {
      for (let c = r.avail; c <= r.last; c++) live[r.bank][c % PERIOD]++;
      rd[r.bank][r.last % PERIOD]++;
      wr[r.bank][(r.avail - 1 + PERIOD) % PERIOD]++;
    }
    const maxlive = {}, words = {};
    let contiguous = true;
    for (const b of BANKS) {
      maxlive[b] = maxOf(live[b]);
      const regs = [...new Set(Object.values(vals).filter((r) => r.bank === b).map((r) => r.reg))].sort((a, c) => a - c);
      words[b] = regs.length;
      contiguous = contiguous && regs.every((r, i) => r === i);
    }
    add('words', 'each bank uses exactly as many words as it has live values at its peak',
        BANKS.every((b) => words[b] === maxlive[b] && words[b] === sj.nregs[b]) && contiguous,
        BANKS.map((b) => `${b} ${words[b]}`).join(' + ') + ` = ${BANKS.reduce((s, b) => s + words[b], 0)} words`);

    /* 6 -- ports per bank and phase (read in the cycle of use, write one cycle before the value is available) */
    const ports = {};
    for (const b of BANKS) { ports[b + '.rd'] = maxOf(rd[b]); ports[b + '.wr'] = maxOf(wr[b]); }
    add('ports', 'peak read and write ports per bank equal the published port budget',
        sameJson(Object.keys(ports).sort().map((k) => [k, ports[k]]),
                 Object.keys(sj.ports || {}).sort().map((k) => [k, sj.ports[k]])),
        BANKS.map((b) => `${b} ${ports[b + '.rd']}R/${ports[b + '.wr']}W`).join(', '));

    /* 7 -- control words of the 3-bit phase counter */
    const reg = (v) => [vals[v].bank, vals[v].reg];
    const expTab = [];
    for (let p = 0; p < PERIOD; p++) expTab.push({ ib_w: null, bf: [null, null], mr_issue: null, mr_done: null, ob_r: null, out_k: null });
    for (let n = 0; n < 8; n += 2) expTab[n].ib_w = vals['x' + n].reg;
    for (const o of ops) {
      const ph = t[o[0]] % PERIOD;
      if (o[1] === 'BF') {
        const src = ins(o).map((v) => (v[0] === 'x' && parseInt(v.slice(1), 10) % 2 ? ['IN', null] : reg(v)));
        expTab[ph].bf[units[o[0]]] = { op: o[0], src, dst: outs(o).map(reg), stage: o[6] };
      } else {
        expTab[ph].mr_issue = { op: o[0], k: o[6], src: ins(o).map(reg) };
        expTab[(t[o[0]] + mrLat - 1) % PERIOD].mr_done = { op: o[0], dst: outs(o).map(reg) };
      }
    }
    for (let k = 0; k < 8; k++) { expTab[(t0 + k) % PERIOD].ob_r = vals['Y' + k].reg; expTab[(t0 + k) % PERIOD].out_k = k; }
    const norm = (row) => ({
      ib_w: row.ib_w,
      bf: row.bf.map((b) => (b === null ? null : { op: b.op, src: b.src, dst: b.dst, stage: b.stage })),
      mr_issue: row.mr_issue === null ? null : { op: row.mr_issue.op, k: row.mr_issue.k, src: row.mr_issue.src },
      mr_done: row.mr_done === null ? null : { op: row.mr_done.op, dst: row.mr_done.dst },
      ob_r: row.ob_r, out_k: row.out_k,
    });
    const mism = [];
    for (let p = 0; p < PERIOD; p++) if (!table[p] || !sameJson(norm(table[p]), norm(expTab[p]))) mism.push(p);
    add('microcode', 'the per-phase control words match the lifetimes and register assignment', mism.length === 0,
        `${PERIOD} phases` + (mism.length ? `; differ: [${mism.join(', ')}]` : ''));

    /* 8 -- outputs leave in natural order, one per clock, from the published start cycle */
    const availY = [0, 1, 2, 3, 4, 5, 6, 7].map((k) => { const p = producer['Y' + k]; return t[p[0]] + lat(p); });
    const ready = availY.every((a, k) => a <= sj.t0 + k), tight = availY.some((a, k) => a === sj.t0 + k);
    add('latency', 'Y0..Y7 are ready in time to leave one per clock in natural order from the published start cycle, and the first output cannot leave earlier',
        ready && tight, `first output after ${sj.t0 + 1} clocks`);

    /* 9 -- utilisation of the two processing elements */
    const ut = sj.utilisation || {};
    add('utilisation', 'butterfly unit and CORDIC unit utilisation equal the published figures',
        Math.abs(ut['butterfly unit'] - nBf / (2 * PERIOD)) < 1e-9 && Math.abs(ut['CORDIC unit'] - nMr / PERIOD) < 1e-9,
        `butterfly unit ${(100 * nBf / (2 * PERIOD)).toFixed(1)} %, CORDIC unit ${(100 * nMr / PERIOD).toFixed(1)} %`);
    return checks;
  }

  /* Deliberate faults in a copy of the schedule: each must be caught by the named check. */
  function controls(sj, ops) {
    ops = ops || OPS;
    const out = [];
    const run = (fault, expect, mutate) => {
      const m = clone(sj);
      delete m.checks; delete m.controls;
      const where = mutate(m);
      const failed = check(m, ops).filter((c) => !c.ok).map((c) => c.id);
      out.push({ fault, where: where === undefined ? null : where, expected: expect, failed, detected: failed.includes(expect) });
    };
    const set = (path, value) => (m) => {
      let d = m;
      for (const key of path.slice(0, -1)) d = d[key];
      const last = path[path.length - 1];
      d[last] = typeof value === 'function' ? value(d[last]) : value;
      return path.join('/');
    };
    run('an operation issues one clock before its operand is ready', 'operands', (m) => {
      for (const o of ops) {
        if ([o[2], o[3]].some((v) => v[0] !== 'x')) {
          const trial = clone(m);
          trial.op_times[o[0]] -= 1;
          if (!check(trial, ops).find((c) => c.id === 'operands').ok) { m.op_times[o[0]] -= 1; return o[0]; }
        }
      }
      return null;
    });
    run('two simultaneously live values share one register', 'registers', (m) => {
      const v = m.values;
      const occSet = (r) => { const s = new Set(); for (let c = r.avail; c <= r.last; c++) s.add(c % PERIOD); return s; };
      const names = Object.keys(v).sort();
      for (const a of names) for (const b of names) {
        if (a < b && v[a].bank === v[b].bank && v[a].reg !== v[b].reg) {
          const sa = occSet(v[a]);
          if ([...occSet(v[b])].some((x) => sa.has(x))) {
            v[b].reg = v[a].reg;
            return `${a} and ${b} in ${v[a].bank}[${v[a].reg}]`;
          }
        }
      }
      return null;
    });
    run('an operation moved by one period', 'lifetimes', set(['op_times', 'U0'], (x) => x + PERIOD));
    run('a stage-1 butterfly moved to the second butterfly unit', 'units', set(['bf_units', 'S0'], 1));
    run('one memory word fewer in bank BM', 'words', set(['nregs', 'BM'], (x) => x - 1));
    run('one read port fewer in bank BM', 'ports', set(['ports', 'BM.rd'], (x) => x - 1));
    run('a control word of the phase table removed', 'microcode', set(['phase_table', 3, 'ob_r'], null));
    run('first output declared one clock early', 'latency', set(['t0'], (x) => x - 1));
    run('first output declared one clock late', 'latency', set(['t0'], (x) => x + 1));
    run('CORDIC unit utilisation misreported', 'utilisation', set(['utilisation', 'CORDIC unit'], 0.5));
    return out;
  }

  /* Derived structure for drawing: operation intervals and value lifetimes. */
  function timeline(sj, ops) {
    ops = ops || OPS;
    const lat = (o) => (o[1] === 'BF' ? sj.bf_latency : sj.mr_latency);
    return ops.map((o) => ({ name: o[0], unit: o[1], start: sj.op_times[o[0]], end: sj.op_times[o[0]] + lat(o),
                             lane: o[1] === 'BF' ? `BF${sj.bf_units[o[0]]}` : 'MR', ins: [o[2], o[3]], outs: [o[4], o[5]] }));
  }
  return { check, controls, timeline, PERIOD, BANKS, OPS };
})();
if (typeof module !== 'undefined') module.exports = Sched;
