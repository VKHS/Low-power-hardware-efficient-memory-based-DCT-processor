"""Bit-accurate 1-D model: accuracy, scaling and the overflow checks of every configuration."""
import numpy as np
import pytest

from dct8 import analysis, cordic2, processor, reference
from dct8.processor import Config

X = analysis.random_inputs(4000)


@pytest.mark.parametrize("cfg,rms_max", [
    (Config(8, 14, 3, (0, 0, 0), "table1"), 0.40),
    (Config(8, 14, 3, (0, 0, 0), "cordic2x"), 0.03),
    (Config(8, 16, 4, (0, 0, 0), "cordic2x"), 0.02),
    (Config(8, 10, 3, (1, 1, 1), "table1"), 0.60),
    (Config(8, 8, 3, (1, 1, 1), "table1"), 2.0),
])
def test_accuracy(cfg, rms_max):
    st = analysis.error_stats_1d(cfg, X)
    assert st["rms"] < rms_max
    assert np.all(np.abs(st["bias"]) < 0.25 * max(1.0, rms_max))      # unbiased rounding


def test_scaling_is_2sqrt2_times_power_of_two():
    cfg = Config(8, 14, 3, (0, 0, 0), "cordic2x")
    x = np.array([[100, -3, 27, 64, -128, 127, 5, -50]])
    y = processor.dct8_fixed_batch(x, cfg)[0]
    assert np.allclose(y / (2 * np.sqrt(2) * 2 ** cfg.e_out), reference.dct8(x[0]), atol=0.15)


def test_dc_of_full_scale_input_is_exact():
    for cfg in (Config(8, 14), Config(8, 10, 3, (1, 1, 1)), Config(8, 8, 3, (1, 1, 1))):
        y = processor.dct8_fixed([-128] * 8, cfg)
        assert y[0] == -(1 << (cfg.w - 1)) and all(v == 0 for v in y[1:])


@pytest.mark.parametrize("mode", cordic2.MODES)
@pytest.mark.parametrize("w", range(8, 17))
def test_no_overflow_anywhere(mode, w):
    """No node and no CORDIC register leaves its range on corner and random inputs."""
    for ss in analysis.valid_ss(8, w):
        cfg = Config(8, w, 3, ss, mode)
        lo, hi = -(1 << (w - 1)), (1 << (w - 1)) - 1
        for name, (a, b) in analysis.node_bounds(cfg, n_random=500).items():
            assert lo <= a and b <= hi, (cfg.describe(), name, a, b)
        for name, (peak, limit) in analysis.mr_register_peaks(cfg, n_random=500).items():
            assert peak <= limit, (cfg.describe(), name)


def test_invalid_configs_rejected():
    with pytest.raises(ValueError):
        Config(8, 10, 3, (0, 0, 0))          # needs one SS stage
    with pytest.raises(ValueError):
        Config(8, 14, 3, (0, 2, 0))
    with pytest.raises(ValueError):
        Config(mr_mode="exact")


def test_batch_matches_scalar():
    for cfg in (Config(8, 14), Config(8, 9, 2, (0, 1, 1), "cordic2x")):
        b = processor.dct8_fixed_batch(X[:300], cfg)
        s = np.array([processor.dct8_fixed(x, cfg) for x in X[:300]])
        assert np.array_equal(b, s)


def test_rotation_error_dominates_table1():
    """With exact rotations the W=14 datapath is ~10x more accurate than Table 1."""
    cfg = Config(8, 14, 3, (0, 0, 0), "table1")
    ref = reference.dct8(X)
    assert analysis.sqnr_db(ref, analysis.ideal_rotation_dct(X, cfg)) > \
        analysis.sqnr_db(ref, processor.dct8_approx_batch(X, cfg)) + 20
