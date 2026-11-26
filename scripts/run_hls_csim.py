#!/usr/bin/env python3
"""C simulation of the HLS kernels against every vector set in vectors/manifest.json.

    python3 scripts/run_hls_csim.py                    # g++ with hls/csim_compat headers
    python3 scripts/run_hls_csim.py --ap-include DIR   # official ap_int.h (HLS_arbitrary_Precision_Types/include)

Each configuration is compiled with the matching -D macros and run; the script
exits non-zero if any test bench fails.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def flags(entry: dict) -> list[str]:
    p = entry["params"]
    if entry["kind"] == "dct8":
        return [f"-DDCT_B_IN={p['B_IN']}", f"-DDCT_W={p['W']}", f"-DDCT_G={p['G']}",
                f"-DDCT_SS1={p['SS1']}", f"-DDCT_SS2={p['SS2']}", f"-DDCT_SS3={p['SS3']}",
                f"-DDCT_MR_MODE={p['MR_MODE']}", f"-DDCT_FIRST_OUT={entry['first_out_cycle']}"]
    return [f"-DDCT_B_IN={p['B_IN']}", f"-DDCT2D_W_ROW={p['W_ROW']}", f"-DDCT2D_G_ROW={p['G_ROW']}",
            f"-DDCT2D_SS_ROW={p['SS1_ROW']},{p['SS2_ROW']},{p['SS3_ROW']}",
            f"-DDCT2D_W_COL={p['W_COL']}", f"-DDCT2D_G_COL={p['G_COL']}",
            f"-DDCT2D_SS_COL={p['SS1_COL']},{p['SS2_COL']},{p['SS3_COL']}",
            f"-DDCT2D_OUT_W={p['OUT_W']}", f"-DDCT2D_OUT_FRAC={p['OUT_FRAC']}",
            f"-DDCT_MR_MODE={p['MR_MODE']}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx", default=os.environ.get("CXX", "g++"))
    ap.add_argument("--ap-include", default=None,
                    help="directory with the official ap_int.h (default: hls/csim_compat)")
    ap.add_argument("--build", default=str(ROOT / "build" / "hls"))
    ap.add_argument("--only", default=None, help="comma-separated vector names")
    a = ap.parse_args()
    if shutil.which(a.cxx) is None:
        print(f"{a.cxx} not found")
        return 2
    man = json.loads((ROOT / "vectors" / "manifest.json").read_text())
    names = a.only.split(",") if a.only else list(man)
    build = Path(a.build)
    build.mkdir(parents=True, exist_ok=True)
    inc = []
    if a.ap_include:
        inc += ["-I", a.ap_include]
    inc += ["-I", str(ROOT / "hls" / "src"), "-I", str(ROOT / "hls" / "csim_compat"),
            "-I", str(ROOT / "hls" / "tb")]
    failed = []
    for name in names:
        e = man[name]
        tb = "tb_dct8.cpp" if e["kind"] == "dct8" else "tb_dct2d.cpp"
        exe = build / f"{name}{'_official' if a.ap_include else ''}"
        cmd = [a.cxx, "-std=c++14", "-O2", "-Wall", "-Wno-unknown-pragmas", *inc, *flags(e),
               str(ROOT / "hls" / "src" / "dct8_top.cpp"), str(ROOT / "hls" / "tb" / tb), "-o", str(exe)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f"COMPILE FAIL {name}\n{r.stderr[-3000:]}")
            failed.append(name)
            continue
        r = subprocess.run([str(exe), str(ROOT / "vectors"), name], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
        if r.returncode:
            failed.append(name)
    print("ALL PASS" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
