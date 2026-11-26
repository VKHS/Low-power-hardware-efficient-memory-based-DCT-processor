"""Golden test vectors shared by the RTL, HLS and MATLAB test benches.

For every configuration ``<name>`` the generator writes into ``vectors/``:

``dct8_<name>_stim.hex``    one line per clock: ``{in_valid, in_data}`` (B_IN+1 bits)
``dct8_<name>_expect.hex``  one line per valid output word (W bits, in order)
``dct8_<name>_in.txt``      one valid block per line, 8 decimal inputs
``dct8_<name>_out.txt``     the matching 8 decimal outputs Y_0..Y_7
``manifest.json``           parameters, counts and the expected first-output cycle

and the same for the 2-D processor (``dct2d_<name>_*``, 64 values per line).
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from . import dct2d, machine, processor
from .fixedpoint import to_hex

CONFIGS_1D = {
    "t1_w14": processor.Config(b_in=8, w=14, guard=3, ss=(0, 0, 0), mr_mode="table1"),
    "c2_w14": processor.Config(b_in=8, w=14, guard=3, ss=(0, 0, 0), mr_mode="cordic2x"),
    "t1_w10ss": processor.Config(b_in=8, w=10, guard=3, ss=(1, 1, 1), mr_mode="table1"),
    "c2_w12ss": processor.Config(b_in=8, w=12, guard=2, ss=(0, 1, 0), mr_mode="cordic2x"),
    # WL = 8 with 8-bit inputs: no fractional bit at all (F = 0), every SS unit active
    "t1_w8ss": processor.Config(b_in=8, w=8, guard=3, ss=(1, 1, 1), mr_mode="table1"),
}
CONFIGS_2D = {
    "t1": dct2d.Config2D(row=processor.Config(8, 14, 3, (0, 0, 0), "table1"),
                         col=processor.Config(14, 16, 3, (1, 1, 1), "table1")),
    "c2": dct2d.Config2D(row=processor.Config(8, 14, 3, (0, 0, 0), "cordic2x"),
                         col=processor.Config(14, 16, 3, (1, 1, 1), "cordic2x")),
    # two fractional output bits (OUT_SHIFT = 3)
    "c2_f2": dct2d.Config2D(row=processor.Config(8, 14, 3, (0, 0, 0), "cordic2x"),
                            col=processor.Config(14, 16, 3, (1, 1, 1), "cordic2x"),
                            out_w=14, out_frac=2),
    # uniform 10-bit word length in both passes (OUT_SHIFT = -1: exact left shift)
    "t1_w10": dct2d.Config2D(row=processor.Config(8, 10, 3, (1, 1, 1), "table1"),
                             col=processor.Config(10, 10, 3, (1, 1, 1), "table1")),
}


def _params_1d(cfg: processor.Config) -> dict:
    return {"B_IN": cfg.b_in, "W": cfg.w, "G": cfg.guard, "SS1": cfg.ss[0], "SS2": cfg.ss[1],
            "SS3": cfg.ss[2], "MR_MODE": cfg.mode_bit}
GAP_BLOCKS = (5, 6, 40)


def _test_image() -> np.ndarray:
    try:
        from skimage import data
        return data.camera().astype(np.int64)
    except Exception:                                    # pragma: no cover
        yy, xx = np.mgrid[0:64, 0:64]
        return ((xx * 3 + yy * 2) % 256).astype(np.int64)


def blocks_1d(b_in: int, n_random: int = 192, seed: int = 2026) -> np.ndarray:
    lo, hi = -(1 << (b_in - 1)), (1 << (b_in - 1)) - 1
    rng = np.random.default_rng(seed)
    blks = [np.full(8, lo), np.full(8, hi), np.zeros(8, int)]
    blks += [np.array([hi if i == j else 0 for i in range(8)]) for j in range(8)]      # impulses
    blks += [np.array([lo if i == j else 0 for i in range(8)]) for j in range(8)]
    blks += [np.array([hi if i % 2 == 0 else lo for i in range(8)]),                   # Nyquist
             np.array([lo if i % 2 == 0 else hi for i in range(8)]),
             np.linspace(lo, hi, 8).round().astype(int)]
    corners = list(itertools.product((lo, hi), repeat=8))
    blks += [np.array(c) for c in corners[::4]]                                       # 64 corners
    img = _test_image()
    rows = img[200:232:4, 100:164].reshape(-1, 8)[:48]
    shift = 1 << (b_in - 1)
    blks += [np.clip(r - 128, lo, hi) if b_in <= 8 else (r - 128) * (shift // 128) for r in rows]
    blks += list(rng.integers(lo, hi + 1, (n_random, 8)))
    return np.array(blks, dtype=np.int64)


def write_1d(outdir: Path, name: str, cfg: processor.Config) -> dict:
    blks = blocks_1d(cfg.b_in)
    outs = machine.run_stream(blks, cfg, gap_blocks=GAP_BLOCKS)
    exp = np.array([processor.dct8_fixed(b, cfg) for b in blks])
    got = np.array([o.data for o in outs]).reshape(-1, 8)
    assert np.array_equal(got, exp), "cycle model disagrees with functional model"
    # clock-level stimulus (same sequence as run_stream)
    stim = []
    for i, b in enumerate(blks):
        if i in GAP_BLOCKS:
            stim += [(0, 0)] * 8
        stim += [(1, int(v)) for v in b]
    stim += [(0, 0)] * 24
    (outdir / f"dct8_{name}_stim.hex").write_text(
        "".join(to_hex((v << cfg.b_in) | (d & ((1 << cfg.b_in) - 1)), cfg.b_in + 1) + "\n"
                for v, d in stim))
    (outdir / f"dct8_{name}_expect.hex").write_text(
        "".join(to_hex(int(y), cfg.w) + "\n" for y in exp.reshape(-1)))
    (outdir / f"dct8_{name}_in.txt").write_text(
        "".join(" ".join(str(int(v)) for v in b) + "\n" for b in blks))
    (outdir / f"dct8_{name}_out.txt").write_text(
        "".join(" ".join(str(int(v)) for v in y) + "\n" for y in exp))
    return {"kind": "dct8", "params": _params_1d(cfg), "mr_mode": cfg.mr_mode,
            "derived": {"H": cfg.headroom, "F": cfg.f_in, "E": cfg.e_out},
            "n_stim": len(stim), "n_blocks": len(blks), "n_expect": int(exp.size),
            "first_out_cycle": outs[0].cycle, "gap_blocks": list(GAP_BLOCKS)}


def blocks_2d(n_img: int = 24, n_random: int = 8, seed: int = 7) -> np.ndarray:
    img = _test_image() - 128
    rng = np.random.default_rng(seed)
    blks = [np.full((8, 8), 127), np.full((8, 8), -128),
            np.array([[127 if (r + c) % 2 else -128 for c in range(8)] for r in range(8)])]
    coords = [(r, c) for r in range(96, 400, 40) for c in range(64, 448, 56)]
    for r, c in coords[:n_img]:
        blks.append(img[r:r + 8, c:c + 8])
    blks += list(rng.integers(-128, 128, (n_random, 8, 8)))
    return np.array(blks, dtype=np.int64)


def write_2d(outdir: Path, name: str, cfg: dct2d.Config2D) -> dict:
    blks = blocks_2d()
    outs, first = dct2d.run_stream_2d(blks, cfg)
    exp = np.concatenate([dct2d.dct2d_fixed(b, cfg).T.reshape(-1) for b in blks])
    assert np.array_equal(np.array(outs), exp), "2-D cycle model disagrees"
    b_in = cfg.row.b_in
    stim = [(1, int(v)) for b in blks for v in b.reshape(-1)] + [(0, 0)] * 200
    (outdir / f"dct2d_{name}_stim.hex").write_text(
        "".join(to_hex((v << b_in) | (d & ((1 << b_in) - 1)), b_in + 1) + "\n" for v, d in stim))
    (outdir / f"dct2d_{name}_expect.hex").write_text(
        "".join(to_hex(int(y), cfg.out_w) + "\n" for y in exp))
    (outdir / f"dct2d_{name}_in.txt").write_text(
        "".join(" ".join(str(int(v)) for v in b.reshape(-1)) + "\n" for b in blks))
    (outdir / f"dct2d_{name}_out.txt").write_text(
        "".join(" ".join(str(int(v)) for v in dct2d.dct2d_fixed(b, cfg).reshape(-1)) + "\n"
                for b in blks))
    return {"kind": "dct2d", "mr_mode": cfg.row.mr_mode,
            "params": {"B_IN": b_in, "W_ROW": cfg.row.w, "G_ROW": cfg.row.guard,
                       "SS1_ROW": cfg.row.ss[0], "SS2_ROW": cfg.row.ss[1], "SS3_ROW": cfg.row.ss[2],
                       "W_COL": cfg.col.w, "G_COL": cfg.col.guard,
                       "SS1_COL": cfg.col.ss[0], "SS2_COL": cfg.col.ss[1], "SS3_COL": cfg.col.ss[2],
                       "OUT_W": cfg.out_w, "OUT_FRAC": cfg.out_frac, "MR_MODE": cfg.row.mode_bit},
            "derived": {"OUT_SHIFT": cfg.out_shift},
            "n_stim": len(stim), "n_blocks": len(blks), "n_expect": int(exp.size),
            "first_out_cycle": first,
            "note": "*_out.txt holds X[u][v] row-major; the hardware emits columns (v-major)"}


def write_all(outdir: str | Path = "vectors") -> dict:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    man = {}
    for name, cfg in CONFIGS_1D.items():
        man[f"dct8_{name}"] = write_1d(outdir, name, cfg)
    for name, cfg in CONFIGS_2D.items():
        man[f"dct2d_{name}"] = write_2d(outdir, name, cfg)
    (outdir / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    return man
