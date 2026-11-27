"""Accuracy and dynamic-range analysis.

* overflow checks: extreme value of every flow-graph node and of every
  register inside the central CORDIC unit over the input-cube corners,
  the near-corner inputs and random inputs;
* word-length (WL) sweeps of the 1-D processor (SQNR) and of the 2-D processor
  (PSNR against the IEEE-754 double-precision DCT);
* image experiments: reconstruction, zonal compression (64:1, 64:3, 64:6, 64:10
  as in the paper) and JPEG quantisation.

All experiments run the bit-accurate model (vectorised; identical to the RTL).
"""
from __future__ import annotations

import itertools
import math

import numpy as np

from . import cordic2, dct2d, flowgraph, processor, reference
from .fixedpoint import rno, rnd
from .processor import Config

# JPEG Annex K luminance quantisation table
JPEG_Q50 = np.array([
    [16, 11, 10, 16, 24, 40, 51, 61], [12, 12, 14, 19, 26, 58, 60, 55],
    [14, 13, 16, 24, 40, 57, 69, 56], [14, 17, 22, 29, 51, 87, 80, 62],
    [18, 22, 37, 56, 68, 109, 103, 77], [24, 35, 55, 64, 81, 104, 113, 92],
    [49, 64, 78, 87, 103, 121, 120, 101], [72, 92, 95, 98, 112, 100, 103, 99]], dtype=float)


def jpeg_qtable(quality: int) -> np.ndarray:
    q = max(1, min(100, quality))
    s = 5000 / q if q < 50 else 200 - 2 * q
    return np.clip(np.floor((JPEG_Q50 * s + 50) / 100), 1, 255)


def zigzag(n: int = 8) -> list[tuple[int, int]]:
    """JPEG zig-zag scan order of an n x n block as (row, column) pairs."""
    order = []
    for s in range(2 * n - 1):
        diag = [(r, s - r) for r in range(n) if 0 <= s - r < n]
        order += diag if s % 2 else diag[::-1]
    return order


ZIGZAG = zigzag()


def zonal_mask(keep: int) -> np.ndarray:
    """Keep the first ``keep`` coefficients in zig-zag order (compression 64:keep)."""
    m = np.zeros((8, 8), dtype=bool)
    for r, c in ZIGZAG[:keep]:
        m[r, c] = True
    return m


# ===================================================================== bounds
def corner_inputs(b_in: int) -> np.ndarray:
    lo, hi = -(1 << (b_in - 1)), (1 << (b_in - 1)) - 1
    return np.array(list(itertools.product((lo, hi), repeat=8)), dtype=np.int64)


def _nodes_batch(xs: np.ndarray, cfg: Config) -> dict:
    cols = [processor.align_input(xs[:, n], cfg) for n in range(8)]
    return flowgraph.evaluate_all(
        cols,
        bf=lambda p, q, st: (rno(p + q, cfg.scale(st)), rno(p - q, cfg.scale(st))),
        mr=lambda p, q, k: cordic2.mr_rotate(p, q, k, cfg.guard, cfg.mr_mode))


def node_bounds(cfg: Config, n_random: int = 4000, seed: int = 0,
                xs: np.ndarray | None = None) -> dict[str, tuple[int, int]]:
    """Worst-case (min, max) of every flow-graph node, without wrap-around.

    Every node is a linear function of the input up to rounding, so its extremes
    are attained at the 2^8 corners of the input hyper-cube; random inputs are
    added as a sanity check of the rounding slack.  ``xs`` replaces the default
    input set (corners + random) by an explicit ``(n, 8)`` array.
    """
    lo, hi = -(1 << (cfg.b_in - 1)), (1 << (cfg.b_in - 1)) - 1
    if xs is None:
        xs = np.vstack([corner_inputs(cfg.b_in),
                        np.random.default_rng(seed).integers(lo, hi + 1, (n_random, 8))])
    return {k: (int(np.min(v)), int(np.max(v))) for k, v in _nodes_batch(xs, cfg).items()}


def linear_gains() -> dict[str, np.ndarray]:
    """Exact linear map (real coefficients) from x to every node, exact rotations."""
    eye = np.eye(8)
    out = {}
    for n in range(8):
        val = flowgraph.evaluate_all(
            list(eye[n]), bf=lambda p, q, st: (p + q, p - q),
            mr=lambda p, q, k: (p * math.cos(k * math.pi / 16) - q * math.sin(k * math.pi / 16),
                                p * math.sin(k * math.pi / 16) + q * math.cos(k * math.pi / 16)))
        for name, v in val.items():
            out.setdefault(name, np.zeros(8))[n] = v
    return out


def headroom_table(b_in: int = 8) -> list[dict]:
    """Largest |node| / max|x| per flow-graph stage (exact rotations)."""
    rows = []
    for name, g in linear_gains().items():
        level = 0 if name.startswith("x") else next(op.level for op in flowgraph.OPS if name in op.outs)
        rows.append({"node": name, "level": level, "gain": float(np.sum(np.abs(g)))})
    return rows


def mr_register_peaks(cfg: Config, n_random: int = 4000, seed: int = 1,
                      xs: np.ndarray | None = None) -> dict[str, tuple[int, int]]:
    """Peak |value| of each internal word of the central CORDIC unit vs. its width.

    Returns ``{word: (peak, limit)}`` with ``limit = 2^(width-1)``; the RTL is
    free of overflow on the tested inputs when ``peak <= limit`` for every word
    (``-limit`` is a legal value).
    ``xs`` replaces the default input set (corners + random) by an explicit
    ``(n, 8)`` array.
    """
    lo, hi = -(1 << (cfg.b_in - 1)), (1 << (cfg.b_in - 1)) - 1
    if xs is None:
        xs = np.vstack([corner_inputs(cfg.b_in),
                        np.random.default_rng(seed).integers(lo, hi + 1, (n_random, 8))])
    nodes = _nodes_batch(xs, cfg)
    g, wm = cfg.guard, cfg.mr_width
    peaks: dict[str, int] = {}

    def upd(key, *arrs):
        peaks[key] = max(peaks.get(key, 0), *(int(np.max(np.abs(a))) for a in arrs))

    for op in flowgraph.OPS:
        if op.unit != "MR":
            continue
        u, v, k = nodes[op.ins[0]], nodes[op.ins[1]], op.param
        x0, y0 = u << g, v << g
        if cfg.mr_mode == "table1":
            a, b = cordic2.T1_P[k]
            xa, ya = a * x0 - b * y0, b * x0 + a * y0
            upd("stage A: rotation by P_k", xa, ya, 48 * x0, 48 * y0, 33 * x0, 33 * y0)
            upd("stage B: radius scale-down", cordic2._csd_int(xa, cordic2.T1_K[k]),
                cordic2._csd_int(ya, cordic2.T1_K[k]))
        else:
            f, s3, s5, n7, n9 = cordic2.CTRL[k]
            if f:
                px, py = 5 * (x0 - y0), 5 * (x0 + y0)
            else:
                px, py = 7 * x0 - y0, x0 + 7 * y0
            upd("friend-angle products", px, py)
            x1, y1 = rnd(px, 3), rnd(py, 3)
            x2, y2 = cordic2._usr_int(x1, y1, s3, 3)
            upd("stage A: FA + USR 2^-3", x1, y1, x2, y2)
            x3, y3 = cordic2._usr_int(x2, y2, s5, 5)
            x4 = x3 - n7 * rnd(y3, 7) - n9 * rnd(y3, 9)
            y4 = y3 + n7 * rnd(x3, 7) + n9 * rnd(x3, 9)
            upd("stage B: USR 2^-5 + nano", x3, y3, x4, y4)
            upd("stage B: radius scaling", cordic2._csd_int(x4, cordic2.RS_TERMS),
                cordic2._csd_int(y4, cordic2.RS_TERMS))
    widths = {"friend-angle products": wm + 3}
    return {key: (pk, 1 << (widths.get(key, wm) - 1)) for key, pk in peaks.items()}


# ================================================================ 1-D accuracy
def sqnr_db(ref, est) -> float:
    ref, est = np.asarray(ref, float), np.asarray(est, float)
    return 10 * math.log10(np.sum(ref ** 2) / max(np.sum((est - ref) ** 2), 1e-300))


def random_inputs(n: int = 20000, b_in: int = 8, seed: int = 2022) -> np.ndarray:
    lo, hi = -(1 << (b_in - 1)), (1 << (b_in - 1)) - 1
    return np.random.default_rng(seed).integers(lo, hi + 1, (n, 8))


def error_stats_1d(cfg: Config, x: np.ndarray) -> dict:
    est = processor.dct8_approx_batch(x, cfg)
    ref = reference.dct8(np.asarray(x, float))
    e = est - ref
    return {"rms": float(np.sqrt(np.mean(e ** 2))), "max": float(np.max(np.abs(e))),
            "bias": e.mean(axis=0), "std": e.std(axis=0), "sqnr": sqnr_db(ref, est), "err": e}


def ideal_rotation_dct(x: np.ndarray, cfg: Config) -> np.ndarray:
    """Same datapath and rounding points, exact rotations (isolates the CORDIC error)."""
    xs = np.asarray(x, dtype=np.int64)

    def mr(p, q, k):
        th = k * math.pi / 16
        u = np.rint(p * math.cos(th) - q * math.sin(th)).astype(np.int64)
        v = np.rint(p * math.sin(th) + q * math.cos(th)).astype(np.int64)
        return processor.wrap(u, cfg.w), processor.wrap(v, cfg.w)

    cols = [processor.align_input(xs[:, n], cfg) for n in range(8)]
    y = flowgraph.evaluate(cols, lambda p, q, st: processor.bf(p, q, cfg.scale(st), cfg.w), mr)
    return np.stack(y, axis=1) / (processor.SQRT8 * 2.0 ** cfg.e_out)


def matrix_dct(x: np.ndarray, coef_bits: int, out_frac: int) -> np.ndarray:
    """Baseline: direct matrix-vector product with ``coef_bits``-bit coefficients."""
    cq = np.round(reference.C8 * 2 ** (coef_bits - 1)) / 2 ** (coef_bits - 1)
    y = np.asarray(x, float) @ cq.T
    return np.round(y * 2 ** out_frac) / 2 ** out_frac


def valid_ss(b_in: int, w: int) -> list[tuple[int, int, int]]:
    out = []
    for ss in itertools.product((0, 1), repeat=3):
        if w - b_in - (3 - sum(ss)) >= 0:
            out.append(ss)
    return out


def best_config(w: int, mode: str, x: np.ndarray, b_in: int = 8, guard: int = 3) -> tuple[Config, float]:
    """Safe-scaling choice with the highest SQNR at word length ``w``."""
    ref = reference.dct8(np.asarray(x, float))
    best = None
    for ss in valid_ss(b_in, w):
        cfg = Config(b_in, w, guard, ss, mode)
        s = sqnr_db(ref, processor.dct8_approx_batch(x, cfg))
        if best is None or s > best[1]:
            best = (cfg, s)
    return best


def wl_sweep_1d(ws, x: np.ndarray, modes=cordic2.MODES, guard: int = 3) -> list[dict]:
    """SQNR versus WL; for each WL the best safe-scaling option, and exact rotations."""
    ref = reference.dct8(np.asarray(x, float))
    rows = []
    for mode in modes:
        for w in ws:
            cfg, s = best_config(w, mode, x, guard=guard)
            est = processor.dct8_approx_batch(x, cfg)
            rows.append({"w": w, "mode": mode, "ss": cfg.ss, "sqnr": s,
                         "sqnr_ideal_rot": sqnr_db(ref, ideal_rotation_dct(x, cfg)),
                         "rms": float(np.sqrt(np.mean((est - ref) ** 2)))})
    return rows


# ================================================================ 2-D / images
def test_images(names=("coffee", "chelsea", "rocket", "moon", "brick", "gravel", "coins",
                       "clock")) -> dict[str, np.ndarray]:
    """Grayscale 8-bit test images shipped with scikit-image, cropped to 8k x 8k."""
    from skimage import color, data
    out = {}
    for n in names:
        im = getattr(data, n)()
        if im.ndim == 3:
            im = np.round(color.rgb2gray(im) * 255)
        im = np.asarray(im, dtype=np.int64)
        h, w = (im.shape[0] // 8) * 8, (im.shape[1] // 8) * 8
        out[n] = im[:h, :w]
    return out


def psnr(a, b, peak: float = 255.0) -> float:
    mse = np.mean((np.asarray(a, float) - np.asarray(b, float)) ** 2)
    return float("inf") if mse == 0 else 10 * math.log10(peak ** 2 / mse)


def uniform_wl_2d(w: int, mode: str, x1d: np.ndarray | None = None, guard: int = 3):
    """Row and column processors that both use word length ``w`` (as the paper's WL).

    Row pass: input 8 bits, safe scaling chosen for the best SQNR.  Column pass:
    input = the w-bit row output, so SS = (1, 1, 1) (no headroom bit is left).
    Returns ``(row_cfg, col_cfg)``.
    """
    x1d = random_inputs(4000) if x1d is None else x1d
    row, _ = best_config(w, mode, x1d, guard=guard)
    col = Config(w, w, guard, (1, 1, 1), mode)
    return row, col


def dct2d_real(blocks, row: Config, col: Config) -> np.ndarray:
    """Real-valued 2-D DCT computed by the two fixed-point passes (no final rounding)."""
    b = np.asarray(blocks, dtype=np.int64)
    n = b.shape[0]
    yr = processor.dct8_fixed_batch(b.reshape(n * 8, 8), row).reshape(n, 8, 8)
    yc = processor.dct8_fixed_batch(yr.transpose(0, 2, 1).reshape(n * 8, 8), col)
    yc = yc.reshape(n, 8, 8).transpose(0, 2, 1)
    return yc / 2.0 ** (row.e_out + col.e_out + 3)


def float_dct2_blocks(blocks) -> np.ndarray:
    c = reference.C8
    return np.einsum("ij,njk,lk->nil", c, np.asarray(blocks, float), c)


def float_idct2_blocks(coefs) -> np.ndarray:
    c = reference.C8
    return np.einsum("ji,njk,kl->nil", c, np.asarray(coefs, float), c)


def psnr_vs_double(img, row: Config, col: Config) -> float:
    """PSNR (peak 255) of the processor's 2-D DCT against the IEEE-754 double DCT.

    The 2-D DCT is orthonormal, so this equals the PSNR of the un-rounded
    reconstruction against the original image.
    """
    blocks = dct2d.to_blocks(np.asarray(img, np.int64) - 128)
    return psnr(dct2d_real(blocks, row, col), float_dct2_blocks(blocks))


def wl_sweep_2d(ws, images: dict, modes=cordic2.MODES) -> list[dict]:
    rows = []
    x1d = random_inputs(4000)
    for mode in modes:
        for w in ws:
            row, col = uniform_wl_2d(w, mode, x1d)
            vals = {n: psnr_vs_double(im, row, col) for n, im in images.items()}
            rows.append({"w": w, "mode": mode, "row_ss": row.ss, "per_image": vals,
                         "mean": float(np.mean(list(vals.values())))})
    return rows


def reconstruct(img, row: Config | None = None, col: Config | None = None, keep: int | None = None,
                quality: int | None = None) -> np.ndarray:
    """2-D DCT (processor, or double precision if ``row`` is None) -> optional zonal
    mask (``keep`` coefficients, 64:keep) or JPEG quantisation -> double IDCT ->
    8-bit image."""
    x = np.asarray(img, np.int64)
    blocks = dct2d.to_blocks(x - 128)
    coef = float_dct2_blocks(blocks) if row is None else dct2d_real(blocks, row, col)
    if keep is not None:
        coef = coef * zonal_mask(keep)
    if quality is not None:
        q = jpeg_qtable(quality)
        coef = np.round(coef / q) * q
    rec = float_idct2_blocks(coef) + 128
    return np.clip(np.round(dct2d.from_blocks(rec, x.shape)), 0, 255).astype(np.int64)


def compression_table(images: dict, row: Config, col: Config, keeps=(10, 6, 3, 1)) -> list[dict]:
    rows = []
    for n, im in images.items():
        for k in keeps:
            hw = reconstruct(im, row, col, keep=k)
            fl = reconstruct(im, keep=k)
            rows.append({"image": n, "ratio": f"64:{k}", "psnr_hw": psnr(im, hw),
                         "psnr_float": psnr(im, fl)})
    return rows


def coef_error_2d(cfg2d: dct2d.Config2D, blocks) -> np.ndarray:
    """Error of the bit-exact 2-D output (with its final rounding) vs. the double DCT."""
    b = np.asarray(blocks, np.int64)
    return dct2d.dct2d_fixed_batch(b, cfg2d) / 2.0 ** cfg2d.out_frac - float_dct2_blocks(b)
