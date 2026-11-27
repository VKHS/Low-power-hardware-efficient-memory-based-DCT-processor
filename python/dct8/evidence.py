"""Evidence behind the repository's claims.

``collect()`` computes every number shown by the results page ``artifact/index.html``
from the bit-accurate models, the golden vectors and the modulo schedule; nothing is
typed in by hand except the values quoted from the paper (``PAPER``), which are marked
as such.  ``scripts/make_artifact.py`` writes the result to ``artifact/data/evidence.json``
and assembles the page.

The module also re-derives a few things by a second route so that a wrong number cannot
pass unnoticed: the reference DCT from its textbook definition and from an FFT, the
schedule constraints from the published schedule alone (:func:`check_schedule`, mirrored
in ``artifact/src/sched.js``), the overflow margins on a larger input set than the unit
tests use, and the accuracy limit of each rotation set from a floating-point model.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import sys
from pathlib import Path

import numpy as np

from . import analysis as A
from . import cordic2, cost, dct2d, flowgraph, machine, processor, reference, scalable, schedule
from . import vectors as V
from .fixedpoint import from_hex, rno
from .processor import Config

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 1
PERIOD = schedule.PERIOD
W_RANGE = range(8, 17)

# ---------------------------------------------------------------------------------
# Values quoted from the paper (J. Real-Time Image Process. 19:1105-1121, 2022).
# They are not measured here.
# ---------------------------------------------------------------------------------
PAPER = {
    "citation": "A. Khalili Sadaghiani and B. Forouzandeh, Low-power hardware-efficient "
                "memory-based DCT processor, J. Real-Time Image Process. 19:1105-1121, 2022",
    "doi": "10.1007/s11554-022-01243-x",
    "table3": {
        "caption": "Average PSNR results of B-100 dataset test-images for 8-point DCT "
                   "(without compression)",
        "dataset": "BSD-100 (B-100), 100 images",
        "reference": "IEEE-754 64-bit floating point 2-D DCT",
        "format_stated": False,       # the paper gives WL only, not the integer/fraction split
        "wl": [16, 14, 12, 10, 8],
        "rows": {
            "[16]": [56.40, 43.09, 32.09, 16.31, 5.38],
            "[17]": [56.26, 42.45, 31.95, 16.36, 5.25],
            "[18]": [56.32, 42.82, 32.12, 16.30, 5.24],
            "[19]": [56.14, 42.16, 32.00, 16.16, 5.16],
            "[20]": [56.27, 42.73, 32.05, 16.43, 5.23],
            "[21]": [56.20, 42.49, 31.88, 16.49, 5.22],
            "[22]": [56.31, 42.23, 32.08, 16.20, 5.10],
            "[23]": [56.20, 42.59, 32.14, 16.37, 5.19],
            "[24]": [56.43, 42.75, 32.19, 16.40, 5.23],
            "Proposed": [56.51, 43.24, 32.60, 17.01, 6.02],
        },
    },
    "hardware": {
        "device": "Artix-7 XC7A25T", "tool": "Vivado 2018", "wl": 14,
        "note": "the competing designs in that table were reproduced by the authors on the same device",
        "table2": {"dsp": 0, "lut": 352, "ff": 440, "msps": 144, "power_mw": 91},
        "table4": {"additions": 25, "cordic_units": 1, "m_b": 6, "shifts": 29, "muxes": 22},
    },
}


def _f(x, nd: int = 6) -> float:
    return round(float(x), nd)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------------
def source_digest(root: Path = ROOT) -> dict:
    """Digest of everything the numbers depend on: model sources and golden vectors."""
    files = sorted((root / "python" / "dct8").glob("*.py")) + sorted((root / "vectors").iterdir())
    h, entries = hashlib.sha256(), {}
    for p in files:
        rel = p.relative_to(root).as_posix()
        d = _sha(p.read_bytes())
        entries[rel] = d
        h.update(f"{rel}:{d}\n".encode())
    return {"sha256": h.hexdigest(), "n_files": len(entries)}


def environment() -> dict:
    env = {"python": platform.python_version(), "numpy": np.__version__,
           "platform": platform.system().lower()}
    try:
        import skimage
        env["scikit-image"] = skimage.__version__
    except Exception:                                                 # pragma: no cover
        pass
    return env


# ---------------------------------------------------------------------------------
# flow graph, rotations
# ---------------------------------------------------------------------------------
def flowgraph_ops() -> list[dict]:
    return [{"name": o.name, "unit": o.unit, "ins": list(o.ins), "outs": list(o.outs),
             "param": o.param, "level": o.level} for o in flowgraph.OPS]


def rotations() -> dict:
    out = {}
    for mode in cordic2.MODES:
        out[mode] = [{"k": r.k, "target_deg": _f(r.target_deg, 6), "realised_deg": _f(r.realised_deg, 6),
                      "angle_err_rad": _f(r.angle_err_rad, 9), "gain": _f(r.gain, 9)}
                     for r in cordic2.analyze(mode)]
    out["table5"] = [{"k": r["k"], "P": r["P"], "target_deg": _f(r["target_deg"], 6),
                      "realised_deg": _f(r["realised_deg"], 6),
                      "angle_err_rad": _f(r["angle_err_rad"], 9), "gain": _f(r["gain"], 9)}
                     for r in scalable.table5_report()]
    out["table1_constants"] = [
        {"k": k, "P": f"{a}+j{b}", "radius": _f(math.hypot(a, b), 6),
         "K_terms": [[sh, sg] for sh, sg in cordic2.T1_K[k]],
         "K": _f(cordic2.k_value(cordic2.T1_K[k]), 9), "inv_radius": _f(1 / math.hypot(a, b), 9)}
        for k, (a, b) in cordic2.T1_P.items()]
    out["cordic2x_constants"] = {
        "friend_angles": ["7+j", "5+5j"], "friend_shift": cordic2.FA_SHIFT,
        "radius_terms": [[sh, sg] for sh, sg in cordic2.RS_TERMS], "radius_K": _f(cordic2.RS_K, 9),
        "ctrl": {str(k): list(v) for k, v in cordic2.CTRL.items()}}
    return out


def float_limit(mode: str, x: np.ndarray) -> float:
    """SQNR (dB) of the whole flow graph with the *realised* rotation coefficients of a mode
    in floating point: the limit that the fixed-point curve approaches as W grows."""
    coef = {k: cordic2.coefficient(k, mode) for k in cordic2.ANGLE_CODES}

    def mr(u, v, k):
        z = (u + 1j * v) * coef[k]
        return z.real, z.imag

    cols = [np.asarray(x[:, n], dtype=float) for n in range(8)]
    y = flowgraph.evaluate(cols, lambda p, q, st: (p + q, p - q), mr)
    est = np.stack(y, axis=1) / processor.SQRT8
    return A.sqnr_db(reference.dct8(np.asarray(x, float)), est)


# ---------------------------------------------------------------------------------
# accuracy
# ---------------------------------------------------------------------------------
def accuracy_1d(n: int = 20000) -> dict:
    x = A.random_inputs(n)
    ref = reference.dct8(np.asarray(x, float))
    rows = []
    for mode in cordic2.MODES:
        for w in W_RANGE:
            best, best_i = None, None
            for ss in A.valid_ss(8, w):
                cfg = Config(8, w, 3, ss, mode)
                est = processor.dct8_approx_batch(x, cfg)
                s = A.sqnr_db(ref, est)
                rows.append({"mode": mode, "w": w, "ss": list(ss), "best": False, "sqnr": _f(s),
                             "rms": _f(np.sqrt(np.mean((est - ref) ** 2))),
                             "max": _f(np.max(np.abs(est - ref))),
                             "sqnr_exact_rot": _f(A.sqnr_db(ref, A.ideal_rotation_dct(x, cfg)))})
                if best is None or s > best:
                    best, best_i = s, len(rows) - 1
            rows[best_i]["best"] = True
    per_output = {}
    for mode in cordic2.MODES:
        cfg = Config(8, 14, 3, (0, 0, 0), mode)
        est = processor.dct8_approx_batch(x, cfg)
        per_output[mode] = [_f(v) for v in np.sqrt(np.mean((est - ref) ** 2, axis=0))]
    per_output["exact_rotations"] = [
        _f(v) for v in np.sqrt(np.mean(
            (A.ideal_rotation_dct(x, Config(8, 14, 3, (0, 0, 0), "table1")) - ref) ** 2, axis=0))]
    limits = {mode: _f(float_limit(mode, x)) for mode in cordic2.MODES}
    return {"n_vectors": n, "seed": 2022, "b_in": 8, "guard": 3, "rows": rows,
            "rms_per_output_w14": per_output, "limit_sqnr_db": limits}


def accuracy_2d(images: dict) -> dict:
    sweep = A.wl_sweep_2d(W_RANGE, images)
    rows = []
    for r in sweep:
        row_cfg = Config(8, r["w"], 3, tuple(r["row_ss"]), r["mode"])
        vals = list(r["per_image"].values())
        rows.append({"mode": r["mode"], "w": r["w"], "row_ss": list(r["row_ss"]),
                     "e_row": row_cfg.e_out, "mean": _f(r["mean"]),
                     "min": _f(min(vals)), "max": _f(max(vals)),
                     "per_image": {k: _f(v) for k, v in r["per_image"].items()}})
    return {"images": {n: [int(im.shape[0]), int(im.shape[1])] for n, im in images.items()},
            "peak": 255, "rows": rows}


def compression(images: dict) -> dict:
    row, col = Config(8, 14, 3, (0, 0, 0), "table1"), Config(14, 16, 3, (1, 1, 1), "table1")
    table = A.compression_table(images, row, col)
    out = {"row": row.describe(), "col": col.describe(), "ratios": ["64:10", "64:6", "64:3", "64:1"],
           "rows": [{"image": t["image"], "ratio": t["ratio"], "psnr_hw": _f(t["psnr_hw"]),
                     "psnr_double": _f(t["psnr_float"]),
                     "abs_diff_db": _f(abs(t["psnr_hw"] - t["psnr_float"]), 6)} for t in table]}
    out["max_abs_diff_db"] = _f(max(r["abs_diff_db"] for r in out["rows"]))
    return out


def paper_alignment(acc2d: dict) -> dict:
    """Facts about the paper's Table 3 and how this repository's 2-D curve relates to it."""
    t3 = PAPER["table3"]
    rows = {k: v for k, v in t3["rows"].items()}
    spread = [round(max(v[i] for v in rows.values()) - min(v[i] for v in rows.values()), 2)
              for i in range(len(t3["wl"]))]
    prop = rows["Proposed"]
    slope = (prop[0] - prop[-1]) / (t3["wl"][0] - t3["wl"][-1])
    out = {"spread_db_per_wl": spread, "max_spread_db": max(spread),
           "paper_slope_db_per_bit": _f(slope, 3), "repo": {}}
    for mode in cordic2.MODES:
        rr = sorted((r for r in acc2d["rows"] if r["mode"] == mode), key=lambda r: r["w"])
        xs, ys = [r["w"] for r in rr], [r["mean"] for r in rr]
        slope_r = (ys[4] - ys[0]) / (xs[4] - xs[0])            # W = 8 .. 12, before saturation
        offsets = []
        for wl, p in zip(t3["wl"], prop):                       # equal-PSNR word length of the repo
            if ys[0] <= p <= ys[-1]:
                w_eq = float(np.interp(p, ys, xs))              # ys is increasing
                offsets.append({"paper_wl": wl, "paper_psnr": p, "repo_w": _f(w_eq, 2),
                                "offset_bits": _f(wl - w_eq, 2)})
        out["repo"][mode] = {"slope_db_per_bit_w8_12": _f(slope_r, 3), "equal_psnr": offsets}
    return out


# ---------------------------------------------------------------------------------
# overflow
# ---------------------------------------------------------------------------------
def near_corner_inputs(b_in: int = 8) -> np.ndarray:
    lo, hi = -(1 << (b_in - 1)), (1 << (b_in - 1)) - 1
    return np.array(list(itertools.product((lo, lo + 1, hi - 1, hi), repeat=8)), dtype=np.int64)


def overflow_control() -> dict:
    """The scan must be able to fail: the W = 14 design with its input alignment one bit too high."""
    cfg = Config(8, 14, 3, (0, 0, 0), "table1")
    lo_lim, hi_lim = -(1 << (cfg.w - 1)), (1 << (cfg.w - 1)) - 1
    xs = A.corner_inputs(cfg.b_in)
    cols = [processor.align_input(xs[:, n], cfg) * 2 for n in range(8)]
    nodes = flowgraph.evaluate_all(
        cols,
        bf=lambda p, q, st: (rno(p + q, cfg.scale(st)), rno(p - q, cfg.scale(st))),
        mr=lambda p, q, k: cordic2.mr_rotate(p, q, k, cfg.guard, cfg.mr_mode))
    bad = sorted(k for k, v in nodes.items() if int(np.min(v)) < lo_lim or int(np.max(v)) > hi_lim)
    return {"config": cfg.describe(), "fault": "input alignment one bit too high (inputs shifted left once more)",
            "inputs": "the 2^8 corners", "nodes_total": len(nodes), "nodes_out_of_range": len(bad),
            "nodes": bad, "detected": bool(bad)}


def overflow(n_random: int = 4000) -> dict:
    xs = np.vstack([near_corner_inputs(8),
                    np.random.default_rng(0).integers(-128, 128, (n_random, 8))])
    rows, words_worst, words_w14 = [], {}, {}
    for mode in cordic2.MODES:
        for w in W_RANGE:
            for ss in A.valid_ss(8, w):
                cfg = Config(8, w, 3, ss, mode)
                lo_lim, hi_lim = -(1 << (w - 1)), (1 << (w - 1)) - 1
                nb = A.node_bounds(cfg, xs=xs)
                slack = {k: min(mn - lo_lim, hi_lim - mx) for k, (mn, mx) in nb.items()}
                node = min(slack, key=lambda k: (slack[k], k))
                pk = A.mr_register_peaks(cfg, xs=xs)
                ratios = {k: p / lim for k, (p, lim) in pk.items()}
                for k, (p, lim) in pk.items():
                    cur = words_worst.setdefault((mode, k), [0.0, 0, lim])
                    if p / lim > cur[0]:
                        words_worst[(mode, k)] = [p / lim, p, lim]
                    if w == 14 and ss == (0, 0, 0):
                        words_w14[(mode, k)] = [p, lim]
                rows.append({"mode": mode, "w": w, "ss": list(ss),
                             "min_node_slack_lsb": int(min(slack.values())), "tightest_node": node,
                             "max_mr_ratio": _f(max(ratios.values())),
                             "ok": bool(all(s >= 0 for s in slack.values())
                                        and all(p <= lim for p, lim in pk.values()))})
    return {"configs": len(rows), "inputs_per_config": int(xs.shape[0]),
            "input_sets": ["4^8 = 65,536 near-corner inputs {-128, -127, 126, 127}^8 "
                           "(contains the 2^8 corners)", f"{n_random:,} random inputs (seed 0)"],
            "failures": sum(not r["ok"] for r in rows),
            "tightest_at_limit": all(r["min_node_slack_lsb"] == 0 for r in rows),
            "control": overflow_control(),
            "rows": rows,
            "mr_words_worst": [{"mode": m, "word": k, "ratio": _f(v[0]), "peak": int(v[1]),
                                "limit": int(v[2])} for (m, k), v in sorted(words_worst.items())],
            "mr_words_w14": [{"mode": m, "word": k, "peak": int(v[0]), "limit": int(v[1]),
                              "ratio": _f(v[0] / v[1])} for (m, k), v in sorted(words_w14.items())]}


# ---------------------------------------------------------------------------------
# cost, design space, 16-point
# ---------------------------------------------------------------------------------
def cost_table() -> dict:
    sch = schedule.build()
    rows = []
    for mode in cordic2.MODES:
        for w in W_RANGE:
            cfg = Config(8, w, 3, (0, 0, 0) if w >= 11 else (1, 1, 1), mode)
            c = cost.processor_cost(cfg, sch)
            rows.append({"mode": mode, "w": w, "adders": c.total_adders,
                         "adder_bits": c.total_adder_bits, "rounding_increments": c.rounding_increments,
                         "register_bits": c.total_register_bits,
                         "memory_words": sum(c.memory_words.values()), "multipliers": c.multipliers})
    breakdown = {}
    for mode in cordic2.MODES:
        c = cost.processor_cost(Config(8, 14, 3, (0, 0, 0), mode), sch)
        breakdown[mode] = {"adders": c.adders, "adder_bits": c.adder_bits,
                           "register_bits": c.register_bits, "memory_words": c.memory_words}
    return {"basis": "operators counted from the RTL structure by dct8.cost, not synthesis",
            "rows": rows, "breakdown_w14": breakdown}


def design_space() -> dict:
    designs = cordic2.explore()
    front = {id(d) for d in cordic2.pareto(designs)}
    return {"designs": [{"name": d.name, "family": d.family, "adders": d.adders,
                         "max_err": float(f"{d.max_err:.6g}"), "chosen": bool(d.chosen),
                         "front": id(d) in front} for d in designs]}


def dct16_errors() -> dict:
    x16 = np.random.default_rng(8).integers(-128, 128, (5000, 16))
    ref = scalable.dct16(x16)
    out = {"n_vectors": 5000, "seed": 8, "config": "2 x 8-point W=15 + Table 5 array", "rows": []}
    for mode in cordic2.MODES:
        e = scalable.dct16_approx(x16, Config(9, 15, 3, (0, 0, 0), mode)) - ref
        out["rows"].append({"mode": mode, "rms": _f(np.sqrt(np.mean(e ** 2))),
                            "max": _f(np.max(np.abs(e)))})
    return out


# ---------------------------------------------------------------------------------
# schedule, input/output timing
# ---------------------------------------------------------------------------------
def schedule_data() -> dict:
    sch = schedule.build()
    sj = json.loads(sch.to_json())
    sj["ports"] = schedule.port_usage(sch)
    sj["utilisation"] = {k: _f(v, 4) for k, v in schedule.utilisation(sch).items()}
    sj["latency_clocks"] = sch.t0 + 1
    sj["total_words"] = sum(sch.nregs.values())
    sj["checks"] = check_schedule(sj)
    sj["controls"] = schedule_controls(sj)
    return sj


def schedule_controls(sj: dict, ops=flowgraph.OPS) -> list[dict]:
    """Deliberate faults in a copy of the schedule; each must be caught by the named check."""
    import copy
    out: list[dict] = []

    def run(fault: str, expect: str, mutate) -> None:
        m = copy.deepcopy(sj)
        m.pop("checks", None)
        m.pop("controls", None)
        where = mutate(m)
        failed = [c["id"] for c in check_schedule(m, ops) if not c["ok"]]
        out.append({"fault": fault, "where": where, "expected": expect, "failed": failed,
                    "detected": expect in failed})

    # an operation issued one clock before its operand is ready
    def early(m):
        for o in ops:
            if any(v[0] != "x" for v in o.ins):
                trial = copy.deepcopy(m)
                trial["op_times"][o.name] -= 1
                if not next(c for c in check_schedule(trial, ops) if c["id"] == "operands")["ok"]:
                    m["op_times"][o.name] -= 1
                    return o.name
    run("an operation issues one clock before its operand is ready", "operands", early)

    # two values that are live in the same phase forced into one register
    def clash(m):
        vals = m["values"]
        occ = lambda r: {c % PERIOD for c in range(r["avail"], r["last"] + 1)}          # noqa: E731
        for a in sorted(vals):
            for b in sorted(vals):
                if a < b and vals[a]["bank"] == vals[b]["bank"] and vals[a]["reg"] != vals[b]["reg"] \
                        and occ(vals[a]) & occ(vals[b]):
                    vals[b]["reg"] = vals[a]["reg"]
                    return f"{a} and {b} in {vals[a]['bank']}[{vals[a]['reg']}]"
    run("two simultaneously live values share one register", "registers", clash)

    def set_(path, value):
        def f(m):
            d = m
            for key in path[:-1]:
                d = d[key]
            d[path[-1]] = value(d[path[-1]]) if callable(value) else value
            return "/".join(str(p) for p in path)
        return f

    run("an operation moved by one period", "lifetimes", set_(("op_times", "U0"), lambda v: v + PERIOD))
    run("a stage-1 butterfly moved to the second butterfly unit", "units", set_(("bf_units", "S0"), 1))
    run("one memory word fewer in bank BM", "words", set_(("nregs", "BM"), lambda v: v - 1))
    run("one read port fewer in bank BM", "ports", set_(("ports", "BM.rd"), lambda v: v - 1))
    run("a control word of the phase table removed", "microcode", set_(("phase_table", 3, "ob_r"), None))
    run("first output declared one clock early", "latency", set_(("t0",), lambda v: v - 1))
    run("first output declared one clock late", "latency", set_(("t0",), lambda v: v + 1))
    run("CORDIC unit utilisation misreported", "utilisation", set_(("utilisation", "CORDIC unit"), 0.5))
    return out


def check_schedule(sj: dict, ops=flowgraph.OPS) -> list[dict]:
    """Constraints of the modulo schedule, derived from the published schedule alone.

    The schedule's own scheduler is not called: lifetimes, register sharing, memory
    words, port use and the control words are re-derived from the operation times.
    ``artifact/src/sched.js`` implements the same checks for the results page.
    """
    t, units, vals, table = sj["op_times"], sj["bf_units"], sj["values"], sj["phase_table"]
    bf_lat, mr_lat = sj["bf_latency"], sj["mr_latency"]
    producer = {v: o for o in ops for v in o.outs}
    consumer = {v: o for o in ops for v in o.ins}
    lat = lambda o: bf_lat if o.unit == "BF" else mr_lat          # noqa: E731
    checks: list[dict] = []

    def add(cid, text, ok, detail):
        checks.append({"id": cid, "text": text, "ok": bool(ok), "detail": detail})

    # 1 -- operands are ready when an operation issues
    bad, total = [], 0
    for o in ops:
        for v in o.ins:
            total += 1
            if v[0] == "x":
                n = int(v[1:])
                ok = t[o.name] == n if n % 2 else t[o.name] >= n + 1       # odd samples: direct bus
            else:
                p = producer[v]
                ok = t[o.name] >= t[p.name] + lat(p)
            if not ok:
                bad.append(f"{o.name}<-{v}")
    add("operands", "every operand is ready when its operation issues", not bad,
        f"{total - len(bad)}/{total} operands" + (f"; violated: {', '.join(bad)}" if bad else ""))

    # 2 -- resource slots modulo the period
    slots: dict = {}
    for o in ops:
        slots.setdefault((o.unit, t[o.name] % PERIOD), []).append(o.name)
    bf_ok = all(len(v) <= 2 and len({units[n] for n in v}) == len(v) and set(units[n] for n in v) <= {0, 1}
                for (u, p), v in slots.items() if u == "BF")
    stage1_ok = all(units[f"S{n}"] == 0 for n in range(4))
    mr_ok = all(len(v) <= 1 for (u, p), v in slots.items() if u == "MR")
    n_bf = sum(o.unit == "BF" for o in ops)
    n_mr = sum(o.unit == "MR" for o in ops)
    add("units", "at most two butterflies and one rotation start per phase; stage 1 on the "
        "input-bypass datapath", bf_ok and stage1_ok and mr_ok,
        f"{n_bf} butterflies in {2 * PERIOD} slots, {n_mr} rotations in {PERIOD} slots")

    # 3 -- lifetimes, banks, latency
    t0 = max(t[producer[f"Y{k}"].name] + lat(producer[f"Y{k}"]) - k for k in range(8))
    exp = {}
    for n in range(0, 8, 2):
        exp[f"x{n}"] = (n + 1, t[consumer[f"x{n}"].name], "IB")
    for o in ops:
        for v in o.outs:
            last = t0 + int(v[1:]) if v[0] == "Y" else t[consumer[v].name]
            bank = "OB" if v[0] == "Y" else ("MM" if consumer[v].unit == "MR" else "BM")
            exp[v] = (t[o.name] + lat(o), last, bank)
    got = {k: (r["avail"], r["last"], r["bank"]) for k, r in vals.items()}
    longest = max(l - a + 1 for a, l, _ in exp.values())
    add("lifetimes", "every stored value is read once and lives at most one period (8 cycles)",
        got == exp and longest <= PERIOD and t0 == sj["t0"] and sj["period"] == PERIOD,
        f"{len(exp)} values, longest {longest} cycles")

    # 4 -- registers shared by values must not be occupied in the same phase
    occ = lambda a, l: sum(1 << r for r in {c % PERIOD for c in range(a, l + 1)})   # noqa: E731
    used: dict = {}
    clashes = 0
    for k, r in vals.items():
        m, key = occ(r["avail"], r["last"]), (r["bank"], r["reg"])
        clashes += bool(used.get(key, 0) & m)
        used[key] = used.get(key, 0) | m
    add("registers", "values that share a register are never live in the same phase", clashes == 0,
        f"{len(used)} registers, {clashes} clashes")

    # 5 -- memory words: registers used = peak number of live values
    live = {b: [0] * PERIOD for b in schedule.BANKS}
    for r in vals.values():
        for c in range(r["avail"], r["last"] + 1):
            live[r["bank"]][c % PERIOD] += 1
    maxlive = {b: max(v) for b, v in live.items()}
    words = {b: len({r["reg"] for r in vals.values() if r["bank"] == b}) for b in schedule.BANKS}
    contiguous = all(sorted({r["reg"] for r in vals.values() if r["bank"] == b})
                     == list(range(words[b])) for b in schedule.BANKS)
    add("words", "each bank uses exactly as many words as it has live values at its peak",
        words == maxlive == sj["nregs"] and contiguous,
        " + ".join(f"{b} {words[b]}" for b in schedule.BANKS) + f" = {sum(words.values())} words")

    # 6 -- ports per bank and phase, from lifetimes (read in the cycle of use, write one cycle before)
    rd = {b: [0] * PERIOD for b in schedule.BANKS}
    wr = {b: [0] * PERIOD for b in schedule.BANKS}
    for r in vals.values():
        rd[r["bank"]][r["last"] % PERIOD] += 1
        wr[r["bank"]][(r["avail"] - 1) % PERIOD] += 1
    ports = {f"{b}.{k}": max(v) for b in schedule.BANKS for k, v in (("rd", rd[b]), ("wr", wr[b]))}
    add("ports", "peak read and write ports per bank equal the published port budget",
        ports == sj["ports"],
        ", ".join(f"{b} {ports[b + '.rd']}R/{ports[b + '.wr']}W" for b in schedule.BANKS))

    # 7 -- control words of the 3-bit phase counter
    def reg(v):
        return [vals[v]["bank"], vals[v]["reg"]]

    exp_tab = [{"ib_w": None, "bf": [None, None], "mr_issue": None, "mr_done": None,
                "ob_r": None, "out_k": None} for _ in range(PERIOD)]
    for n in range(0, 8, 2):
        exp_tab[n]["ib_w"] = vals[f"x{n}"]["reg"]
    for o in ops:
        ph = t[o.name] % PERIOD
        if o.unit == "BF":
            src = [["IN", None] if (v[0] == "x" and int(v[1:]) % 2) else reg(v) for v in o.ins]
            exp_tab[ph]["bf"][units[o.name]] = {"op": o.name, "src": src,
                                                "dst": [reg(v) for v in o.outs], "stage": o.param}
        else:
            exp_tab[ph]["mr_issue"] = {"op": o.name, "k": o.param, "src": [reg(v) for v in o.ins]}
            exp_tab[(t[o.name] + mr_lat - 1) % PERIOD]["mr_done"] = {
                "op": o.name, "dst": [reg(v) for v in o.outs]}
    for k in range(8):
        exp_tab[(t0 + k) % PERIOD]["ob_r"] = vals[f"Y{k}"]["reg"]
        exp_tab[(t0 + k) % PERIOD]["out_k"] = k

    def norm(row):
        bf = [None if b is None else {"op": b["op"], "src": [list(s) for s in b["src"]],
                                      "dst": [list(d) for d in b["dst"]], "stage": b["stage"]}
              for b in row["bf"]]
        mi, md = row["mr_issue"], row["mr_done"]
        return {"ib_w": row["ib_w"], "bf": bf,
                "mr_issue": None if mi is None else {"op": mi["op"], "k": mi["k"],
                                                     "src": [list(s) for s in mi["src"]]},
                "mr_done": None if md is None else {"op": md["op"], "dst": [list(d) for d in md["dst"]]},
                "ob_r": row["ob_r"], "out_k": row["out_k"]}

    mismatched = [p for p in range(PERIOD) if norm(table[p]) != norm(exp_tab[p])]
    add("microcode", "the per-phase control words match the lifetimes and register assignment",
        not mismatched, f"{PERIOD} phases" + (f"; differ: {mismatched}" if mismatched else ""))

    # 8 -- outputs leave in natural order, one per clock, from the published start cycle
    avail_y = [t[producer[f"Y{k}"].name] + lat(producer[f"Y{k}"]) for k in range(8)]
    t0_pub = sj["t0"]
    ready = all(a <= t0_pub + k for k, a in enumerate(avail_y))
    tight = any(a == t0_pub + k for k, a in enumerate(avail_y))
    add("latency", "Y0..Y7 are ready in time to leave one per clock in natural order from the "
        "published start cycle, and the first output cannot leave earlier", ready and tight,
        f"first output after {t0_pub + 1} clocks")

    # 9 -- utilisation of the two processing elements
    ut = sj["utilisation"]
    add("utilisation", "butterfly unit and CORDIC unit utilisation equal the published figures",
        abs(ut["butterfly unit"] - n_bf / (2 * PERIOD)) < 1e-9 and abs(ut["CORDIC unit"] - n_mr / PERIOD) < 1e-9,
        f"butterfly unit {100 * n_bf / (2 * PERIOD):.1f} %, CORDIC unit {100 * n_mr / PERIOD:.1f} %")
    return checks


def io_timing() -> dict:
    """Input/output timing of the cycle-accurate models on a continuous stream."""
    rng = np.random.default_rng(1)
    blocks = rng.integers(-128, 128, (40, 8))
    outs = machine.run_stream(blocks, Config())
    cyc = [o.cycle for o in outs]
    t1 = {"blocks": 40, "samples_in": 40 * 8, "words_out": len(outs), "first_out_cycle": cyc[0],
          "contiguous": cyc == list(range(cyc[0], cyc[0] + len(cyc))),
          "natural_order": [o.index for o in outs] == [i % 8 for i in range(len(outs))],
          "last_flag": all(o.last == (o.index == 7) for o in outs)}
    cfg2 = V.CONFIGS_2D["t1"]
    blocks2 = V.blocks_2d()[:6]
    m = dct2d.DCT2DMachine(cfg2)
    stream = [(1, int(v)) for b in blocks2 for v in b.reshape(-1)] + [(0, 0)] * 300
    cyc2 = []
    for valid, v in stream:
        m.step(valid, v)
        if m.dout_valid:
            cyc2.append(m.cycle)
    t2 = {"blocks": len(blocks2), "samples_in": len(blocks2) * 64, "words_out": len(cyc2),
          "first_out_cycle": cyc2[0],
          "contiguous": cyc2 == list(range(cyc2[0], cyc2[0] + len(cyc2)))}
    return {"dct8": t1, "dct2d": t2}


# ---------------------------------------------------------------------------------
# golden vectors
# ---------------------------------------------------------------------------------
def vector_sets(root: Path = ROOT) -> dict:
    vdir = root / "vectors"
    man = json.loads((vdir / "manifest.json").read_text())
    sets = {}
    for name, m in man.items():
        ins = np.loadtxt(vdir / f"{name}_in.txt", dtype=np.int64, ndmin=2)
        outs = np.loadtxt(vdir / f"{name}_out.txt", dtype=np.int64, ndmin=2)
        hexes = (vdir / f"{name}_expect.hex").read_text().split()
        if m["kind"] == "dct8":
            cfg = V.CONFIGS_1D[name[len("dct8_"):]]
            func = np.array_equal(processor.dct8_fixed_batch(ins, cfg), outs)
            expect = outs.reshape(-1)
            hex_ok = [from_hex(h, cfg.w) for h in hexes] == list(expect)
            cyc = machine.run_stream(ins, cfg, gap_blocks=tuple(m["gap_blocks"]))
            cycle_ok = [o.data for o in cyc] == list(expect) and cyc[0].cycle == m["first_out_cycle"]
            cfg_text = cfg.describe()
        else:
            cfg = V.CONFIGS_2D[name[len("dct2d_"):]]
            func = np.array_equal(
                dct2d.dct2d_fixed_batch(ins.reshape(-1, 8, 8), cfg).reshape(-1, 64), outs)
            col_major = outs.reshape(-1, 8, 8).transpose(0, 2, 1).reshape(-1)
            hex_ok = [from_hex(h, cfg.out_w) for h in hexes] == list(col_major)
            got, first = dct2d.run_stream_2d(ins.reshape(-1, 8, 8), cfg)
            cycle_ok = got == list(col_major) and first == m["first_out_cycle"]
            cfg_text = cfg.describe()
        files = {}
        for suffix in ("in.txt", "out.txt", "stim.hex", "expect.hex"):
            p = vdir / f"{name}_{suffix}"
            files[suffix] = {"sha256": _sha(p.read_bytes()), "bytes": p.stat().st_size}
        sets[name] = {"kind": m["kind"], "mr_mode": m["mr_mode"], "params": m["params"],
                      "derived": m["derived"], "config": cfg_text, "blocks": int(ins.shape[0]),
                      "words": int(outs.size), "n_stim_clocks": m["n_stim"],
                      "first_out_cycle": m["first_out_cycle"],
                      "functional_ok": bool(func), "hex_ok": bool(hex_ok), "cycle_ok": bool(cycle_ok),
                      "files": files}
    top = {}
    for fn in ("manifest.json", "schedule.json"):
        p = vdir / fn
        top[fn] = {"sha256": _sha(p.read_bytes()), "bytes": p.stat().st_size}
    return {"sets": sets, "files": top}


# ---------------------------------------------------------------------------------
# second-route cross-checks
# ---------------------------------------------------------------------------------
def dct_definition(x: np.ndarray) -> np.ndarray:
    """Orthonormal DCT-II straight from the textbook sum (plain Python loops)."""
    n = len(x)
    out = []
    for k in range(n):
        s = sum(x[m] * math.cos(math.pi * (2 * m + 1) * k / (2 * n)) for m in range(n))
        out.append(s * math.sqrt((1.0 if k == 0 else 2.0) / n))
    return np.array(out)


def dct_fft(x: np.ndarray) -> np.ndarray:
    """Orthonormal DCT-II along the last axis through a 2N-point FFT (no cosine matrix)."""
    x = np.asarray(x, dtype=float)
    n = x.shape[-1]
    y = np.concatenate([x, x[..., ::-1]], axis=-1)
    z = np.fft.fft(y, axis=-1)[..., :n] * np.exp(-1j * np.pi * np.arange(n) / (2 * n))
    out = z.real / 2.0                    # = sum_m x[m] cos(pi (2m + 1) k / 2N)
    out[..., 0] *= math.sqrt(1.0 / n)
    out[..., 1:] *= math.sqrt(2.0 / n)
    return out


def cross_checks(acc1: dict, vec: dict, sch: dict, timing: dict, ovf: dict) -> list[dict]:
    checks: list[dict] = []

    def add(cid, text, ok, detail):
        checks.append({"id": cid, "text": text, "ok": bool(ok), "detail": detail})

    rng = np.random.default_rng(3)
    x = rng.integers(-128, 128, (200, 8)).astype(float)
    d1 = max(float(np.max(np.abs(dct_definition(r) - reference.dct8(r)))) for r in x)
    d2 = float(np.max(np.abs(dct_fft(x) - reference.dct8(x))))
    add("reference", "the double-precision reference DCT equals the textbook sum and an FFT-based DCT",
        d1 < 1e-9 and d2 < 1e-9, f"max difference {max(d1, d2):.1e} on 200 vectors")

    xi = rng.integers(-128, 128, (500, 8))
    exact = flowgraph.evaluate([xi[:, n].astype(float) for n in range(8)],
                               lambda p, q, st: (p + q, p - q),
                               lambda u, v, k: (u * math.cos(k * math.pi / 16) - v * math.sin(k * math.pi / 16),
                                                u * math.sin(k * math.pi / 16) + v * math.cos(k * math.pi / 16)))
    e3 = float(np.max(np.abs(np.stack(exact, axis=1) / processor.SQRT8 - reference.dct8(xi.astype(float)))))
    add("flowgraph", "the 17-operation flow graph with exact rotations reproduces the orthonormal DCT",
        e3 < 1e-9, f"max difference {e3:.1e} on 500 vectors")

    sets = vec["sets"]
    add("vectors-functional", "the functional model reproduces every expected output word",
        all(s["functional_ok"] and s["hex_ok"] for s in sets.values()),
        f"{len(sets)} sets, {sum(s['words'] for s in sets.values())} words")
    add("vectors-cycle", "the cycle-accurate models reproduce the same words with the expected "
        "latency", all(s["cycle_ok"] for s in sets.values()),
        f"{len(sets)} sets, first output at cycle " +
        "/".join(sorted({str(s['first_out_cycle']) for s in sets.values()}, key=int)))

    t1, t2 = timing["dct8"], timing["dct2d"]
    add("timing", "one coefficient per clock, in natural order, from clock 16 (8-point) and 97 (8x8)",
        t1["contiguous"] and t1["natural_order"] and t1["last_flag"] and t1["first_out_cycle"] == 16
        and t1["words_out"] == t1["samples_in"] and t2["contiguous"] and t2["first_out_cycle"] == 97
        and t2["words_out"] == t2["samples_in"],
        f"{t1['samples_in']} samples in / {t1['words_out']} words out; "
        f"{t2['samples_in']} / {t2['words_out']}")

    add("schedule", "every schedule constraint holds, re-derived from the published schedule alone",
        all(c["ok"] for c in sch["checks"]), f"{sum(c['ok'] for c in sch['checks'])}/{len(sch['checks'])} checks")

    lim = acc1["limit_sqnr_db"]
    rows = acc1["rows"]
    below = all(r["sqnr"] <= lim[r["mode"]] + 0.01 for r in rows)
    t1_w16 = [r for r in rows if r["mode"] == "table1" and r["w"] == 16 and r["best"]][0]["sqnr"]
    add("limit", "no fixed-point SQNR exceeds the floating-point limit of its rotation set, and "
        "Table 1 reaches it", below and abs(lim["table1"] - t1_w16) < 0.01,
        f"limits {lim['table1']:.2f} / {lim['cordic2x']:.2f} dB; Table 1 at W=16: {t1_w16:.2f} dB")

    add("overflow", "no node and no CORDIC register leaves its range on any tested input, and in "
        "every configuration the tightest node reaches its limit exactly",
        ovf["failures"] == 0 and ovf["tightest_at_limit"],
        f"{ovf['configs']} configurations x {ovf['inputs_per_config']:,} inputs")
    ctl = sch["controls"]
    add("controls", "each deliberate fault (10 in a copy of the schedule, 1 in the range scan) is "
        "caught by the check meant to catch it",
        all(c["detected"] for c in ctl) and ovf["control"]["detected"] and len(ctl) == 10,
        f"{sum(c['detected'] for c in ctl)}/{len(ctl)} schedule faults; range scan flags "
        f"{ovf['control']['nodes_out_of_range']} of {ovf['control']['nodes_total']} nodes")
    return checks


# ---------------------------------------------------------------------------------
# the ledger of claims
# ---------------------------------------------------------------------------------
def claims(d: dict) -> list[dict]:
    """Every claim of the repository with the way it is established.

    ``basis``: built (computed in this build), ci (checked by a CI job on every push),
    paper (quoted, not measured here), pending (needs a measurement that is not in the repo).
    ``live`` names the check the results page repeats in the browser with independent code.
    """
    a1, a2, al = d["accuracy_1d"], d["accuracy_2d"], d["paper_alignment"]
    best = lambda mode, w: [r for r in a1["rows"] if r["mode"] == mode and r["w"] == w and r["best"]][0]   # noqa: E731
    p2 = lambda mode, w: [r for r in a2["rows"] if r["mode"] == mode and r["w"] == w][0]["mean"]          # noqa: E731
    ck = {c["id"]: c for c in d["cross_checks"]}
    sch, ovf, hw, vec = d["schedule"], d["overflow"], d["paper"]["hardware"], d["vectors"]
    c14 = {r["mode"]: r for r in d["cost"]["rows"] if r["w"] == 14}
    rot = d["rotations"]
    max_err = {m: max(abs(r["angle_err_rad"]) for r in rot[m]) for m in cordic2.MODES}
    lim = a1["limit_sqnr_db"]
    w_sat = min(w for w in W_RANGE if lim["table1"] - best("table1", w)["sqnr"] < 0.01)
    gap_c2 = lim["cordic2x"] - best("cordic2x", 16)["sqnr"]
    comp = d["compression"]
    n_words = sum(s["words"] for s in vec["sets"].values())
    off = [o["offset_bits"] for m in cordic2.MODES for o in al["repo"][m]["equal_psnr"]]
    status = lambda *ids: "built" if all(ck[i]["ok"] for i in ids) else "failed"                       # noqa: E731
    return [
        {"id": "C1", "kind": "equivalence", "basis": status("vectors-functional", "vectors-cycle"),
         "live": "vectors",
         "claim": f"The functional and the cycle-accurate model reproduce all {n_words:,} expected "
                  f"words of the {len(vec['sets'])} golden vector sets.",
         "evidence": "vectors/*, python/tests/test_artifacts.py",
         "reproduce": "pytest -q python/tests/test_artifacts.py"},
        {"id": "C2", "kind": "equivalence", "basis": "ci",
         "claim": "The Verilog RTL (behavioural and carry-save/Kogge-Stone adder styles), the HLS "
                  "kernels (C simulation with the stand-in and with the official ap_int headers) and "
                  "the MATLAB/Octave model reproduce the same words.",
         "evidence": ".github/workflows/ci.yml, jobs rtl, hls-csim, octave",
         "reproduce": "make rtl hls matlab"},
        {"id": "C3", "kind": "timing", "basis": status("timing"),
         "claim": "One sample in and one coefficient out per clock, in natural order; first output "
                  f"after {sch['latency_clocks']} clocks (8-point) and "
                  f"{d['io_timing']['dct2d']['first_out_cycle']} clocks (8x8).",
         "evidence": "cycle-accurate models; RTL and HLS test benches check the latency",
         "reproduce": "pytest -q python/tests/test_machine.py"},
        {"id": "C4", "kind": "schedule", "basis": status("schedule", "controls"), "live": "schedule",
         "claim": f"12 butterflies and 5 rotations per block; butterfly unit "
                  f"{100 * sch['utilisation']['butterfly unit']:.1f} % and CORDIC unit "
                  f"{100 * sch['utilisation']['CORDIC unit']:.1f} % busy; {sch['total_words']} memory "
                  "words; every value lives at most 8 cycles, so all addresses are functions of the "
                  "3-bit phase.",
         "evidence": "vectors/schedule.json; dct8.evidence.check_schedule; artifact/src/sched.js",
         "reproduce": "pytest -q python/tests/test_schedule.py python/tests/test_evidence.py"},
        {"id": "C5", "kind": "range", "basis": status("overflow", "controls"),
         "claim": f"No node and no CORDIC register leaves its range in any of the {ovf['configs']} "
                  f"configurations (W = 8..16, every valid safe-scaling choice, both modes). Each is "
                  f"scanned with {ovf['inputs_per_config']:,} inputs: the 65,536 near-corner inputs "
                  "{-128, -127, 126, 127}^8 and 4,000 random ones. In every configuration the tightest "
                  f"node reaches its limit exactly; with the input alignment one bit too high the same "
                  f"scan flags {ovf['control']['nodes_out_of_range']} of "
                  f"{ovf['control']['nodes_total']} nodes.",
         "evidence": "dct8.analysis.node_bounds, mr_register_peaks; dct8.evidence.overflow",
         "reproduce": "python scripts/make_artifact.py"},
        {"id": "C6", "kind": "accuracy", "basis": "built",
         "claim": f"1-D SQNR ({a1['n_vectors']:,} random 8-bit vectors): Table 1 micro-rotations "
                  f"{best('table1', 14)['sqnr']:.2f} dB at W = 14 and {best('table1', 16)['sqnr']:.2f} dB at "
                  f"W = 16; CORDIC-II unit {best('cordic2x', 14)['sqnr']:.2f} dB at W = 14 and "
                  f"{best('cordic2x', 16)['sqnr']:.2f} dB at W = 16.",
         "evidence": "dct8.analysis.wl_sweep_1d", "reproduce": "python scripts/report.py"},
        {"id": "C7", "kind": "accuracy", "basis": status("limit"),
         "claim": f"The plateau is the angle and gain error of the rotation set. Run with the realised "
                  f"rotation coefficients in floating point, the flow graph gives {lim['table1']:.2f} dB "
                  f"(Table 1), which the fixed-point curve meets from W = {w_sat}, and "
                  f"{lim['cordic2x']:.2f} dB (CORDIC-II), {gap_c2:.2f} dB above the fixed-point value "
                  f"at W = 16. Largest angle error: {max_err['table1']:.2e} rad (Table 1), "
                  f"{max_err['cordic2x']:.2e} rad (CORDIC-II).",
         "evidence": "dct8.evidence.float_limit; dct8.cordic2.analyze",
         "reproduce": "python scripts/make_artifact.py"},
        {"id": "C8", "kind": "accuracy", "basis": "built",
         "claim": f"2-D PSNR against the double-precision DCT at W = 14: {p2('table1', 14):.1f} dB "
                  f"(Table 1), {p2('cordic2x', 14):.1f} dB (CORDIC-II); mean over "
                  f"{len(a2['images'])} test images.",
         "evidence": "dct8.analysis.wl_sweep_2d", "reproduce": "python scripts/report.py"},
        {"id": "C9", "kind": "accuracy", "basis": "built",
         "claim": f"Zonal compression through the bit-accurate 2-D processor (W 14/16, Table 1) stays "
                  f"within {comp['max_abs_diff_db']:.4f} dB of the double-precision DCT for every image "
                  "and ratio (64:10, 64:6, 64:3, 64:1).",
         "evidence": "dct8.analysis.compression_table", "reproduce": "python scripts/report.py"},
        {"id": "C10", "kind": "comparison", "basis": "built",
         "claim": f"Paper Table 3 (BSD-100, WL 8..16) gives its ten rows (nine methods and the proposed one) "
                  f"within {al['max_spread_db']:.2f} dB of each other at every WL, so its PSNR follows the word "
                  f"length ({al['paper_slope_db_per_bit']:.1f} dB per bit for the proposed row); "
                  + ("" if d["paper"]["table3"]["format_stated"] else "the format of that word is not stated in the paper. ")
                  + f"On this repository's word-length scale the same PSNR is reached "
                  f"{min(off):.1f} to {max(off):.1f} bits earlier (interpolated at WL "
                  f"{' and '.join(str(o['paper_wl']) for o in al['repo']['table1']['equal_psnr'])}).",
         "evidence": "paper Table 3; dct8.evidence.paper_alignment", "reproduce": "python scripts/make_artifact.py"},
        {"id": "C11", "kind": "cost", "basis": "built",
         "claim": f"Zero multipliers; two-input adders at W = 14: {c14['table1']['adders']} (Table 1), "
                  f"{c14['cordic2x']['adders']} (CORDIC-II). Counted from the RTL structure, not synthesised.",
         "evidence": "dct8.cost.processor_cost", "reproduce": "python scripts/report.py"},
        {"id": "C12", "kind": "scalability", "basis": "built",
         "claim": "The 16-point extension (two 8-point processors and a CORDIC array with the paper's "
                  f"Table 5 constants) has rms error {d['dct16']['rows'][0]['rms']:.2f} (Table 1) and "
                  f"{d['dct16']['rows'][1]['rms']:.3f} (CORDIC-II) against the double-precision DCT.",
         "evidence": "dct8.scalable.dct16_fixed", "reproduce": "python scripts/report.py"},
        {"id": "C13", "kind": "hardware", "basis": "paper",
         "claim": f"FPGA figures of the paper ({hw['device']}, {hw['tool']}, WL {hw['wl']}): "
                  f"{hw['table2']['dsp']} DSP, {hw['table2']['lut']} LUT, {hw['table2']['ff']} FF, "
                  f"{hw['table2']['msps']} Msps, {hw['table2']['power_mw']} mW.",
         "evidence": "paper Table 2 and Table 4", "reproduce": "see C14"},
        {"id": "C14", "kind": "hardware", "basis": "pending",
         "claim": "LUT, FF, maximum frequency and power of this repository's RTL on the same device.",
         "evidence": "scripts/vivado_synth.tcl, hls/run_hls.tcl",
         "reproduce": "vivado -mode batch -source scripts/vivado_synth.tcl"},
    ]


# ---------------------------------------------------------------------------------
def collect(root: Path = ROOT, log=lambda s: None) -> dict:
    """Run every measurement and return the evidence dictionary (JSON-serialisable)."""
    d: dict = {"schema": SCHEMA}
    log("meta")
    d["meta"] = {
        "title": "Low-power hardware-efficient memory-based DCT processor",
        "repository": "https://github.com/VKHS/memory-based-dct8",
        "source": source_digest(root),
        "environment": environment(),
        "commands": {"rebuild": "python scripts/make_artifact.py",
                     "verify": "python scripts/make_artifact.py --check",
                     "node": "node artifact/tests/selfcheck.js"},
    }
    d["paper"] = PAPER
    d["flowgraph"] = flowgraph_ops()
    log("rotations")
    d["rotations"] = rotations()
    log("schedule")
    d["schedule"] = schedule_data()
    log("timing")
    d["io_timing"] = io_timing()
    log("vectors")
    d["vectors"] = vector_sets(root)
    log("accuracy 1-D")
    d["accuracy_1d"] = accuracy_1d()
    log("images")
    images = A.test_images()
    log("accuracy 2-D")
    d["accuracy_2d"] = accuracy_2d(images)
    d["paper_alignment"] = paper_alignment(d["accuracy_2d"])
    log("compression")
    d["compression"] = compression(images)
    log("overflow")
    d["overflow"] = overflow()
    log("cost, design space, 16-point")
    d["cost"] = cost_table()
    d["design_space"] = design_space()
    d["dct16"] = dct16_errors()
    log("cross-checks")
    d["cross_checks"] = cross_checks(d["accuracy_1d"], d["vectors"], d["schedule"], d["io_timing"],
                                     d["overflow"])
    d["claims"] = claims(d)
    return d


def to_json(d: dict) -> str:
    return json.dumps(d, indent=1, ensure_ascii=True) + "\n"


if __name__ == "__main__":                                            # pragma: no cover
    sys.stdout.write(to_json(collect(log=lambda s: print(s, file=sys.stderr))))
