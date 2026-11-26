"""2-D processor, 16-point extension, verification flow and I/O timing diagrams."""
from __future__ import annotations

import numpy as np
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

from dct8 import scalable

from .style import (BF_EDGE, BF_FILL, CTL_EDGE, CTL_FILL, GRID, HL_EDGE, HL_FILL, INK, INK2,
                    IO_EDGE, IO_FILL, MEM_EDGE, MEM_FILL, MR_EDGE, MR_FILL, S1, S2, arrow, box,
                    canvas, dot, label, path, save)


# ---------------------------------------------------------------------------- 2-D processor
def _grid(ax, x0, y0, size, mode, title):
    c = size / 8
    for i in range(9):
        ax.plot([x0, x0 + size], [y0 + i * c, y0 + i * c], color=MEM_EDGE, lw=0.6, zorder=2)
        ax.plot([x0 + i * c, x0 + i * c], [y0, y0 + size], color=MEM_EDGE, lw=0.6, zorder=2)
    ax.add_patch(Rectangle((x0, y0), size, size, facecolor=MEM_FILL, edgecolor="none", zorder=1))
    pts = []
    for tau in range(64):
        a = tau if mode == 0 else 8 * (tau % 8) + tau // 8
        r, col = divmod(a, 8)
        pts.append((x0 + (col + 0.5) * c, y0 + size - (r + 0.5) * c))
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=MEM_EDGE, lw=1.0, zorder=3)
    ax.scatter([xs[0]], [ys[0]], s=14, color=INK, zorder=4)
    arrow(ax, pts[-2], pts[-1], color=MEM_EDGE, lw=1.0, ms=7, z=4)
    label(ax, x0 + size / 2, y0 - 0.38, title, fs=7.0, color=INK)


def dct2d(path_out) -> None:
    fig, ax = canvas(17.0, 6.3, scale=0.66)
    y = 4.9
    label(ax, 0.2, y + 0.35, "pixels", fs=9, color=INK, ha="left", bold=True)
    label(ax, 0.2, y - 0.35, "row-major\n8 bit, 1/clk", fs=7, ha="left", va="top")
    arrow(ax, (1.35, y), (1.8, y), ms=8)
    box(ax, 1.8, y - 0.85, 2.9, 1.7, "", fill=BF_FILL, edge=BF_EDGE, radius=0.12, lw=1.3)
    label(ax, 3.25, y + 0.45, "row processor", fs=8.5, color=INK, bold=True)
    label(ax, 3.25, y - 0.15, "dct8_core\n$W_{ROW}$ = 14, SS 000", fs=7, color=INK)
    arrow(ax, (4.7, y), (5.3, y), ms=8)
    label(ax, 5.0, y + 0.25, "$Y_r$", fs=7.5)
    box(ax, 5.3, y - 0.85, 4.2, 1.7, "", fill=MEM_FILL, edge=MEM_EDGE, radius=0.12, lw=1.3)
    label(ax, 7.4, y + 0.45, "transpose buffer", fs=8.5, color=INK, bold=True)
    label(ax, 7.4, y - 0.2, "ONE 64-word memory: each word is read\n(previous block) and re-written "
          "(current\nblock) in the same clock", fs=6.8, color=INK)
    arrow(ax, (9.5, y), (10.1, y), ms=8)
    box(ax, 10.1, y - 0.85, 2.9, 1.7, "", fill=BF_FILL, edge=BF_EDGE, radius=0.12, lw=1.3)
    label(ax, 11.55, y + 0.45, "column processor", fs=8.5, color=INK, bold=True)
    label(ax, 11.55, y - 0.15, "dct8_core\n$W_{COL}$ = 16, SS 111", fs=7, color=INK)
    arrow(ax, (13.0, y), (13.5, y), ms=8)
    box(ax, 13.5, y - 0.85, 1.9, 1.7, "", fill=IO_FILL, edge=IO_EDGE, radius=0.12)
    label(ax, 14.45, y + 0.4, "final scaling", fs=8, color=INK, bold=True)
    label(ax, 14.45, y - 0.25, "round half to\neven by\nOUT_SHIFT bits", fs=6.6, color=INK)
    arrow(ax, (15.4, y), (15.85, y), ms=8)
    label(ax, 16.9, y + 0.35, "X[u][v]", fs=9, color=INK, ha="right", bold=True)
    label(ax, 16.9, y - 0.35, "column by\ncolumn", fs=7, ha="right", va="top")

    _grid(ax, 5.35, 0.75, 1.75, 0, "even blocks\nrow-major")
    _grid(ax, 7.75, 0.75, 1.75, 1, "odd blocks\ncolumn-major")
    label(ax, 7.4, 3.25, "address order alternates per block:\naddr = τ  |  addr = 8(τ mod 8) + ⌊τ/8⌋",
          fs=6.9, color=INK)
    ax.plot([7.4, 7.4], [3.65, y - 0.85], color=MEM_EDGE, lw=0.8, ls=(0, (2, 2)))

    # timing and scaling notes
    notes = [("latency", "16 (row) + 64 (transpose) + 16 (column) + 1 = 97 clocks"),
             ("throughput", "one pixel in and one coefficient out per clock"),
             ("scaling", r"$(2\sqrt{2})^2 = 8$: the column output is $2^{E_r + E_c + 3} X$, "
                         "only a shift remains"),
             ("memory", "64 + 2 × 19 words (a ping-pong transpose: 128 + 2 × 19)")]
    for i, (a, b) in enumerate(notes):
        label(ax, 10.3, 2.75 - 0.5 * i, a, fs=7.4, color=INK, ha="left", bold=True)
        label(ax, 11.85, 2.75 - 0.5 * i, b, fs=7.2, color=INK, ha="left")
    save(fig, path_out)


# ---------------------------------------------------------------------------- 16-point
def dct16(path_out) -> None:
    fig, ax = canvas(15.6, 10.4, scale=0.7)
    y = lambda r: 9.6 - r * 0.58                                              # noqa: E731
    # inputs and stage-1 butterflies
    for n in range(16):
        label(ax, 0.75, y(n), f"x[{n}]", fs=7.5, color=INK, ha="right")
    box(ax, 1.0, y(15) - 0.3, 2.2, y(0) - y(15) + 0.6, "", fill=BF_FILL, edge=BF_EDGE, radius=0.12)
    label(ax, 2.1, y(0) + 0.55, "stage-1 butterflies", fs=8, color=INK, bold=True)
    for m in range(8):
        yy = (y(2 * m) + y(2 * m + 1)) / 2
        label(ax, 2.1, yy, f"$x[{2*m}] \\pm x[{2*m+1}]$", fs=6.6, color=INK)
    label(ax, 2.1, y(15) - 0.6, "$(-1)^m$: operand order", fs=6.6)
    # two 8-point processors
    for (r0, nm, inp, outn) in ((0, "8-point processor", r"$x_L[m] = x[2m] + x[2m+1]$", "A"),
                                (8, "8-point processor", r"$(-1)^m x_H[m]$", "B")):
        top, bot = y(r0) + 0.3, y(r0 + 7) - 0.2
        box(ax, 4.0, bot, 3.0, top - bot, "", fill=BF_FILL, edge=BF_EDGE, radius=0.12, lw=1.3)
        label(ax, 5.5, (top + bot) / 2 + 0.35, nm, fs=8.5, color=INK, bold=True)
        label(ax, 5.5, (top + bot) / 2 - 0.25, "(this processor, 9-bit input)", fs=6.8)
        label(ax, 5.5, (top + bot) / 2 - 0.75, inp, fs=7)
        arrow(ax, (3.2, (top + bot) / 2), (4.0, (top + bot) / 2), ms=8)
        for k in range(8):
            label(ax, 7.2, y(r0 + k) + 0.15, f"${outn}_{k}$", fs=6.8, ha="left")
    # CORDIC array (in place: A_k on row k, B_{8-k} on row 16-k)
    xr = {k: 8.5 + (8 - k) * 0.62 for k in range(1, 8)}
    for r in range(16):
        ax.plot([7.0, 13.6], [y(r), y(r)], color=INK, lw=0.8, zorder=1)
    box(ax, 8.05, y(15) - 0.45, 5.15, y(0) - y(15) + 0.9, "", fill=MR_FILL, edge=MR_EDGE, radius=0.12,
        z=0)
    label(ax, 10.6, y(0) + 0.72, "CORDIC array (Table 5)", fs=8.5, color=INK, bold=True)
    for k in range(1, 8):
        a, b = scalable.TABLE5[k]
        xc = xr[k]
        ya, yb = y(k), y(16 - k)
        ax.plot([xc, xc], [ya, yb], color=MR_EDGE, lw=1.5, zorder=3)
        for yy in (ya, yb):
            ax.add_patch(FancyBboxPatch((xc - 0.2, yy - 0.11), 0.4, 0.22,
                                        boxstyle="round,pad=0,rounding_size=0.08",
                                        facecolor="white", edgecolor=MR_EDGE, lw=1.0, zorder=4))
        ym = (ya + yb) / 2 + (0.29 if k % 2 else -0.29)
        box(ax, xc - 0.29, ym - 0.17, 0.58, 0.34, f"{a}+j{b}", fill="white", edge=MR_EDGE, fs=5.5,
            z=5, radius=0.06)
    for k in range(16):
        dot(ax, 13.6, y(k), r=0.04)
        label(ax, 13.75, y(k), f"$Z_{{{k}}}$", fs=7.5, color=INK, ha="left")
    label(ax, 14.75, 5.25, r"$Z = 4X$", fs=8, color=INK2, rotation=90)
    label(ax, 10.5, y(15) - 0.85, r"rotator k: $(Z_k, Z_{16-k}) = \mathrm{Rot}(-k\pi/32)\,(A_k, B_{8-k})$,"
          r"  $Z_0 = A_0$,  $Z_8 = B_0$", fs=7, color=INK)
    save(fig, path_out)


# ---------------------------------------------------------------------------- verification flow
def flow(path_out) -> None:
    fig, ax = canvas(17.2, 9.6, scale=0.64)
    P_FILL, P_EDGE = BF_FILL, BF_EDGE
    G_FILL, G_EDGE = CTL_FILL, CTL_EDGE
    cols = [(0.3, "specification"), (3.9, "models (python/dct8)"),
            (8.25, "generated"), (12.1, "implementations and checks")]
    for x0, t in cols:
        label(ax, x0, 9.25, t, fs=9, color=INK, ha="left", bold=True)
    box(ax, 0.3, 6.1, 3.0, 2.6, "paper, Eqs. (4)-(13):\nscalable radix-2 DCT\n\nTable 1: micro-rotations\n"
        "Table 5: 16-point array", fill=IO_FILL, edge=IO_EDGE, fs=7.3)
    box(ax, 0.3, 3.0, 3.0, 2.5, "design decisions\n\nheadroom H = 3 - ΣSS\nvon Neumann SS rounding\n"
        "two butterfly datapaths", fill=IO_FILL, edge=IO_EDGE, fs=7.3)
    models = [("flowgraph.py", "12 butterflies + 5 rotations", 7.75),
              ("cordic2.py", "two micro-rotation modes", 6.65),
              ("processor.py", "bit-accurate functional model", 5.55),
              ("schedule.py", "exact modulo schedule, registers", 4.45),
              ("machine.py", "cycle-accurate model", 3.35)]
    for nm, d, yy in models:
        box(ax, 3.9, yy, 3.6, 0.85, "", fill=P_FILL, edge=P_EDGE)
        label(ax, 4.05, yy + 0.57, nm, fs=7.6, color=INK, ha="left", bold=True)
        label(ax, 4.05, yy + 0.24, d, fs=6.8, color=INK, ha="left")
    label(ax, 5.7, 2.85, "functional == cycle model\n(asserted while writing vectors)", fs=6.8, va="top")
    arrow(ax, (3.3, 7.4), (3.9, 7.4), ms=8)
    arrow(ax, (3.3, 4.25), (3.9, 4.25), ms=8)
    gens = [("rtl/dct8_ctrl.v", "decoders of the 3-bit phase", 7.75),
            ("rtl/dct8_sched_params.vh", "bank sizes, latency", 6.65),
            ("hls/src/dct8_sched.h", "same microcode for HLS", 5.55),
            ("vectors/", "9 configurations: stimulus,\nexpected words, manifest", 3.9)]
    for nm, d, yy in gens:
        h = 1.2 if nm == "vectors/" else 0.85
        box(ax, 8.25, yy, 3.3, h, "", fill=G_FILL, edge=G_EDGE)
        label(ax, 8.4, yy + h - 0.28, nm, fs=7.4, color=INK, ha="left", bold=True)
        label(ax, 8.4, yy + (0.3 if nm == "vectors/" else 0.24), d, fs=6.7, color=INK, ha="left")
    path(ax, [(7.5, 4.85), (7.85, 4.85), (7.85, 8.15), (8.25, 8.15)], ms=7)
    path(ax, [(7.85, 7.05), (8.25, 7.05)], ms=7)
    path(ax, [(7.85, 5.95), (8.25, 5.95)], ms=7)
    dot(ax, 7.85, 7.05, r=0.05)
    dot(ax, 7.85, 5.95, r=0.05)
    label(ax, 7.68, 7.05, "python -m dct8 emit", fs=6.4, rotation=90)
    path(ax, [(7.5, 3.75), (7.85, 3.75), (7.85, 4.5), (8.25, 4.5)], ms=7)
    label(ax, 8.3, 3.62, "python -m dct8 vectors", fs=6.4, ha="left")
    impls = [("rtl/ + sim/", "Verilog-2005 RTL, two adder styles;\nIcarus test benches, Verilator lint",
              7.45, MR_FILL, MR_EDGE),
             ("hls/", "Vitis HLS C++: block, cycle and 2-D\nDATAFLOW kernels; g++ C simulation",
              5.85, HL_FILL, HL_EDGE),
             ("matlab/", "MATLAB / Octave bit-accurate model\nand self-checking run_tests.m",
              4.25, MEM_FILL, MEM_EDGE),
             ("python/tests/", "overflow proof, schedule invariants,\naccuracy, artifacts up to date",
              2.65, P_FILL, P_EDGE)]
    for nm, d, yy, fc, ec in impls:
        box(ax, 12.1, yy, 4.7, 1.25, "", fill=fc, edge=ec)
        label(ax, 12.25, yy + 0.95, nm, fs=7.6, color=INK, ha="left", bold=True)
        label(ax, 12.25, yy + 0.45, d, fs=6.7, color=INK, ha="left")
    for yy in (8.05, 6.45, 4.85):
        path(ax, [(11.55, 4.5), (11.8, 4.5), (11.8, yy), (12.1, yy)], ms=7)
    box(ax, 5.2, 0.35, 11.6, 1.05, "", fill="white", edge=INK2, radius=0.1)
    label(ax, 11.0, 1.05, "every implementation reproduces every expected output word bit for bit,",
          fs=7.8, color=INK, bold=True)
    label(ax, 11.0, 0.65, "with the same latency (16 clocks 1-D, 97 clocks 2-D); CI runs every check on "
          "each push", fs=7.3, color=INK)
    save(fig, path_out)


# ---------------------------------------------------------------------------- I/O timing
def _bus(ax, y, t0, t1, text, fc="white", ec=INK, fs=6.3, h=0.32):
    d = 0.12
    pts = [(t0, y), (t0 + d, y + h), (t1 - d, y + h), (t1, y), (t1 - d, y - h), (t0 + d, y - h)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, lw=0.9, zorder=2))
    if text:
        ax.text((t0 + t1) / 2, y, text, ha="center", va="center", fontsize=fs, color=INK, zorder=3)


def _digital(ax, y, levels, X, h=0.3):
    xs, ys = [], []
    for t, v in enumerate(levels):
        yy = y + (h if v else -h)
        if ys and ys[-1] != yy:
            xs.append(X(t))
            ys.append(yy)
        xs += [X(t), X(t + 1)]
        ys += [yy, yy]
    ax.plot(xs, ys, color=INK, lw=1.2)


def timing(path_out) -> None:
    fig, ax = canvas(26.0, 8.6, scale=0.46)
    T = 48
    x0 = 3.2
    sx = (25.6 - x0) / T
    X = lambda t: x0 + t * sx                                                  # noqa: E731
    sig = ["clk", "in_valid", "in_data", "phase", "out_valid", "out_index", "out_data"]
    ys = {s: 7.75 - i * 1.0 for i, s in enumerate(sig)}
    for s_ in sig:
        label(ax, 2.9, ys[s_], s_, fs=8, color=INK, ha="right")
    for t in range(T + 1):
        ax.plot([X(t), X(t)], [1.35, 8.15], color=GRID, lw=0.6, zorder=0)
    for t in range(T):
        yy = ys["clk"]
        ax.plot([X(t), X(t), X(t + 0.5), X(t + 0.5), X(t + 1)],
                [yy - 0.3, yy + 0.3, yy + 0.3, yy - 0.3, yy - 0.3], color=INK, lw=0.9)
    blocks = [(0, "A", S1, 1), (8, "B", S2, 1), (16, "-", None, 0), (24, "C", "#00b894", 1)]
    vin = [0] * T
    vout = [0] * T
    for tb, nm, c, v in blocks:
        for n in range(8):
            vin[tb + n] = v
            if tb + 16 + n < T:
                vout[tb + 16 + n] = v
            _bus(ax, ys["in_data"], X(tb + n), X(tb + n + 1), f"x{n}" if v else "",
                 fc=(c + "30") if v else "#f4f4f4")
        if v:
            label(ax, X(tb + 4), ys["in_valid"] + 0.52, f"block {nm}", fs=7, color=INK)
    _digital(ax, ys["in_valid"], vin, X)
    _digital(ax, ys["out_valid"], vout, X)
    _bus(ax, ys["in_data"], X(32), X(T), "", fc="#f4f4f4")
    for t in range(T):
        _bus(ax, ys["phase"], X(t), X(t + 1), str(t % 8), fs=6)
    _bus(ax, ys["out_data"], X(0), X(16), "", fc="#f4f4f4")
    for t in range(T):                       # the index runs continuously (decoded phase)
        _bus(ax, ys["out_index"], X(t), X(t + 1), str(t % 8), fs=6)
    for tb, nm, c, v in blocks:
        t1 = tb + 16
        for k in range(8):
            if t1 + k >= T:
                break
            _bus(ax, ys["out_data"], X(t1 + k), X(t1 + k + 1), f"Y{k}" if v else "",
                 fc=(c + "30") if v else "#f4f4f4")
    arrow(ax, (X(0), 0.95), (X(16), 0.95), color=INK2, lw=0.9, style="<|-|>", ms=7)
    label(ax, X(8), 0.6, "latency 16 clocks (x0 in, Y0 out)", fs=7.2)
    label(ax, X(36), 0.6, "an invalid block (in_valid = 0) leaves as out_valid = 0", fs=7.2)
    label(ax, X(T / 2), 8.55, "one sample in and one coefficient out per clock; blocks follow each "
          "other without a gap", fs=8, color=INK)
    save(fig, path_out)
