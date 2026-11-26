"""8x8 2-D DCT built from two memory-based 1-D processors and one transpose buffer.

Row processor  ->  64-word transpose buffer  ->  column processor  ->  rounding

The transpose buffer is a *single* 64-word memory: every location is read
(previous block, transposed order) and re-written (current block) in the same
cycle.  The address order alternates between row-major and column-major from
one block to the next, so no ping-pong buffer is needed.

Output order: the column processor emits the coefficients column by column,
``X[0][v], X[1][v], ..., X[7][v]`` for ``v = 0..7`` (v = horizontal frequency).

Scaling: the row processor returns ``Y_r = 2 sqrt(2) X_row 2**E_r`` (W_r-bit
integers), which the column processor takes as its integer input
(``B_IN_col = W_r``).  The two post-scaling factors combine to (2 sqrt 2)^2 = 8,
so the column output is ``Y_c = 2**(E_r + E_c + 3) X2D`` -- a pure power of two --
and the final stage rounds it (half to even) to ``OUT_FRAC`` fractional bits.
When ``E_r + E_c + 3 < OUT_FRAC`` (very short word lengths) the final stage is an
exact left shift instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import machine as mach
from .fixedpoint import shift_round, wrap
from .processor import Config, dct8_fixed, dct8_fixed_batch


@dataclass(frozen=True)
class Config2D:
    row: Config = field(default_factory=lambda: Config(b_in=8, w=14, guard=3))
    col: Config = field(default_factory=lambda: Config(b_in=14, w=16, guard=3, ss=(1, 1, 1)))
    out_w: int = 12
    out_frac: int = 0

    def __post_init__(self):
        if self.col.b_in != self.row.w:
            raise ValueError("column processor input width must equal row word length")
        if self.row.mr_mode != self.col.mr_mode:
            raise ValueError("both passes use the same micro-rotation mode")

    @property
    def out_shift(self) -> int:
        return self.row.e_out + self.col.e_out + 3 - self.out_frac

    def to_real(self, out) -> np.ndarray:
        return np.asarray(out, dtype=float) / 2.0 ** self.out_frac

    def describe(self) -> str:
        return (f"row[{self.row.describe()}]  col[{self.col.describe()}]  "
                f"out {self.out_w} bits, {self.out_frac} fractional")


def dct2d_fixed(block, cfg: Config2D = Config2D()) -> np.ndarray:
    """Bit-accurate 2-D DCT of one 8x8 block; returns X[u][v] as integers."""
    b = np.asarray(block, dtype=np.int64)
    yr = np.array([dct8_fixed(b[r], cfg.row) for r in range(8)], dtype=np.int64)   # [r][v]
    yc = np.array([dct8_fixed(yr[:, v], cfg.col) for v in range(8)], dtype=np.int64)  # [v][u]
    out = [[wrap(shift_round(int(z), cfg.out_shift), cfg.out_w) for z in row] for row in yc.T]
    return np.array(out, dtype=np.int64)


def dct2d_fixed_batch(blocks, cfg: Config2D = Config2D()) -> np.ndarray:
    """:func:`dct2d_fixed` for an ``(n, 8, 8)`` stack of blocks (vectorised)."""
    b = np.asarray(blocks, dtype=np.int64)
    n = b.shape[0]
    yr = dct8_fixed_batch(b.reshape(n * 8, 8), cfg.row).reshape(n, 8, 8)          # [n][r][v]
    yc = dct8_fixed_batch(yr.transpose(0, 2, 1).reshape(n * 8, 8), cfg.col)        # [n*v][u]
    yc = yc.reshape(n, 8, 8).transpose(0, 2, 1)                                    # [n][u][v]
    return wrap(shift_round(yc, cfg.out_shift), cfg.out_w)


def to_blocks(img) -> np.ndarray:
    """``(H, W)`` image -> ``(H/8 * W/8, 8, 8)`` blocks in raster order."""
    x = np.asarray(img)
    h, w = x.shape
    if h % 8 or w % 8:
        raise ValueError("image dimensions must be multiples of 8")
    return x.reshape(h // 8, 8, w // 8, 8).transpose(0, 2, 1, 3).reshape(-1, 8, 8)


def from_blocks(blocks, shape) -> np.ndarray:
    h, w = shape
    return np.asarray(blocks).reshape(h // 8, w // 8, 8, 8).transpose(0, 2, 1, 3).reshape(h, w)


def dct2d_image(img, cfg: Config2D = Config2D(), level_shift: int = 128) -> np.ndarray:
    """Blockwise bit-accurate 2-D DCT of an image (dimensions multiple of 8)."""
    x = np.asarray(img, dtype=np.int64) - level_shift
    return from_blocks(dct2d_fixed_batch(to_blocks(x), cfg), x.shape)


class TransposeBuffer:
    """Single 64-word buffer with alternating row/column-major addressing."""

    def __init__(self):
        self.mem = [0] * 64
        self.tau = 0
        self.frame = 0
        self.started = False

    @staticmethod
    def addr(tau: int, mode: int) -> int:
        return tau if mode == 0 else 8 * (tau % 8) + tau // 8


class DCT2DMachine:
    """Cycle-accurate model of ``rtl/dct2d_8x8.v``."""

    def __init__(self, cfg: Config2D = Config2D()):
        self.cfg = cfg
        self.row = mach.DCT8Machine(cfg.row)
        self.col = mach.DCT8Machine(cfg.col)
        self.tb = TransposeBuffer()
        self.frame_tag = 0          # valid tag of the frame being written
        self.read_tag = 0           # valid tag of the frame being read
        self.dout = 0
        self.dout_valid = 0
        self.cycle = 0

    def step(self, in_valid: int, in_data: int) -> None:
        cfg, tb = self.cfg, self.tb
        # values visible during this cycle (registered outputs of both cores)
        r_valid, r_data, r_idx = self.row.dout_valid, self.row.dout, self.row.dout_index
        c_valid, c_data = self.col.dout_valid, self.col.dout
        start_now = (not tb.started) and r_valid and r_idx == 0
        active = tb.started or start_now
        if active:
            tau = tb.tau
            mode = tb.frame % 2
            a = tb.addr(tau, mode)
            rd = tb.mem[a]
            col_valid = self.read_tag
            tag_w = r_valid if tau == 0 else self.frame_tag
            # column core consumes the transposed stream in the same cycle
            self.col.step(col_valid, rd)
            tb.mem[a] = r_data
            # frame bookkeeping (clock edge)
            if tau == 0:
                self.frame_tag = tag_w
            tb.tau = (tau + 1) % 64
            if tb.tau == 0:
                tb.frame += 1
                self.read_tag = self.frame_tag
            tb.started = True
        # final rounding register
        self.dout = wrap(shift_round(c_data, cfg.out_shift), cfg.out_w)
        self.dout_valid = c_valid
        self.row.step(in_valid, in_data)
        self.cycle += 1


def run_stream_2d(blocks, cfg: Config2D = Config2D(), flush_cycles: int = 300):
    """Stream 8x8 blocks (row-major samples) through the 2-D machine.

    Returns ``(outputs, first_valid_cycle)`` where ``outputs`` is the list of
    valid output words in emission order (column-major per block).
    """
    m = DCT2DMachine(cfg)
    outs, first = [], None
    stream = [(1, int(v)) for blk in blocks for v in np.asarray(blk).reshape(-1)]
    stream += [(0, 0)] * flush_cycles
    for valid, v in stream:
        m.step(valid, v)
        if m.dout_valid:
            if first is None:
                first = m.cycle
            outs.append(m.dout)
    return outs, first
