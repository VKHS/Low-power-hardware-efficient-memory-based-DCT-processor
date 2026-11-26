#!/usr/bin/env bash
# Smoke test: everything that the tools installed on this machine can run.
#   python tests -> HLS C simulation (g++) -> RTL simulation (Icarus) -> MATLAB/Octave
# Missing tools are reported and skipped; any failing check makes the script fail.
set -u
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
pass=(); fail=(); skip=()

run() {   # name, command...
    local name=$1; shift
    echo "=== $name"
    if "$@"; then pass+=("$name"); else fail+=("$name"); fi
}

run "python: unit tests" "$PY" -m pytest -q python/tests
if command -v "${CXX:-g++}" >/dev/null; then
    run "hls: C simulation (all vector sets)" "$PY" scripts/run_hls_csim.py
else
    skip+=("hls (no C++ compiler)")
fi
if command -v iverilog >/dev/null; then
    run "rtl: Icarus simulation (all vector sets, STYLE 0)" "$PY" scripts/run_rtl.py --style 0
else
    skip+=("rtl (Icarus Verilog not installed)")
fi
if command -v octave >/dev/null; then
    run "matlab: run_tests (Octave)" octave --no-gui --eval "addpath('matlab'); run_tests"
elif command -v matlab >/dev/null; then
    run "matlab: run_tests" matlab -batch "addpath('matlab'); run_tests"
else
    skip+=("matlab (neither Octave nor MATLAB installed)")
fi

echo
for s in "${pass[@]}"; do echo "PASS  $s"; done
for s in "${skip[@]+"${skip[@]}"}"; do echo "SKIP  $s"; done
for s in "${fail[@]+"${fail[@]}"}"; do echo "FAIL  $s"; done
[ ${#fail[@]} -eq 0 ]
