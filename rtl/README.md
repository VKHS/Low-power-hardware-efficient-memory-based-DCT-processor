# RTL

Verilog-2005, synchronous active-high reset, no vendor primitives.

| file | content |
|---|---|
| `dct8_core.v` | 1-D processor: input buffer, butterfly unit (BF0, BF1), M_B, memory bank, central CORDIC unit, output buffer, controller |
| `cordic2_mr.v` | central CORDIC unit; `MR_MODE` 0 = Table 1 micro-rotations, 1 = CORDIC-II |
| `dct8_bf_pe.v` | butterfly datapath `a ± b` with the safe-scaling unit (von Neumann rounding) |
| `dct8_mem_bank.v` | N-word register file, NWP write ports, NRP asynchronous read ports, read-before-write |
| `dct8_ctrl.v` | **generated** (`python -m dct8 emit`): phase decoders of BF0, BF1, CORDIC and I/O |
| `dct8_sched_params.vh` | **generated**: bank sizes, latency, output phase |
| `dct8_adders.v` | 3:2 and 4:2 compressors, Kogge-Stone adder, 3- and 5-operand adders (`STYLE` 0 behavioural, 1 carry-save) |
| `dct8_round.v` | rounding shifts `rnd` (half up), `rne` (half even), `rnd_sel` (shift selected before rounding) |
| `dct2d_8x8.v` | 8×8 2-D processor: row core → `dct8_transpose` → column core → final scaling |
| `dct8_transpose.v` | single 64-word transpose memory with alternating row/column-major addressing |

`dct8_core #(B_IN, W, G, SS1, SS2, SS3, MR_MODE, STYLE)`:
`clk, rst, ce, in_valid, in_data[B_IN-1:0] → out_valid, out_index[2:0], out_last, out_data[W-1:0]`;
one sample per clock in natural order, the first coefficient 16 clocks after `x0`,
`out_data = 2√2 · X_k · 2^E` with `E = W − B_IN − 3`.

Simulation: `python3 scripts/run_rtl.py` (Icarus, every vector set, both adder styles);
synthesis: `vivado -mode batch -source scripts/vivado_synth.tcl -tclargs dct8_core 14 0 6.9`.
