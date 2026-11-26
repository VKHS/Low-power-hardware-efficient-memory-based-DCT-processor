"""Central CORDIC unit: both micro-rotation modes."""
import math

import numpy as np
import pytest

from dct8 import cordic2


def test_table1_coefficients_match_paper():
    assert cordic2.T1_P == {1: (10, 2), 2: (50, 21), 3: (50, 33)}
    for k, (a, b) in cordic2.T1_P.items():
        assert abs(a) + abs(b) < 2 ** cordic2.T1_GROWTH
        kv = cordic2.k_value(cordic2.T1_K[k])
        assert abs(kv * math.hypot(a, b) - 1) < 1e-3          # radius scale-down restores |P|


@pytest.mark.parametrize("mode,limit", [("table1", 6e-3), ("cordic2x", 4e-4)])
def test_angle_errors(mode, limit):
    for r in cordic2.analyze(mode):
        assert abs(r.angle_err_rad) < limit
        assert abs(r.gain - 1) < 1e-3


def test_cordic2x_is_more_accurate():
    e1 = max(abs(r.angle_err_rad) for r in cordic2.analyze("table1"))
    e2 = max(abs(r.angle_err_rad) for r in cordic2.analyze("cordic2x"))
    assert e2 < e1 / 10


@pytest.mark.parametrize("mode", cordic2.MODES)
def test_integer_rotation_tracks_ideal(mode):
    rng = np.random.default_rng(3)
    for k in cordic2.ANGLE_CODES:
        p = cordic2.coefficient(k, mode)
        for u, v in rng.integers(-2000, 2000, (300, 2)):
            ru, rv = cordic2.mr_rotate(int(u), int(v), k, 3, mode)
            ideal = complex(int(u), int(v)) * p
            assert abs(ru - ideal.real) <= 1.5 and abs(rv - ideal.imag) <= 1.5


@pytest.mark.parametrize("mode", cordic2.MODES)
def test_batch_rotation_matches_scalar(mode):
    rng = np.random.default_rng(4)
    u, v = rng.integers(-8192, 8192, (2, 500))
    for k in cordic2.ANGLE_CODES:
        bu, bv = cordic2.mr_rotate(u, v, k, 3, mode)
        su, sv = zip(*[cordic2.mr_rotate(int(a), int(b), k, 3, mode) for a, b in zip(u, v)])
        assert np.array_equal(bu, su) and np.array_equal(bv, sv)


def test_negative_rotation_by_swapping():
    for k in cordic2.ANGLE_CODES:
        th = k * math.pi / 16
        u, v = 0.3, -0.7
        hi, lo = (v * math.cos(th) - u * math.sin(th), v * math.sin(th) + u * math.cos(th))
        assert np.allclose((lo, hi), (u * math.cos(th) + v * math.sin(th),
                                      -u * math.sin(th) + v * math.cos(th)))


def test_design_space_contains_chosen_point():
    designs = cordic2.explore()
    chosen = [d for d in designs if d.chosen]
    assert len(chosen) == 1
    front = cordic2.pareto(designs)
    assert front and all(a.adders <= b.adders for a, b in zip(front, front[1:]))
