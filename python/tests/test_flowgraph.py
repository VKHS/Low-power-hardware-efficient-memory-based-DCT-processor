"""The radix-2 signal-flow graph computes 2*sqrt(2) * DCT-II exactly."""
import math

import numpy as np
import pytest

from dct8 import flowgraph as fg
from dct8 import reference, scalable


def _exact(x):
    return fg.evaluate(
        list(x), bf=lambda p, q, st: (p + q, p - q),
        mr=lambda p, q, k: (p * math.cos(k * math.pi / 16) - q * math.sin(k * math.pi / 16),
                            p * math.sin(k * math.pi / 16) + q * math.cos(k * math.pi / 16)))


def test_flow_graph_is_scaled_dct():
    rng = np.random.default_rng(0)
    for x in rng.normal(size=(200, 8)):
        assert np.allclose(_exact(x), 2 * math.sqrt(2) * reference.dct8(x), atol=1e-12)


def test_operation_counts_and_single_use():
    assert (fg.N_BF, fg.N_MR) == (12, 5)
    produced = [v for op in fg.OPS for v in op.outs]
    consumed = [v for op in fg.OPS for v in op.ins]
    assert len(produced) == len(set(produced))
    assert len(consumed) == len(set(consumed))                      # one reader per value
    assert set(consumed) | set(fg.OUTPUTS) == set(produced) | set(fg.INPUTS)
    assert sorted(op.param for op in fg.OPS if op.unit == "MR") == [1, 2, 2, 2, 3]


def test_topological_order():
    seen = set(fg.INPUTS)
    for op in fg.OPS:
        assert set(op.ins) <= seen
        seen |= set(op.outs)


@pytest.mark.parametrize("n", [2, 4, 8, 16, 32, 64])
def test_radix2_recursion(n):
    k, m = np.arange(n)[:, None], np.arange(n)[None, :]
    c = np.sqrt(2 / n) * np.cos((2 * m + 1) * k * np.pi / (2 * n))
    c[0] /= np.sqrt(2)
    x = np.random.default_rng(n).normal(size=(20, n))
    assert np.allclose(scalable.dct_radix2(x), math.sqrt(n) * x @ c.T, atol=1e-11)


def test_reference_is_orthonormal():
    assert np.allclose(reference.C8 @ reference.C8.T, np.eye(8))
    b = np.random.default_rng(1).normal(size=(8, 8))
    assert np.allclose(reference.idct2(reference.dct2(b)), b)
