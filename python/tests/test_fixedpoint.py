"""Rounding primitives: exhaustive check against exact rational definitions."""
from fractions import Fraction

import numpy as np
import pytest

from dct8.fixedpoint import fits, from_hex, rnd, rne, rno, shift_round, to_hex, wrap

Z = range(-700, 700)


def _floor(q: Fraction) -> int:
    return q.numerator // q.denominator


@pytest.mark.parametrize("s", range(0, 7))
def test_rounding_definitions(s):
    for z in Z:
        q = Fraction(z, 2 ** s)
        f, r = _floor(q), q - _floor(q)
        half = Fraction(1, 2)
        assert rnd(z, s) == _floor(q + half)
        assert rne(z, s) == (f + 1 if r > half else f if r < half else f + (f & 1))
        assert rno(z, s) == (f + 1 if r > half else f if r < half else f | 1)


@pytest.mark.parametrize("s", range(0, 7))
def test_numpy_matches_scalar(s):
    z = np.arange(-700, 700, dtype=np.int64)
    for fn in (rnd, rne, rno):
        assert np.array_equal(fn(z, s), np.array([fn(int(v), s) for v in z]))
    assert np.array_equal(wrap(z * 37, 9), np.array([wrap(int(v) * 37, 9) for v in z]))


def test_von_neumann_is_jamming():
    for z in Z:
        assert rno(z, 1) == (z >> 1) | (z & 1)


def test_von_neumann_never_overflows():
    w = 8
    for a in range(-128, 128):
        for b in (-128, 127, 0, 1, -1):
            assert fits(rno(a + b, 1), w) and fits(rno(a - b, 1), w)
    # round half to even does overflow at the edge: (127 - (-128)) / 2 = 127.5 -> 128
    assert not fits(rne(127 + 128, 1), w)


def test_wrap_hex_and_shift_round():
    for z in Z:
        assert -(1 << 7) <= wrap(z, 8) < (1 << 7) and (wrap(z, 8) - z) % 256 == 0
        assert from_hex(to_hex(z, 11), 11) == wrap(z, 11)
        assert shift_round(z, -2) == 4 * z and shift_round(z, 0) == z
        assert shift_round(z, 3) == rne(z, 3)
    with pytest.raises(ValueError):
        rnd(5, -1)
