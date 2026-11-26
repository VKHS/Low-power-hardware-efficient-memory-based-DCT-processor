"""16-point extension, image experiments and helpers."""
import math

import numpy as np

from dct8 import analysis, cordic2, scalable
from dct8.processor import Config


def test_table5_contains_table1():
    for k in (1, 2, 3):
        assert scalable.TABLE5[2 * k] == cordic2.T1_P[k]
        assert scalable.TABLE5_K[2 * k] == cordic2.T1_K[k]
    for r in scalable.table5_report():
        assert abs(r["angle_err_rad"]) < 6e-3 and abs(r["gain"] - 1) < 2e-3


def test_dct16_fixed():
    x = np.random.default_rng(8).integers(-128, 128, (2000, 16))
    ref = scalable.dct16(x)
    est = scalable.dct16_approx(x, Config(9, 15, 3, (0, 0, 0), "cordic2x"))
    assert np.sqrt(np.mean((est - ref) ** 2)) < 0.3
    ext = np.array([[127 if (i >> (j % 8)) & 1 else -128 for j in range(16)] for i in range(256)])
    z = scalable.dct16_fixed(ext, Config(9, 15, 3, (0, 0, 0), "table1"))
    assert np.max(np.abs(z)) <= 2 ** 14


def test_ops_count():
    assert scalable.ops_count(8) == {"butterflies": 12, "rotations": 5}
    assert scalable.ops_count(16) == {"butterflies": 32, "rotations": 17}


def test_zigzag():
    z = analysis.ZIGZAG
    assert z[:6] == [(0, 0), (0, 1), (1, 0), (2, 0), (1, 1), (0, 2)]
    assert len(set(z)) == 64 and z[-1] == (7, 7)
    assert analysis.zonal_mask(10).sum() == 10


def test_image_round_trip_and_compression():
    img = analysis.test_images(("coffee",))["coffee"][:128, :128]
    row, col = analysis.uniform_wl_2d(14, "cordic2x")
    assert analysis.psnr_vs_double(img, row, col) > 55
    assert np.array_equal(analysis.reconstruct(img), img)            # double round trip is exact
    p = [analysis.psnr(img, analysis.reconstruct(img, row, col, keep=k)) for k in (1, 3, 6, 10)]
    assert p == sorted(p)
    assert math.isfinite(analysis.psnr(img, analysis.reconstruct(img, row, col, quality=50)))


def test_short_word_length_still_works():
    img = analysis.test_images(("coffee",))["coffee"][:128, :128]
    row, col = analysis.uniform_wl_2d(8, "table1")
    assert analysis.psnr_vs_double(img, row, col) > 25
