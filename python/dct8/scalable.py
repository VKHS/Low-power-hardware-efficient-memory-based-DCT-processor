"""Scalability: N-point radix-2 DCT, and the 16-point DCT built from two 8-point
processors and a CORDIC array (the paper's Table 5).

One radix-2 step (paper, Eqs. 4-13) turns an N-point DCT into two N/2-point DCTs
plus N/2 - 1 rotations.  With M = N/2,

    x_L[m] = x[2m] + x[2m+1],     x_H[m] = x[2m] - x[2m+1]          (m = 0 .. M-1)
    A = DCT_M(x_L),               B = DCT_M((-1)^m x_H)
    Z[0] = A[0],                  Z[M] = B[0]
    (Z[k], Z[N-k]) = Rot(-k pi / (2N)) (A[k], B[M-k])                 (k = 1 .. M-1)

If both halves carry the uniform scale sqrt(M) (``A = sqrt(M) X_M``) the result
carries sqrt(N): ``Z = sqrt(N) X_N`` -- for N = 8 that is the 2*sqrt(2) of the
8-point processor, for N = 16 a factor 4 (a pure shift).

16-point processor
------------------
stage 1 butterflies (x_L, x_H; the factor (-1)^m is free: operand order) ->
two 8-point processors (one for x_L, one for (-1)^m x_H) -> a CORDIC array of
seven micro-rotation units for k*pi/32, k = 1..7, each a Gaussian integer of the
paper's Table 5 with a radius scale-down K_k ~ 1/|P_k| (four signed powers of
two), exactly like the Table 1 mode of the 8-point central CORDIC unit (k = 2,
4, 6 are the Table 1 entries).
"""
from __future__ import annotations

import math

import numpy as np

from . import cordic2, processor
from .fixedpoint import rne, wrap
from .processor import Config

# Gaussian integers of the paper's Table 5: angle k*pi/32 ~ atan2(b, a)
TABLE5 = {1: (10, 1), 2: (10, 2), 3: (10, 3), 4: (50, 21), 5: (50, 27), 6: (50, 33), 7: (50, 41)}


def csd_terms(value: float, nterms: int = 4) -> tuple[tuple[int, int], ...]:
    """Greedy signed-power-of-two approximation: ``value ~ sum(sign * 2^-shift)``."""
    terms, r = [], value
    for _ in range(nterms):
        if r == 0:
            break
        e = round(math.log2(abs(r)))
        terms.append((-e, 1 if r > 0 else -1))
        r -= math.copysign(2.0 ** e, r)
    return tuple(terms)


TABLE5_K = {k: csd_terms(1.0 / math.hypot(a, b)) for k, (a, b) in TABLE5.items()}


def table5_report() -> list[dict]:
    rows = []
    for k, (a, b) in TABLE5.items():
        th = k * math.pi / 32
        kv = cordic2.k_value(TABLE5_K[k])
        rows.append({"k": k, "target_deg": math.degrees(th), "P": f"{a}+j{b}",
                     "realised_deg": math.degrees(math.atan2(b, a)),
                     "angle_err_rad": math.atan2(b, a) - th,
                     "gain": math.hypot(a, b) * kv, "K_terms": TABLE5_K[k]})
    return rows


# ------------------------------------------------------------------ floating point
def _rot(u, v, theta):
    c, s = math.cos(theta), math.sin(theta)
    return u * c - v * s, u * s + v * c


def dct_radix2(x, rot=None) -> np.ndarray:
    """N-point DCT by recursive radix-2 decomposition along the last axis.

    Returns ``sqrt(N) * X`` (X: orthonormal DCT-II).  ``rot(u, v, k, n)`` rotates
    counter-clockwise by ``k*pi/(2n)``; default: exact.
    """
    x = np.asarray(x, dtype=float)
    n = x.shape[-1]
    if n == 1:
        return x.copy()
    if n & (n - 1):
        raise ValueError("length must be a power of two")
    rot = rot or (lambda u, v, k, nn: _rot(u, v, k * math.pi / (2 * nn)))
    m = n // 2
    xl = x[..., 0::2] + x[..., 1::2]
    xh = (x[..., 0::2] - x[..., 1::2]) * np.where(np.arange(m) % 2, -1.0, 1.0)
    a, b = dct_radix2(xl, rot), dct_radix2(xh, rot)
    z = np.empty_like(x)
    z[..., 0], z[..., m] = a[..., 0], b[..., 0]
    for k in range(1, m):
        # Rot(-theta)(A[k], B[m-k]) = swap(Rot(+theta)(B[m-k], A[k]))
        hi, lo = rot(b[..., m - k], a[..., k], k, n)
        z[..., k], z[..., n - k] = lo, hi
    return z


def dct16_table5_float(x) -> np.ndarray:
    """16-point DCT (scale 4) with exact 8-point halves and Table-5 rotations in
    floating point (angle error of the Gaussian integers only, unit gain)."""
    def rot(u, v, k, nn):
        if nn == 16:
            a, b = TABLE5[k]
            r = math.hypot(a, b)
            return (a * u - b * v) / r, (b * u + a * v) / r
        return _rot(u, v, k * math.pi / (2 * nn))
    return dct_radix2(x, rot)


# --------------------------------------------------------------- bit-accurate model
def cordic_array_rotate(u, v, k: int, guard: int):
    """One unit of the CORDIC array: CCW rotation by ~k*pi/32 (Table 5)."""
    a, b = TABLE5[k]
    x0, y0 = u << guard, v << guard
    xa, ya = a * x0 - b * y0, b * x0 + a * y0
    return rne(cordic2._csd_int(xa, TABLE5_K[k]), guard), rne(cordic2._csd_int(ya, TABLE5_K[k]), guard)


def dct16_fixed(x, cfg8: Config = Config(b_in=9, w=15, guard=3), guard: int = 3) -> np.ndarray:
    """Bit-accurate 16-point DCT; ``x``: ``(n, 16)`` integers of ``cfg8.b_in - 1`` bits.

    Returns ``(n, 16)`` integers ``Z = 4 * X16 * 2^E`` (``E = cfg8.e_out``) on
    ``cfg8.w`` bits: every AC output of the 16-point DCT has a smaller L1 gain
    (at most 14.8 max|x|) than the two unrotated terms Z[0], Z[8] (16 max|x|), so the CORDIC array keeps
    the word length of the 8-point engines.
    """
    xs = np.atleast_2d(np.asarray(x, dtype=np.int64))
    if xs.shape[1] != 16:
        raise ValueError("expected 16 samples per vector")
    xl = xs[:, 0::2] + xs[:, 1::2]
    xh = (xs[:, 0::2] - xs[:, 1::2]) * np.where(np.arange(8) % 2, -1, 1)
    ya = processor.dct8_fixed_batch(xl, cfg8)
    yb = processor.dct8_fixed_batch(xh, cfg8)
    wz = cfg8.w
    z = np.empty((xs.shape[0], 16), dtype=np.int64)
    z[:, 0], z[:, 8] = ya[:, 0], yb[:, 0]
    for k in range(1, 8):
        hi, lo = cordic_array_rotate(yb[:, 8 - k], ya[:, k], k, guard)
        z[:, k], z[:, 16 - k] = wrap(lo, wz), wrap(hi, wz)
    return z


def dct16_approx(x, cfg8: Config = Config(b_in=9, w=15, guard=3), guard: int = 3) -> np.ndarray:
    return dct16_fixed(x, cfg8, guard) / (4.0 * 2.0 ** cfg8.e_out)


def dct16_matrix() -> np.ndarray:
    k = np.arange(16)[:, None]
    m = np.arange(16)[None, :]
    c = np.sqrt(2.0 / 16) * np.cos((2 * m + 1) * k * np.pi / 32)
    c[0, :] /= np.sqrt(2.0)
    return c


def dct16(x) -> np.ndarray:
    return np.asarray(x, float) @ dct16_matrix().T


def ops_count(n: int) -> dict:
    """Butterflies and rotations of the N-point radix-2 flow (N = 2^m)."""
    if n == 2:
        return {"butterflies": 1, "rotations": 0}
    h = ops_count(n // 2)
    return {"butterflies": n // 2 + 2 * h["butterflies"],
            "rotations": n // 2 - 1 + 2 * h["rotations"]}
