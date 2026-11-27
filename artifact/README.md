# Results page

[`index.html`](index.html) is one self-contained page: the results of the repository together
with the evidence behind each number. It needs no network access and no other file; download it
and open it in a browser. The theme follows the system setting and can be switched with the
button in the header; every chart can be shown as a table.

## What the page shows

| Section | Content | Computed by |
|---|---|---|
| Claims | 14 claims, each with its evidence, the command that reproduces it and its basis | `dct8.evidence.claims` |
| Re-run in this browser | the nine golden vector sets are hashed (SHA-256) and replayed through an independent JavaScript model of both processors and both rotation units; eight deliberate arithmetic faults and ten schedule faults show that the checks can fail | `artifact/src/model.js`, `sched.js`, `sha256.js` |
| Accuracy | 1-D SQNR and 8×8 PSNR against the double-precision DCT for W = 8 … 16 and both rotation sets; zonal compression; the paper's Table 3 on the same axes | `dct8.evidence.accuracy_1d`, `accuracy_2d`, `compression`, `paper_alignment` |
| Dynamic range | the largest value of every flow-graph node and CORDIC register in 120 configurations, with a control run that must fail | `dct8.evidence.overflow`, `overflow_control` |
| Schedule and memory | modulo schedule of period 8, unit utilisation, memory words and ports, input/output timing; nine invariants checked from `vectors/schedule.json` | `dct8.evidence.schedule_data` |
| Cost and design space | adders, rounding increments, register bits, multipliers; the realised angles and gains of both rotation sets; the 16-point extension | `dct8.evidence.cost_table`, `design_space`, `dct16_errors` |
| FPGA figures | the paper's Table 2 as quoted; the row for this repository's RTL stays red until the Vivado figures are entered | `scripts/vivado_synth.tcl` |

## Basis of a number

| Label | Meaning |
|---|---|
| built | computed by `python/dct8/evidence.py` from the bit-accurate models, the golden vectors and the schedule when the page is built |
| CI | established by a CI job that runs outside Python (Verilog simulation, HLS C simulation, MATLAB/Octave) |
| paper | quoted from the paper, not re-measured here |
| pending | not measured yet (shown in red) |

No value on the page is estimated or projected.

## Commands

```bash
python3 scripts/make_artifact.py              # recompute everything (about 70 s), write data/evidence.json and index.html
python3 scripts/make_artifact.py --assemble   # keep data/evidence.json, rebuild index.html only
python3 scripts/make_artifact.py --check      # recompute and compare with what is committed (used by CI)
node artifact/tests/selfcheck.js artifact/index.html   # JavaScript checks of the page without a browser
make artifact                                 # rebuild (first command), then the JavaScript checks
make artifact-check                           # compare (third command), then the JavaScript checks
```

`--check` fails when the committed data differ from a fresh run (integers, text and booleans
exactly; floating-point values within a small tolerance, so that another NumPy build does not
trip it) or when `index.html` is not the page that the committed inputs produce.

## Freshness

`data/evidence.json` records the SHA-256 of `python/dct8/*.py` and `vectors/*`. The test
`python/tests/test_evidence.py::test_evidence_was_generated_from_the_current_sources` fails
after any change to those files until `python3 scripts/make_artifact.py` has been run again.

## Two implementations

The Python modules produce the data. The page also re-computes the vector results with a second
implementation in JavaScript (`src/model.js`, `src/sched.js`) that shares no code with
`python/dct8`; its tables are transcribed again. The two agree word for word on the 22,000
expected words and, check by check, on the schedule. What they share are the input files
`vectors/*` (digests on the page), including `vectors/schedule.json`.

## Files

```text
artifact/
├── index.html                       the page (generated)
├── README.md
├── data/
│   ├── evidence.json                every number of the page (generated)
│   └── fpga_measured.template.json  the figures to enter once Vivado has been run
├── src/
│   ├── template.html, style.css     layout and styles
│   ├── app.js                       sections, charts, tables, tooltips
│   ├── model.js, sched.js           the JavaScript models and the schedule checker
│   └── sha256.js                    SHA-256 for the digests
└── tests/selfcheck.js               the JavaScript checks, runnable with Node
```

## Entering the Vivado figures

1. `vivado -mode batch -source scripts/vivado_synth.tcl` (options in the script header).
2. Copy `data/fpga_measured.template.json` to `data/fpga_measured.json` and replace each
   `null` with the value from the reports in `build/vivado_dct8_core_w14_m<mode>/`; the
   template says which line of which report each field comes from.
3. `python3 scripts/make_artifact.py --assemble`.

The build stops with a message when a field is missing, empty or of the wrong kind.

## Scope of the checks

* The range scan covers 69,536 inputs per configuration (the 65,536 near-corner inputs
  {−128, −127, 126, 127}⁸ and 4,000 random ones). It is a test and not a formal proof; the
  control run, with the input alignment one bit too high, shows that it can fail.
* The cost table counts operators in the RTL structure; it is not a synthesis result.
* The test images (scikit-image samples) differ from the paper's BSD-100 set, and Table 3 of the
  paper does not state how its word length is split into integer and fraction bits; the page
  compares the slopes and the equal-PSNR offsets, and says so.
