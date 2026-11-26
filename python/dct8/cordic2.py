"""Shared-resource central CORDIC unit (MR-PE) -- two micro-rotation configurations.

The radix-2 flow graph needs counter-clockwise rotations by exactly three angles,
``theta_k = k*pi/16`` for ``k = 1, 2, 3`` (pi/16, pi/8, 3pi/16).  One pipelined unit
executes all five rotations of a block; its stages are shared ("overlapped") by
the three angles and only the option of each stage is selected per operation.

Mode ``"table1"`` -- the micro-rotations of the paper (Table 1)
    Each angle is a Gaussian integer P_k = a_k + j b_k:
        pi/16  ~ 10 + j2   (11.310 deg)      pi/8 ~ 50 + j21  (22.782 deg)
        3pi/16 ~ 50 + j33  (33.425 deg)
    radius scale-up (guard bits, x 2^G) -> exact shift-add rotation by P_k ->
    radius scale-down by K_k ~ 1/|P_k| (four signed powers of two) -> rounding.
    The unit gain is restored per angle; the angle error is that of P_k.

Mode ``"cordic2x"`` -- extended CORDIC-II configuration (this repository)
    friend angles (7+j)/8 | (5+5j)/8  ->  uniformly-scaled redundant (USR)
    stages 2^-3 and 2^-5  ->  nano-rotation n7 2^-7 + n9 2^-9  ->  ONE radius
    scaling K = 1 + 2^-3 - 2^-6 + 2^-8 - 2^-11 for all angles (uniform gain).
    Worst angle error 3.5e-4 rad (16x smaller than Table 1).

Both modes: two pipeline stages (A = scale-up + coarse rotation, B = fine
rotation + scale-down + rounding), bit-exact with rtl/cordic2_mr.v, the HLS
kernel and the MATLAB model.  ``rnd`` = round half up, ``rne`` = half to even.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .fixedpoint import rnd, rne

ANGLE_CODES = (1, 2, 3)
MODES = ("table1", "cordic2x")

# ----------------------------------------------------------------- Table 1 mode
T1_P = {1: (10, 2), 2: (50, 21), 3: (50, 33)}                 # (a, b): a + j b
# radius scale-down K_k ~ 1/|P_k| as signed powers of two: [(shift, sign), ...]
T1_K = {1: ((3, +1), (5, -1), (8, +1), (11, +1)),              # 0.0981445 vs 0.0980581
        2: ((6, +1), (8, +1), (10, -1), (13, -1)),             # 0.0184326 vs 0.0184396
        3: ((6, +1), (10, +1), (13, +1), (15, -1))}            # 0.0166931 vs 0.0166922
T1_GROWTH = 7          # |a| + |b| < 2^7: extra integer bits after the exact rotation

# --------------------------------------------------------------- CORDIC-II mode
CTRL = {                 # k -> (f, s3, s5, n7, n9)
    1: (0, 0, +1, -1, 0),     # pi/16  :  8.130 + 3.580 - 0.448          = 11.262 deg
    2: (0, +1, 0, 0, +1),     # pi/8   :  8.130 + 14.250 + 0.112         = 22.492 deg
    3: (1, -1, +1, -1, -1),   # 3pi/16 : 45 - 14.250 + 3.580 - 0.560     = 33.770 deg
}
FA_COEF = {0: complex(7, 1), 1: complex(5, 5)}          # friend angles, |P|^2 = 50
FA_SHIFT = 3
RS_TERMS = ((0, +1), (3, +1), (6, -1), (8, +1), (11, -1))
RS_K = sum(sg * 2.0 ** -sh for sh, sg in RS_TERMS)


def k_value(terms) -> float:
    return sum(sg * 2.0 ** -sh for sh, sg in terms)


def usr_coef(k: int, s: int) -> complex:
    if s == 0:
        return complex(1 + 2.0 ** (-2 * k), 0.0)
    return complex(1 - 2.0 ** (-2 * k), s * 2.0 ** (1 - k))


def nano_coef(n7: int, n9: int) -> complex:
    return complex(1.0, n7 * 2.0 ** -7 + n9 * 2.0 ** -9)


def stage_coefs(k: int, mode: str = "table1") -> list[complex]:
    """Normalised stage coefficients for angle code k (for analysis and figures)."""
    if mode == "table1":
        a, b = T1_P[k]
        return [complex(a, b), complex(k_value(T1_K[k]), 0.0)]
    f, s3, s5, n7, n9 = CTRL[k]
    return [FA_COEF[f] / 2 ** FA_SHIFT, usr_coef(3, s3), usr_coef(5, s5),
            nano_coef(n7, n9), complex(RS_K, 0.0)]


STAGE_NAMES = {"table1": ("rotation by P_k", "radius scale-down K_k"),
               "cordic2x": ("friend angle", "USR 2^-3", "USR 2^-5", "nano", "radius scaling")}


def coefficient(k: int, mode: str = "table1") -> complex:
    p = complex(1.0, 0.0)
    for c in stage_coefs(k, mode):
        p *= c
    return p


def trajectory(k: int, mode: str = "cordic2x") -> list[complex]:
    pts = [complex(1.0, 0.0)]
    for c in stage_coefs(k, mode):
        pts.append(pts[-1] * c)
    return pts


@dataclass
class AngleReport:
    k: int
    mode: str
    target_deg: float
    realised_deg: float
    angle_err_rad: float
    gain: float
    complex_err: float


def analyze(mode: str = "table1") -> list[AngleReport]:
    out = []
    for k in ANGLE_CODES:
        p = coefficient(k, mode)
        th = k * math.pi / 16
        ang = math.atan2(p.imag, p.real)
        out.append(AngleReport(k, mode, math.degrees(th), math.degrees(ang), ang - th, abs(p),
                               abs(p - complex(math.cos(th), math.sin(th)))))
    return out


# --------------------------------------------------------------- integer datapath
def _usr_int(x: int, y: int, s: int, k: int) -> tuple[int, int]:
    if s:
        return (x - rnd(x, 2 * k) - s * rnd(y, k - 1),
                y - rnd(y, 2 * k) + s * rnd(x, k - 1))
    return x + rnd(x, 2 * k), y + rnd(y, 2 * k)


def _csd_int(x: int, terms) -> int:
    acc = 0
    for sh, sg in terms:
        acc += sg * (x if sh == 0 else rnd(x, sh))
    return acc


def mr_stage_a(u: int, v: int, k: int, guard: int, mode: str = "table1") -> tuple[int, int]:
    """Stage A: radius scale-up (guard bits) and the coarse rotation."""
    x0, y0 = u << guard, v << guard
    if mode == "table1":
        a, b = T1_P[k]
        return a * x0 - b * y0, b * x0 + a * y0
    f, s3, _, _, _ = CTRL[k]
    if f:
        x1, y1 = rnd(5 * (x0 - y0), FA_SHIFT), rnd(5 * (x0 + y0), FA_SHIFT)
    else:
        x1, y1 = rnd(7 * x0 - y0, FA_SHIFT), rnd(x0 + 7 * y0, FA_SHIFT)
    return _usr_int(x1, y1, s3, 3)


def mr_stage_b(x: int, y: int, k: int, guard: int, mode: str = "table1") -> tuple[int, int]:
    """Stage B: fine rotation, radius scale-down and removal of the guard bits."""
    if mode == "table1":
        return rne(_csd_int(x, T1_K[k]), guard), rne(_csd_int(y, T1_K[k]), guard)
    _, _, s5, n7, n9 = CTRL[k]
    x3, y3 = _usr_int(x, y, s5, 5)
    x4 = x3 - n7 * rnd(y3, 7) - n9 * rnd(y3, 9)
    y4 = y3 + n7 * rnd(x3, 7) + n9 * rnd(x3, 9)
    return rne(_csd_int(x4, RS_TERMS), guard), rne(_csd_int(y4, RS_TERMS), guard)


def mr_rotate(u: int, v: int, k: int, guard: int, mode: str = "table1") -> tuple[int, int]:
    """Rotate (u, v) counter-clockwise by ~k*pi/16 with the bit-accurate MR-PE."""
    xa, ya = mr_stage_a(u, v, k, guard, mode)
    return mr_stage_b(xa, ya, k, guard, mode)


def internal_width(w: int, guard: int, mode: str) -> int:
    """Word length of the MR-PE pipeline register (hardware)."""
    return w + guard + (T1_GROWTH + 1 if mode == "table1" else 1)


def mr_internal_peak(u: int, v: int, k: int, guard: int, mode: str) -> int:
    xa, ya = mr_stage_a(u, v, k, guard, mode)
    peak = max(abs(xa), abs(ya))
    if mode == "cordic2x":
        _, _, s5, n7, n9 = CTRL[k]
        x3, y3 = _usr_int(xa, ya, s5, 5)
        x4 = x3 - n7 * rnd(y3, 7) - n9 * rnd(y3, 9)
        y4 = y3 + n7 * rnd(x3, 7) + n9 * rnd(x3, 9)
        peak = max(peak, abs(x3), abs(y3), abs(x4), abs(y4),
                   abs(_csd_int(x4, RS_TERMS)), abs(_csd_int(y4, RS_TERMS)))
    else:
        peak = max(peak, abs(_csd_int(xa, T1_K[k])), abs(_csd_int(ya, T1_K[k])))
    return peak


# --------------------------------------------------------------- hardware cost
def adder_count(mode: str = "table1") -> dict[str, int]:
    """Carry-propagate adders of rtl/cordic2_mr.v, both output components.

    A multi-operand sum of n terms counts as n - 1 two-input adders.  The +1 of
    every rounding shift (:func:`rounding_count`) is listed separately: it is a
    carry-in that an adder tree can absorb.
    """
    if mode == "table1":
        return {"partial products 48x, 21x, 33x": 8, "rotation by P_k (2 x 3-operand)": 4,
                "radius scale-down K_k (2 x 4-term)": 6}
    return {"friend angle (s, d, two add/sub)": 4, "USR 2^-3 (2 x 3-operand)": 4,
            "USR 2^-5 (2 x 3-operand)": 4, "nano-rotation (2 x 3-operand)": 4,
            "radius scaling K (2 x 5-term)": 2 * (len(RS_TERMS) - 1)}


def rounding_count(mode: str = "table1") -> int:
    """Rounding increments (shift + carry-in) of rtl/cordic2_mr.v."""
    if mode == "table1":
        return 2 * 4 + 2                    # four scale-down terms per component + final rne
    return 2 + 4 + 4 + 4 + 2 * (len(RS_TERMS) - 1) + 2


# --------------------------------------------------------------- design space
THETAS = [k * math.pi / 16 for k in ANGLE_CODES]


def _atan2(k: int) -> float:
    return math.atan(2.0 ** -k)


@dataclass
class Design:
    name: str
    family: str
    adders: int
    max_err: float
    detail: str = ""
    chosen: bool = False
    per_angle: list = field(default_factory=list)


def _csd_terms_for(value: float, tol: float, max_terms: int = 8) -> tuple[int, float]:
    best = None
    for nterms in range(1, max_terms + 1):
        r, approx = value, 0.0
        for _ in range(nterms):
            if r == 0:
                break
            e = round(math.log2(abs(r)))
            approx += math.copysign(2.0 ** e, r)
            r = value - approx
        err = abs(approx - value) / value
        if best is None or err < best[1]:
            best = (nterms, err)
        if err <= tol:
            return nterms, err
    return best


def _evaluate(stage_opts, base_cost, name, family, detail) -> Design:
    per = []
    for th in THETAS:
        best = None
        for combo in itertools.product(*stage_opts):
            ang = sum(a for a, _ in combo)
            g = math.prod(gg for _, gg in combo)
            if best is None or abs(ang - th) < best[0]:
                best = (abs(ang - th), ang, g)
        per.append(best)
    gains = [p[2] for p in per]
    gm = math.exp(sum(math.log(g) for g in gains) / len(gains))
    ang_err = max(p[0] for p in per)
    spread = max(abs(g / gm - 1) for g in gains)
    nterms, rs_err = _csd_terms_for(1.0 / gm, max(ang_err / 4, 2.0 ** -16))
    return Design(name, family, base_cost + 2 * (nterms - 1), ang_err + spread + rs_err, detail,
                  per_angle=[(math.degrees(p[1]), p[0]) for p in per])


def explore() -> list[Design]:
    """Conventional CORDIC, USR CORDIC and CORDIC-II variants for {pi/16, pi/8, 3pi/16}."""
    designs: list[Design] = []
    for n in range(4, 13):
        opts = [[(+_atan2(k), math.sqrt(1 + 4.0 ** -k)), (-_atan2(k), math.sqrt(1 + 4.0 ** -k))]
                for k in range(n)]
        designs.append(_evaluate(opts, 2 * n, f"CORDIC n={n}", "conventional CORDIC",
                                 f"stages 0..{n - 1}"))
    nano_sets = [(), (7,), (8,), (9,), (7, 9), (8, 10), (7, 10)]
    for usr in [(2, 3), (2, 4), (3, 5), (2, 4, 6), (3, 4, 5), (2, 3, 5), (3, 5, 7)]:
        for nano in nano_sets:
            opts = [[(2 * _atan2(k), 1 + 4.0 ** -k), (0.0, 1 + 4.0 ** -k),
                     (-2 * _atan2(k), 1 + 4.0 ** -k)] for k in usr]
            opts += [[(s * 2.0 ** -m, math.sqrt(1 + 4.0 ** -m) if s else 1.0) for s in (-1, 0, 1)]
                     for m in nano]
            designs.append(_evaluate(opts, 4 * len(usr) + 2 * len(nano),
                                     f"USR{list(usr)} nano{list(nano)}", "USR CORDIC", "USR + nano"))
    fa = [(math.atan2(1, 7), math.sqrt(50) / 8), (math.pi / 4, math.sqrt(50) / 8)]
    for usr in [(3,), (3, 5), (2, 4), (3, 4), (3, 6), (3, 5, 7)]:
        for nano in nano_sets:
            opts = [fa]
            opts += [[(2 * _atan2(k), 1 + 4.0 ** -k), (0.0, 1 + 4.0 ** -k),
                      (-2 * _atan2(k), 1 + 4.0 ** -k)] for k in usr]
            opts += [[(s * 2.0 ** -m, math.sqrt(1 + 4.0 ** -m) if s else 1.0) for s in (-1, 0, 1)]
                     for m in nano]
            d = _evaluate(opts, 4 + 4 * len(usr) + 2 * len(nano),
                          f"FA USR{list(usr)} nano{list(nano)}", "CORDIC-II (friend angles)",
                          "friend angles + USR + nano")
            d.chosen = (usr == (3, 5) and nano == (7, 9))
            designs.append(d)
    # the paper's Table 1 Gaussian-integer micro-rotations (per-angle radius scaling)
    errs = []
    for k in ANGLE_CODES:
        p = coefficient(k, "table1")
        errs.append(abs(p - complex(math.cos(THETAS[k - 1]), math.sin(THETAS[k - 1]))))
    designs.append(Design("Table 1 (10+j2, 50+j21, 50+j33)", "paper Table 1",
                          sum(adder_count("table1").values()), max(errs), "Gaussian integers"))
    return designs


def pareto(designs: list[Design]) -> list[Design]:
    pts = sorted(designs, key=lambda d: (d.adders, d.max_err))
    front, best = [], float("inf")
    for d in pts:
        if d.max_err < best - 1e-15:
            front.append(d)
            best = d.max_err
    return front
