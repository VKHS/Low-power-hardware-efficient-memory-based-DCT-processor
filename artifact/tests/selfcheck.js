#!/usr/bin/env node
/* Self-check of the results page, without a browser:
 *
 *   node artifact/tests/selfcheck.js
 *
 * - SHA-256 (the page's own implementation) against Node's crypto, and the digests of every
 *   vector file against artifact/data/evidence.json
 * - the JavaScript model against all 9 golden vector sets, and 8 deliberate arithmetic faults
 *   that the vectors must catch
 * - the schedule checker against vectors/schedule.json, check by check against the Python
 *   checker's results, and 10 deliberate schedule faults
 * - freshness of evidence.json (source digest recomputed here), and, if present, that index.html
 *   embeds exactly these data and requests nothing from the network
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const ART = path.join(ROOT, 'artifact');
const Sha256 = require(path.join(ART, 'src', 'sha256.js'));
const Model = require(path.join(ART, 'src', 'model.js'));
global.Model = Model;
const Sched = require(path.join(ART, 'src', 'sched.js'));

let failures = 0, total = 0;
function check(name, fn) {
  total++;
  try {
    const detail = fn();
    console.log(`  ok    ${name}${detail ? '  (' + detail + ')' : ''}`);
  } catch (e) {
    failures++;
    console.log(`  FAIL  ${name}\n        ${String(e.message || e).split('\n').join('\n        ')}`);
  }
}
const eq = (a, b, msg) => { if (a !== b) throw new Error(`${msg || 'values differ'}: ${a} !== ${b}`); };
const ok = (c, msg) => { if (!c) throw new Error(msg || 'assertion failed'); };
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

const evidence = JSON.parse(fs.readFileSync(path.join(ART, 'data', 'evidence.json'), 'utf8'));
const manifest = JSON.parse(read('vectors', 'manifest.json'));
const SUFFIX = { in: 'in.txt', out: 'out.txt', stim: 'stim.hex', expect: 'expect.hex' };
const files = {};
for (const name of Object.keys(manifest)) {
  files[name] = {};
  for (const [k, suf] of Object.entries(SUFFIX)) files[name][k] = read('vectors', `${name}_${suf}`);
}

console.log('SHA-256');
check('known answers (FIPS 180-4)', () => {
  eq(Sha256.hex(''), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
  eq(Sha256.hex('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  eq(Sha256.hex('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),
     '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
});
check('against Node crypto on lengths 0..300 and 100 000 bytes', () => {
  let seed = 12345;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed & 255; };
  const sizes = Array.from({ length: 301 }, (_, i) => i).concat([100000]);
  for (const n of sizes) {
    const b = new Uint8Array(n).map(rnd);
    eq(Sha256.digest(b), crypto.createHash('sha256').update(b).digest('hex'), `length ${n}`);
  }
  return `${sizes.length} messages`;
});
check('digests of all vector files equal evidence.json (and Node crypto)', () => {
  let n = 0;
  for (const [name, set] of Object.entries(evidence.vectors.sets)) {
    for (const [k, suf] of Object.entries(SUFFIX)) {
      const d = Sha256.hex(files[name][k]);
      eq(d, set.files[suf].sha256, `${name}_${suf}`);
      eq(d, crypto.createHash('sha256').update(files[name][k]).digest('hex'), `${name}_${suf} (crypto)`);
      n++;
    }
  }
  for (const fn of ['manifest.json', 'schedule.json']) {
    eq(Sha256.hex(read('vectors', fn)), evidence.vectors.files[fn].sha256, fn);
    n++;
  }
  return `${n} files`;
});

console.log('JavaScript model against the golden vectors');
const model = Model.make();
for (const [name, man] of Object.entries(manifest)) {
  check(name, () => {
    const res = Model.checkSet(model, man, files[name]);
    const bad = res.filter((c) => !c.ok);
    ok(bad.length === 0, bad.map((c) => `${c.id}: ${c.detail}`).join('; '));
    return res.find((c) => c.id === 'functional').detail;
  });
}
check('verdicts agree with the Python run recorded in evidence.json', () => {
  for (const [name, man] of Object.entries(manifest)) {
    const res = Model.checkSet(model, man, files[name]);
    const e = evidence.vectors.sets[name];
    eq(res.find((c) => c.id === 'functional').ok, e.functional_ok, name);
    eq(res.find((c) => c.id === 'expect-hex').ok, e.hex_ok, name);
  }
});

const clone = (o) => JSON.parse(JSON.stringify(o));
const D = Model.DEFAULT_TABLES;
const withT1P = (() => { const t = clone(D.T1_P); t[1] = [10, 3]; return t; })();
const withT1K = (() => { const t = clone(D.T1_K); t[2] = t[2].slice(0, 3); return t; })();
const withCtrl = (() => { const t = clone(D.CTRL); t[2][4] = 0; return t; })();
const withRs = (() => { const t = clone(D.RS_TERMS); t[4][1] = 1; return t; })();
const FAULTS = [
  ['safe-scaling unit rounds half to even', { ssRound: Model.rne }],
  ['safe-scaling unit rounds half up', { ssRound: Model.rnd }],
  ['safe-scaling unit truncates', { ssRound: (z, s) => z >> s }],
  ['Table 1: P1 = 10+j3 instead of 10+j2', { T1_P: withT1P }],
  ['Table 1: K2 loses its last term', { T1_K: withT1K }],
  ['CORDIC-II: nano term n9 of angle 2 removed', { CTRL: withCtrl }],
  ['CORDIC-II: radius scaling, sign of the last term flipped', { RS_TERMS: withRs }],
  ['CORDIC-II: friend-angle shift 2 instead of 3', { FA_SHIFT: 2 }],
];
console.log('Deliberate arithmetic faults (each must be caught by at least one vector set)');
const caughtBy = [];
for (const [name, over] of FAULTS) {
  check(name, () => {
    const m = Model.make(over), caught = [];
    for (const [set, man] of Object.entries(manifest)) {
      let res;
      try { res = Model.checkSet(m, man, files[set]); } catch (e) { caught.push(set); continue; }
      if (res.some((c) => !c.ok)) caught.push(set);
    }
    caughtBy.push(caught);
    ok(caught.length > 0, 'no vector set noticed the fault');
    return `${caught.length} of ${Object.keys(manifest).length} sets fail`;
  });
}
check('each fault is noticed by exactly the sets that exercise the element it changes', () => {
  const sets = Object.keys(manifest), lossy = {};
  for (const set of sets) {
    let n = 0;
    const m = Model.make({ ssRound: (z, s) => { if (s >= 1 && (z & ((1 << s) - 1)) !== 0) n++; return Model.rno(z, s); } });
    Model.checkSet(m, manifest[set], files[set]);
    lossy[set] = n;
  }
  const exercised = {
    ss: sets.filter((s) => lossy[s] > 0),
    t1: sets.filter((s) => manifest[s].mr_mode === 'table1'),
    c2: sets.filter((s) => manifest[s].mr_mode === 'cordic2x'),
  };
  const kinds = ['ss', 'ss', 'ss', 't1', 't1', 'c2', 'c2', 'c2'];
  kinds.forEach((k, i) => eq(JSON.stringify([...caughtBy[i]].sort()), JSON.stringify([...exercised[k]].sort()), FAULTS[i][0]));
  return `rounding faults: ${exercised.ss.length} sets; Table 1: ${exercised.t1.length}; CORDIC-II: ${exercised.c2.length}`;
});
check('a single flipped bit in an expected word is caught', () => {
  const man = manifest.dct8_t1_w14, f = clone(files.dct8_t1_w14);
  const words = f.expect.split('\n');
  words[100] = (parseInt(words[100], 16) ^ 1).toString(16).padStart(words[100].length, '0');
  f.expect = words.join('\n');
  ok(!Model.checkSet(model, man, f).find((c) => c.id === 'expect-hex').ok);
});
check('a changed input sample is caught by the stimulus check', () => {
  const man = manifest.dct8_t1_w14, f = clone(files.dct8_t1_w14);
  f.in = f.in.replace(/^-128 /, '-127 ');
  ok(!Model.checkSet(model, man, f).find((c) => c.id === 'stimulus').ok);
});

console.log('Schedule');
const sj = JSON.parse(read('vectors', 'schedule.json'));
sj.ports = evidence.schedule.ports;
sj.utilisation = evidence.schedule.utilisation;
check('all 9 checks pass on vectors/schedule.json', () => {
  const res = Sched.check(sj);
  const bad = res.filter((c) => !c.ok);
  ok(res.length === 9 && bad.length === 0, bad.map((c) => `${c.id}: ${c.detail}`).join('; '));
  return `${res.length} checks`;
});
check('identical to the Python checker (id, verdict, wording, detail)', () => {
  const js = Sched.check(sj), py = evidence.schedule.checks;
  eq(js.length, py.length);
  js.forEach((c, i) => eq(JSON.stringify(c), JSON.stringify(py[i]), c.id));
});
check('the 10 deliberate faults are caught, identically to Python', () => {
  const js = Sched.controls(sj), py = evidence.schedule.controls;
  eq(js.length, py.length);
  js.forEach((c, i) => { ok(c.detected, c.fault); eq(JSON.stringify(c), JSON.stringify(py[i]), c.fault); });
});
check('first output cycle in the manifest equals t0 + 1 for every 1-D set', () => {
  for (const [n, m] of Object.entries(manifest)) if (m.kind === 'dct8') eq(m.first_out_cycle, sj.t0 + 1, n);
});

console.log('Evidence data');
function sourceDigest() {
  const h = crypto.createHash('sha256');
  const dirs = [['python', 'dct8'], ['vectors']];
  let n = 0;
  for (const d of dirs) {
    const names = fs.readdirSync(path.join(ROOT, ...d)).filter((f) => (d[0] === 'python' ? f.endsWith('.py') : true)).sort();
    for (const f of names) {
      const full = path.join(ROOT, ...d, f);
      if (!fs.statSync(full).isFile()) continue;
      const rel = [...d, f].join('/');
      h.update(`${rel}:${crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex')}\n`);
      n++;
    }
  }
  return { sha256: h.digest('hex'), n };
}
check('evidence.json was generated from the current sources and vectors', () => {
  const s = sourceDigest();
  eq(s.n, evidence.meta.source.n_files, 'number of files');
  eq(s.sha256, evidence.meta.source.sha256, 'source digest (run: python3 scripts/make_artifact.py)');
  return `digest ${s.sha256.slice(0, 12)}, ${s.n} files`;
});
check('every cross-check of the Python run passed', () => {
  const bad = evidence.cross_checks.filter((c) => !c.ok);
  ok(bad.length === 0, bad.map((c) => c.id).join(', '));
  return `${evidence.cross_checks.length} checks`;
});
check('no claim is marked failed; every claim has a basis, evidence and a command', () => {
  const kinds = new Set(['built', 'ci', 'paper', 'pending']);
  for (const c of evidence.claims) {
    ok(kinds.has(c.basis), `${c.id}: basis ${c.basis}`);
    ok(c.claim && c.evidence && c.reproduce, `${c.id}: incomplete`);
  }
  return `${evidence.claims.length} claims`;
});

const pagePath = process.argv[2] || path.join(ART, 'index.html');
if (fs.existsSync(pagePath)) {
  console.log('Page');
  const html = fs.readFileSync(pagePath, 'utf8');
  const blob = (id) => {
    const m = html.match(new RegExp(`<script type="application/json" id="${id}">([\\s\\S]*?)</script>`));
    if (!m) throw new Error(`no <script id="${id}">`);
    return JSON.parse(m[1]);
  };
  check('embedded evidence equals artifact/data/evidence.json', () => {
    eq(JSON.stringify(blob('evidence')), JSON.stringify(evidence));
  });
  check('embedded vector files equal vectors/', () => {
    const v = blob('vectors');
    eq(v['manifest.json'], read('vectors', 'manifest.json'));
    eq(v['schedule.json'], read('vectors', 'schedule.json'));
    for (const name of Object.keys(manifest)) for (const k of Object.keys(SUFFIX)) eq(v.sets[name][k], files[name][k], `${name}.${k}`);
  });
  check('the page requests nothing from the network', () => {
    const code = html.replace(/<script type="application\/json"[\s\S]*?<\/script>/g, '');
    const bad = [];
    for (const re of [/<script[^>]*\ssrc=/i, /<link[^>]*\shref=/i, /<img[^>]*\ssrc=["']?https?:/i, /<iframe/i,
                      /@import/i, /url\(\s*["']?(https?:)?\/\//i, /\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/,
                      /navigator\.sendBeacon/, /\bimport\s*\(/]) {
      if (re.test(code)) bad.push(String(re));
    }
    ok(bad.length === 0, bad.join(', '));
    return `${(html.length / 1024).toFixed(0)} KiB`;
  });
}

console.log(`\n${total - failures}/${total} checks passed`);
process.exit(failures ? 1 : 0);
