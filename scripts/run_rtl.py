#!/usr/bin/env python3
"""RTL simulation with Icarus Verilog against every vector set in vectors/manifest.json.

    python3 scripts/run_rtl.py                 # all configurations, STYLE 0 and 1
    python3 scripts/run_rtl.py --style 0 --only dct8_t1_w14,dct2d_t1

Each configuration is compiled with the matching -P parameters (the self-checking
test benches in sim/ compare every output word bit for bit) and the script exits
non-zero if any run does not print PASS.
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default="0,1", help="adder styles to simulate (0 behavioural, 1 CSA+CLA)")
    ap.add_argument("--only", default=None, help="comma-separated vector names")
    ap.add_argument("--build", default=str(ROOT / "build" / "rtl"))
    a = ap.parse_args()
    for tool in ("iverilog", "vvp"):
        if shutil.which(tool) is None:
            print(f"{tool} not found (install Icarus Verilog)")
            return 2
    man = json.loads((ROOT / "vectors" / "manifest.json").read_text())
    names = a.only.split(",") if a.only else list(man)
    build = Path(a.build)
    build.mkdir(parents=True, exist_ok=True)
    rtl = sorted(glob.glob(str(ROOT / "rtl" / "*.v")))
    failed = []
    for name in names:
        e = man[name]
        top = "tb_dct8_core" if e["kind"] == "dct8" else "tb_dct2d_8x8"
        for style in a.style.split(","):
            params = dict(e["params"], STYLE=int(style), N_STIM=e["n_stim"], N_EXP=e["n_expect"],
                          FIRST_OUT=e["first_out_cycle"])
            exe = build / f"{name}_s{style}.vvp"
            cmd = ["iverilog", "-g2005", "-I", str(ROOT / "rtl"), "-s", top, "-o", str(exe)]
            for k, v in params.items():
                cmd += ["-P", f"{top}.{k}={v}"]
            cmd += rtl + [str(ROOT / "sim" / f"{top}.v")]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode:
                print(f"COMPILE FAIL {name} STYLE={style}\n{r.stderr[-3000:]}")
                failed.append(f"{name}/s{style}")
                continue
            r = subprocess.run(["vvp", "-n", str(exe),
                                f"+stim={ROOT / 'vectors' / (name + '_stim.hex')}",
                                f"+expect={ROOT / 'vectors' / (name + '_expect.hex')}"],
                               capture_output=True, text=True)
            lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))]
            print(f"{name:14s} STYLE={style}: {lines[-1] if lines else r.stdout[-500:]}")
            if not lines or not lines[-1].startswith("PASS"):
                failed.append(f"{name}/s{style}")
    print("ALL PASS" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
