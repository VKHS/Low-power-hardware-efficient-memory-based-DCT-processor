"""Integer primitives that define the bit-accurate behaviour of the processor.

Every implementation in this repository (Python, MATLAB, Verilog RTL and the
Vitis-HLS C++ kernel) is written against exactly these primitives, which is
what makes the four of them bit-exact with each other.

* ``rnd(z, s)``  -- round-half-up arithmetic right shift, ``floor((z + 2^(s-1)) / 2^s)``.
  In hardware this is ``(z >>> s) + z[s-1]``: a plain shift whose discarded MSB is
  injected as a carry-in, so it costs no extra adder.
* ``rne(z, s)`` -- round-half-to-even (convergent) arithmetic right shift; used
  where rounding errors would otherwise accumulate into a bias (butterfly safe
  scaling, final rounding of the MR-PE).  In hardware:
  ``(z >>> s) + (z[s-1] & (z[s] | (z[s-2:0] != 0)))``.
* ``rno(z, s)`` -- round-half-to-odd arithmetic right shift.  For ``s = 1`` this is
  von Neumann rounding ("jamming"): ``(z >>> 1) | z[0]`` -- the discarded bit is
  OR-ed into the LSB, so it needs no adder.  It is unbiased like ``rne`` and can
  never round ``2^(W-1) - 1/2`` up to ``2^(W-1)``; used by the safe-scaling (SS)
  units of the butterflies, which therefore cannot overflow.
* ``wrap(z, w)`` -- two's-complement wrap-around to ``w`` bits (what a ``w``-bit
  register does).
* ``shift_round(z, s)`` -- ``rne(z, s)`` for ``s >= 1`` and an exact left shift by
  ``-s`` otherwise (final scaling stage of the 2-D processor).

All primitives accept Python integers or NumPy ``int64`` arrays (element-wise),
so the same model code runs on one vector or on a whole image at once.
"""
from __future__ import annotations

import numpy as np


def rnd(z, s: int):
    """Round-half-up arithmetic right shift by ``s`` bits (``s = 0`` returns ``z``)."""
    if s < 0:
        raise ValueError("shift must be non-negative")
    if s == 0:
        return z
    return (z + (1 << (s - 1))) >> s


def rne(z, s: int):
    """Round-half-to-even arithmetic right shift by ``s`` bits (``s = 0`` returns ``z``)."""
    if s < 0:
        raise ValueError("shift must be non-negative")
    if s == 0:
        return z
    q = z >> s
    r = z - (q << s)
    half = 1 << (s - 1)
    if isinstance(q, np.ndarray):
        return q + ((r > half) | ((r == half) & ((q & 1) == 1))).astype(q.dtype)
    if r > half or (r == half and (q & 1)):
        q += 1
    return q


def rno(z, s: int):
    """Round-half-to-odd arithmetic right shift by ``s`` bits (``s = 0`` returns ``z``)."""
    if s < 0:
        raise ValueError("shift must be non-negative")
    if s == 0:
        return z
    if s == 1:
        return (z >> 1) | (z & 1)
    q = z >> s
    r = z - (q << s)
    half = 1 << (s - 1)
    if isinstance(q, np.ndarray):
        return np.where(r > half, q + 1, np.where(r == half, q | 1, q))
    return q + 1 if r > half else (q | 1 if r == half else q)


def shift_round(z, s: int):
    """``rne(z, s)`` for ``s >= 1``; exact left shift by ``-s`` for ``s <= 0``."""
    return rne(z, s) if s >= 1 else z << (-s)


def wrap(z, w: int):
    """Two's-complement wrap-around of ``z`` to ``w`` bits."""
    m = 1 << w
    z = z & (m - 1)
    if isinstance(z, np.ndarray):
        return np.where(z >= (m >> 1), z - m, z)
    return z - m if z >= (m >> 1) else z


def fits(z, w: int) -> bool:
    """True if ``z`` (every element of ``z``) is a ``w``-bit two's-complement number."""
    ok = (-(1 << (w - 1)) <= z) & (z < (1 << (w - 1)))
    return bool(np.all(ok)) if isinstance(ok, np.ndarray) else bool(ok)


def sat(z: int, w: int) -> int:
    """Saturate ``z`` to the ``w``-bit two's-complement range."""
    lo, hi = -(1 << (w - 1)), (1 << (w - 1)) - 1
    return lo if z < lo else hi if z > hi else z


def to_hex(z: int, w: int) -> str:
    """Two's-complement hexadecimal string of ``z`` on ``w`` bits (for $readmemh)."""
    digits = (w + 3) // 4
    return format(z & ((1 << w) - 1), "0{}x".format(digits))


def from_hex(s: str, w: int) -> int:
    """Inverse of :func:`to_hex`."""
    return wrap(int(s, 16), w)


def range_of(w: int) -> tuple[int, int]:
    """Inclusive two's-complement range of a ``w``-bit word."""
    return -(1 << (w - 1)), (1 << (w - 1)) - 1
