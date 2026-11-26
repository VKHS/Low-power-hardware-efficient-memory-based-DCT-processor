"""Cycle-accurate model of the memory-based processor (mirrors the RTL register by register).

One call of :meth:`DCT8Machine.step` is one rising clock edge.  Within a cycle
all memory reads see the values *before* the edge and all writes commit at the
edge -- the read-before-write register-file semantics of the RTL.  The control
is the per-phase microcode of :mod:`dct8.schedule`, i.e. the same tables that
are emitted into ``rtl/dct8_ctrl.v`` and ``hls/src/dct8_sched.h``.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import cordic2, schedule
from .fixedpoint import wrap
from .processor import Config, bf


@dataclass
class OutSample:
    cycle: int
    index: int
    data: int
    last: bool


class DCT8Machine:
    def __init__(self, cfg: Config = Config(), sch: schedule.Schedule | None = None):
        self.cfg = cfg
        self.sch = sch or schedule.build()
        if self.sch.mr_lat != 2:
            raise ValueError("the RTL CORDIC unit has two pipeline stages (mr_lat = 2)")
        self.reset()

    def reset(self) -> None:
        self.mem = {b: [0] * n for b, n in self.sch.nregs.items()}
        self.mr_a = (0, 0, 1)                    # CORDIC stage-A pipeline register (x, y, k)
        self.phase = 0
        self.tags = [0] * (self.sch.out_block_offset + 1)
        self.out_tag = 0
        self.dout = 0
        self.dout_valid = 0
        self.dout_index = 0
        self.dout_last = 0
        self.cycle = 0

    def _read(self, bank: str, reg, x_in: int) -> int:
        return x_in if bank == "IN" else self.mem[bank][reg]

    def step(self, in_valid: int, in_data: int, ce: int = 1) -> None:
        if not ce:
            return
        cfg, row = self.cfg, self.sch.table[self.phase]
        x_in = wrap(int(in_data), cfg.b_in) << cfg.f_in
        writes: list[tuple[str, int, int]] = []

        # butterfly unit: two datapaths
        for op in row["bf"]:
            if op is None:
                continue
            a = self._read(*op["src"][0], x_in)
            b = self._read(*op["src"][1], x_in)
            s, d = bf(a, b, cfg.scale(op["stage"]), cfg.w)
            writes += [(op["dst"][0][0], op["dst"][0][1], s), (op["dst"][1][0], op["dst"][1][1], d)]

        # central CORDIC unit, stage B (finishes the rotation issued last cycle)
        if row["mr_done"]:
            x, y, k = self.mr_a
            u, v = cordic2.mr_stage_b(x, y, k, cfg.guard, cfg.mr_mode)
            (b0, r0), (b1, r1) = row["mr_done"]["dst"]
            writes += [(b0, r0, wrap(u, cfg.w)), (b1, r1, wrap(v, cfg.w))]

        # central CORDIC unit, stage A (issue)
        mr_a_next = self.mr_a
        if row["mr_issue"]:
            iss = row["mr_issue"]
            u = self._read(*iss["src"][0], x_in)
            v = self._read(*iss["src"][1], x_in)
            x, y = cordic2.mr_stage_a(u, v, iss["k"], cfg.guard, cfg.mr_mode)
            mr_a_next = (x, y, iss["k"])

        if row["ib_w"] is not None:
            writes.append(("IB", row["ib_w"], x_in))

        # rearrange / output stage: in-order read of the output buffer
        k_out = row["out_k"]
        po = self.sch.out_phase
        tag_now = self.tags[self.sch.out_block_offset] if self.phase == po else self.out_tag
        dout_next = (self.mem["OB"][row["ob_r"]], k_out, int(k_out == 7), tag_now)

        # ---- clock edge
        for bank, reg, val in writes:
            self.mem[bank][reg] = val
        self.mr_a = mr_a_next
        if self.phase == po:
            self.out_tag = tag_now
        if self.phase == 0:
            self.tags = [int(bool(in_valid))] + self.tags[:-1]
        self.dout, self.dout_index, self.dout_last, self.dout_valid = dout_next
        self.phase = (self.phase + 1) % schedule.PERIOD
        self.cycle += 1


def run_stream(blocks, cfg: Config = Config(), flush_blocks: int = 3, gap_blocks=()) -> list:
    """Stream blocks (8 ints each) through the machine and return the valid outputs.

    An invalid (all-zero) block is inserted before every position in ``gap_blocks``.
    """
    m = DCT8Machine(cfg)
    seq = []
    for i, blk in enumerate(blocks):
        if i in gap_blocks:
            seq.append((0, [0] * 8))
        seq.append((1, list(blk)))
    seq += [(0, [0] * 8)] * flush_blocks
    outs = []
    for valid, blk in seq:
        for n in range(8):
            m.step(valid, blk[n])
            if m.dout_valid:
                outs.append(OutSample(m.cycle, m.dout_index, m.dout, bool(m.dout_last)))
    return outs
