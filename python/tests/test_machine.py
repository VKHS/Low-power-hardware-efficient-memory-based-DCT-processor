"""Cycle-accurate models equal the functional models (1-D and 2-D)."""
import numpy as np

from dct8 import dct2d, machine, processor, vectors
from dct8.processor import Config


def test_1d_stream_with_gaps():
    cfg = Config(8, 12, 2, (0, 1, 0), "cordic2x")
    blks = vectors.blocks_1d(8)[:60]
    outs = machine.run_stream(blks, cfg, gap_blocks=(3, 4, 20))
    exp = np.array([processor.dct8_fixed(b, cfg) for b in blks]).reshape(-1)
    assert [o.data for o in outs] == list(exp)
    assert [o.index for o in outs] == [i % 8 for i in range(len(exp))]
    assert outs[0].cycle == 16
    assert all(o.last == (o.index == 7) for o in outs)


def test_2d_stream():
    cfg = vectors.CONFIGS_2D["t1_w10"]
    blks = vectors.blocks_2d()[:6]
    outs, first = dct2d.run_stream_2d(blks, cfg)
    exp = np.concatenate([dct2d.dct2d_fixed(b, cfg).T.reshape(-1) for b in blks])
    assert first == 97 and np.array_equal(outs, exp)


def test_2d_batch_matches_scalar():
    rng = np.random.default_rng(5)
    for cfg in vectors.CONFIGS_2D.values():
        b = rng.integers(-128, 128, (20, 8, 8))
        assert np.array_equal(dct2d.dct2d_fixed_batch(b, cfg),
                              np.array([dct2d.dct2d_fixed(x, cfg) for x in b]))


def test_2d_accuracy():
    blocks = np.random.default_rng(6).integers(-128, 128, (200, 8, 8))
    from dct8 import analysis
    e = analysis.coef_error_2d(vectors.CONFIGS_2D["c2_f2"], blocks)
    assert np.sqrt(np.mean(e ** 2)) < 0.12
