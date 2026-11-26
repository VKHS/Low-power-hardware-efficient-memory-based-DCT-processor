# Convenience targets (each one is a thin wrapper around a script)
PY ?= python3

.PHONY: all smoke test python rtl hls matlab emit vectors figures report clean

all: test

smoke:                 ## everything the installed tools can run
	./scripts/smoke_test.sh

test: python hls rtl matlab

python:                ## unit tests, overflow proof, schedule invariants
	$(PY) -m pytest -q python/tests

rtl:                   ## Icarus Verilog, every vector set, both adder styles
	$(PY) scripts/run_rtl.py

hls:                   ## C simulation of the HLS kernels with g++
	$(PY) scripts/run_hls_csim.py

matlab:                ## MATLAB/Octave model against the vectors
	octave --no-gui --eval "addpath('matlab'); run_tests"

emit:                  ## regenerate rtl/dct8_ctrl.v, rtl/dct8_sched_params.vh, hls/src/dct8_sched.h
	cd python && $(PY) -m dct8 emit

vectors:               ## regenerate the golden vectors
	cd python && $(PY) -m dct8 vectors

figures:               ## regenerate figures/
	$(PY) scripts/make_figures.py

report:                ## regenerate docs/results.md
	$(PY) scripts/report.py > docs/results.md

clean:
	rm -rf build python/.pytest_cache
