"""Generated files in the repository are up to date with the Python sources."""
import json
from pathlib import Path

import numpy as np
import pytest

from dct8 import dct2d, emit, processor, schedule, vectors
from dct8.fixedpoint import from_hex

ROOT = Path(__file__).resolve().parents[2]
MAN = json.loads((ROOT / "vectors" / "manifest.json").read_text())


def test_generated_controller_is_current():
    sch = schedule.build()
    assert (ROOT / "rtl" / "dct8_ctrl.v").read_text() == emit.ctrl_verilog(sch)
    assert (ROOT / "rtl" / "dct8_sched_params.vh").read_text() == emit.params_vh(sch)
    assert (ROOT / "hls" / "src" / "dct8_sched.h").read_text() == emit.hls_header(sch)


@pytest.mark.parametrize("name", sorted(vectors.CONFIGS_1D))
def test_1d_vectors(name):
    cfg = vectors.CONFIGS_1D[name]
    m = MAN[f"dct8_{name}"]
    assert m["params"] == vectors._params_1d(cfg)
    ins = np.loadtxt(ROOT / "vectors" / f"dct8_{name}_in.txt", dtype=np.int64, ndmin=2)
    outs = np.loadtxt(ROOT / "vectors" / f"dct8_{name}_out.txt", dtype=np.int64, ndmin=2)
    assert np.array_equal(processor.dct8_fixed_batch(ins, cfg), outs)
    hexes = (ROOT / "vectors" / f"dct8_{name}_expect.hex").read_text().split()
    assert [from_hex(h, cfg.w) for h in hexes] == list(outs.reshape(-1))
    assert len((ROOT / "vectors" / f"dct8_{name}_stim.hex").read_text().split()) == m["n_stim"]


@pytest.mark.parametrize("name", sorted(vectors.CONFIGS_2D))
def test_2d_vectors(name):
    cfg = vectors.CONFIGS_2D[name]
    ins = np.loadtxt(ROOT / "vectors" / f"dct2d_{name}_in.txt", dtype=np.int64, ndmin=2)
    outs = np.loadtxt(ROOT / "vectors" / f"dct2d_{name}_out.txt", dtype=np.int64, ndmin=2)
    got = dct2d.dct2d_fixed_batch(ins.reshape(-1, 8, 8), cfg).reshape(-1, 64)
    assert np.array_equal(got, outs)
    hexes = (ROOT / "vectors" / f"dct2d_{name}_expect.hex").read_text().split()
    col_major = outs.reshape(-1, 8, 8).transpose(0, 2, 1).reshape(-1)
    assert [from_hex(h, cfg.out_w) for h in hexes] == list(col_major)
    assert MAN[f"dct2d_{name}"]["derived"]["OUT_SHIFT"] == cfg.out_shift
