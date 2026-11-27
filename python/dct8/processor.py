"""Bit-accurate functional model of the memory-based radix-2 8-point DCT processor.

Fixed-point format
------------------
``B_IN``     input word length (signed integers x, e.g. level-shifted pixels)
``W``        internal word length (WL): memory bank, butterfly unit, CORDIC unit ports
``G``        guard bits of the central CORDIC unit ("radius scale-up")
``SS``       safe-scaling flags of the three butterfly stages (SS unit: x 1/2,
             von Neumann rounding), e.g. ``(0, 0, 0)`` or ``(1, 1, 1)``
``MR_MODE``  micro-rotations: ``"table1"`` (paper, Table 1) or ``"cordic2x"``

The input is aligned as ``x << F`` with ``F = W - B_IN - H`` fractional bits and
``H = 3 - sum(SS)`` headroom bits.  The flow graph's largest node is the DC sum
(8 max|x|), halved by each SS stage, so with H headroom bits it fills the W-bit range
exactly (-2^(W-1) for the input -128 on every sample).  No node leaves the range on
any of the 2^8 corner inputs, the 4^8 near-corner inputs or random inputs
(:func:`dct8.analysis.node_bounds`, ``dct8.evidence``).  Every output word is

    Y_k = 2*sqrt(2) * X_k * 2**E,   E = F - sum(SS),

i.e. the orthonormal DCT-II X_k carrying the paper's post-scaling factor
2*sqrt(2) and a power of two -- no other constant remains.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import cordic2, flowgraph
from .fixedpoint import fits, rno, wrap

SQRT8 = 2.0 * math.sqrt(2.0)


@dataclass(frozen=True)
class Config:
    b_in: int = 8
    w: int = 14
    guard: int = 3
    ss: tuple = (0, 0, 0)
    mr_mode: str = "table1"

    def __post_init__(self):
        if len(self.ss) != 3 or any(s not in (0, 1) for s in self.ss):
            raise ValueError("ss must be three 0/1 flags")
        if self.mr_mode not in cordic2.MODES:
            raise ValueError(f"mr_mode must be one of {cordic2.MODES}")
        if self.guard < 1:
            raise ValueError("guard must be >= 1")
        if self.mr_width <= (15 if self.mr_mode == "table1" else 11):
            raise ValueError("CORDIC word too short for its largest shift (use W + G >= 11)")
        if self.f_in < 0:
            raise ValueError(f"W={self.w} too short for B_IN={self.b_in} with H={self.headroom}")

    @property
    def headroom(self) -> int:
        return 3 - sum(self.ss)

    @property
    def f_in(self) -> int:
        return self.w - self.b_in - self.headroom

    @property
    def e_out(self) -> int:
        return self.f_in - sum(self.ss)

    @property
    def mr_width(self) -> int:
        return cordic2.internal_width(self.w, self.guard, self.mr_mode)

    @property
    def mode_bit(self) -> int:
        return cordic2.MODES.index(self.mr_mode)

    def scale(self, stage: int) -> int:
        return self.ss[stage - 1]

    def to_real(self, y) -> list[float]:
        """Processor output words -> orthonormal DCT-II coefficients."""
        return [v / (SQRT8 * 2.0 ** self.e_out) for v in y]

    def describe(self) -> str:
        return (f"B_IN={self.b_in} W={self.w} G={self.guard} SS={''.join(map(str, self.ss))} "
                f"{self.mr_mode} (H={self.headroom}, F={self.f_in}, E={self.e_out})")


def align_input(x: int, cfg: Config) -> int:
    if not fits(x, cfg.b_in):
        raise ValueError(f"input {x} does not fit in {cfg.b_in} bits")
    return x << cfg.f_in


def bf(p: int, q: int, shift: int, w: int) -> tuple[int, int]:
    """Butterfly datapath with its SS unit (x 1/2, von Neumann rounding)."""
    return wrap(rno(p + q, shift), w), wrap(rno(p - q, shift), w)


def mr(p: int, q: int, k: int, cfg: Config) -> tuple[int, int]:
    """Central CORDIC unit: counter-clockwise rotation by ~k*pi/16."""
    u, v = cordic2.mr_rotate(p, q, k, cfg.guard, cfg.mr_mode)
    return wrap(u, cfg.w), wrap(v, cfg.w)


def dct8_fixed(x, cfg: Config = Config()) -> list[int]:
    """Bit-accurate 8-point DCT: the eight W-bit output words Y_0..Y_7."""
    xi = [align_input(int(v), cfg) for v in x]
    return flowgraph.evaluate(
        xi,
        bf=lambda p, q, st: bf(p, q, cfg.scale(st), cfg.w),
        mr=lambda p, q, k: mr(p, q, k, cfg))


def dct8_fixed_nodes(x, cfg: Config = Config()) -> dict[str, int]:
    """All node values without wrap-around (the input of the overflow checks)."""
    xi = [align_input(int(v), cfg) for v in x]
    return flowgraph.evaluate_all(
        xi,
        bf=lambda p, q, st: (rno(p + q, cfg.scale(st)), rno(p - q, cfg.scale(st))),
        mr=lambda p, q, k: cordic2.mr_rotate(p, q, k, cfg.guard, cfg.mr_mode))


def dct8_approx(x, cfg: Config = Config()) -> list[float]:
    return cfg.to_real(dct8_fixed(x, cfg))


def dct8_fixed_batch(xs, cfg: Config = Config()) -> np.ndarray:
    """:func:`dct8_fixed` for many vectors at once: ``(n, 8)`` integers -> ``(n, 8)``."""
    xs = np.asarray(xs, dtype=np.int64)
    if xs.ndim != 2 or xs.shape[1] != 8:
        raise ValueError("expected an (n, 8) array")
    cols = [align_input(xs[:, n], cfg) for n in range(8)]
    y = flowgraph.evaluate(
        cols,
        bf=lambda p, q, st: bf(p, q, cfg.scale(st), cfg.w),
        mr=lambda p, q, k: mr(p, q, k, cfg))
    return np.stack(y, axis=1)


def dct8_approx_batch(xs, cfg: Config = Config()) -> np.ndarray:
    """Real-valued (orthonormal DCT-II) view of :func:`dct8_fixed_batch`."""
    return dct8_fixed_batch(xs, cfg) / (SQRT8 * 2.0 ** cfg.e_out)
