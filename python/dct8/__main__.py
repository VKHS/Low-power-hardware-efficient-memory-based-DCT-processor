"""Command line: ``python -m dct8 {info,emit,vectors,schedule}``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cordic2, cost, emit, processor, schedule, vectors

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dct8")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="print the micro-rotation table, schedule and cost")
    e = sub.add_parser("emit", help="regenerate the controller RTL, schedule parameters and HLS tables")
    e.add_argument("--root", default=str(ROOT))
    v = sub.add_parser("vectors", help="regenerate golden vectors")
    v.add_argument("--out", default=str(ROOT / "vectors"))
    s = sub.add_parser("schedule", help="dump the schedule as JSON")
    s.add_argument("--mr-lat", type=int, default=schedule.DEFAULT_MR_LAT)
    a = ap.parse_args(argv)

    if a.cmd == "info":
        for mode in cordic2.MODES:
            print(f"central CORDIC unit, mode {mode}")
            for r in cordic2.analyze(mode):
                print(f"  k={r.k}: target {r.target_deg:7.4f} deg  realised {r.realised_deg:8.5f} deg"
                      f"  angle error {r.angle_err_rad:+.2e} rad  gain {r.gain:.6f}")
        sch = schedule.build()
        print(f"\nschedule: T0 = {sch.t0}, words {sch.nregs}, ops {sch.times}")
        for mode in cordic2.MODES:
            c = cost.processor_cost(processor.Config(mr_mode=mode))
            print(f"cost (W=14, G=3, {mode}): {c.total_adders} adders ({c.total_adder_bits} adder bits), "
                  f"{c.rounding_increments} rounding increments, {c.total_register_bits} register bits, "
                  f"0 multipliers")
    elif a.cmd == "emit":
        sch = emit.write(a.root)
        print(f"wrote rtl/dct8_ctrl.v, rtl/dct8_sched_params.vh, hls/src/dct8_sched.h, "
              f"vectors/schedule.json (T0 = {sch.t0}, words {sch.nregs})")
    elif a.cmd == "vectors":
        man = vectors.write_all(a.out)
        for k, m in man.items():
            print(f"{k:16s} blocks={m['n_blocks']:4d} expect={m['n_expect']:5d} "
                  f"first_out_cycle={m['first_out_cycle']}")
    elif a.cmd == "schedule":
        print(schedule.build(a.mr_lat).to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
