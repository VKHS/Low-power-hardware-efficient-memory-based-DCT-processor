# Vitis HLS

| file | content |
|---|---|
| `src/dct8_arith.h` | bit-accurate butterfly datapath and central CORDIC unit (`MR<W, G, MODE>`, both modes) |
| `src/dct8_hls.h` | configuration macros and the kernels `dct8_block_stream`, `dct8_cycle_stream`, 2-D passes |
| `src/dct8_sched.h` | **generated** microcode (same tables as `rtl/dct8_ctrl.v`) |
| `src/dct8_top.cpp` | synthesis tops `dct8_block_top`, `dct8_cycle_top`, `dct2d_top` |
| `tb/tb_dct8.cpp`, `tb/tb_dct2d.cpp` | C test benches against `vectors/` |
| `run_hls.tcl` | C simulation, synthesis, IP export: `vitis_hls -f hls/run_hls.tcl -tclargs dct8_cycle_top` |
| `csim_compat/` | minimal `ap_int.h` / `hls_stream.h` stand-ins for C simulation with a plain C++ compiler |

* `dct8_block_top` — one block per 8 clocks (`PIPELINE II=8`), `ALLOCATION` of two butterfly
  datapaths and one CORDIC unit: the tool time-shares them like the hand-written RTL.
* `dct8_cycle_top` — the RTL micro-architecture, one loop iteration per clock (`II=1`),
  cycle-exact with `rtl/dct8_core.v` (same latency, same output words every clock).
* `dct2d_top` — row pass, single-buffer transpose, column pass, final scaling (`DATAFLOW`).

`python3 scripts/run_hls_csim.py` compiles and runs the C simulation of every vector set
with g++ (`--ap-include <dir>` uses the official `ap_int.h` instead of the stand-ins).
