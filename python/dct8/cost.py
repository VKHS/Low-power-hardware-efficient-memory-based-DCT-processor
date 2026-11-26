"""Architecture-level hardware cost of the processor, derived from the RTL structure.

Counts of the arithmetic operators, register bits and memory words that ``rtl/``
instantiates for a configuration -- not synthesis results.  The safe-scaling
units cost no adder (von Neumann rounding is an OR gate); every other rounding
shift adds a carry-in, counted separately as a rounding increment.  (The FPGA
numbers of the paper are quoted separately in the README; scripts/ contains the
Vivado flow to measure this RTL.)
"""
from __future__ import annotations

from dataclasses import dataclass

from . import cordic2, schedule
from .processor import Config


@dataclass
class Cost:
    adders: dict
    adder_bits: dict
    register_bits: dict
    memory_words: dict
    rounding_increments: int = 0
    multipliers: int = 0

    @property
    def total_adders(self) -> int:
        return sum(self.adders.values())

    @property
    def total_adder_bits(self) -> int:
        return sum(self.adder_bits.values())

    @property
    def total_register_bits(self) -> int:
        return sum(self.register_bits.values())


def processor_cost(cfg: Config = Config(), sch: schedule.Schedule | None = None) -> Cost:
    sch = sch or schedule.build()
    w, wm = cfg.w, cfg.mr_width
    mr = cordic2.adder_count(cfg.mr_mode)
    adders = {"butterfly datapath BF0": 2, "butterfly datapath BF1": 2,
              **{f"CORDIC: {k}": v for k, v in mr.items()}}
    adder_bits = {"butterfly datapath BF0": 2 * (w + 1), "butterfly datapath BF1": 2 * (w + 1)}
    wa = wm + 3 if cfg.mr_mode == "cordic2x" else wm
    for k, v in mr.items():
        adder_bits[f"CORDIC: {k}"] = v * (wa if k.startswith("friend") else wm)
    regs = {f"bank {b}": n * w for b, n in sch.nregs.items()}
    regs["CORDIC pipeline register"] = 2 * wm + 2
    regs["output register"] = w + 3 + 1 + 1
    regs["controller (phase, block tags)"] = 3 + sch.out_block_offset + 2
    return Cost(adders, adder_bits, regs, dict(sch.nregs), cordic2.rounding_count(cfg.mr_mode))


# Arithmetic operations of classic fast 8-point DCT algorithms (from the literature)
LITERATURE_OPS = {
    "Chen et al. (1977)": {"mult": 16, "add": 26},
    "Loeffler et al. (1989)": {"mult": 11, "add": 29},
    "Arai-Agui-Nakajima (1988), scaled": {"mult": 5, "add": 29},
}


def ops_per_block() -> dict:
    return {"butterflies": 12, "rotations": 5, "multiplications": 0}
