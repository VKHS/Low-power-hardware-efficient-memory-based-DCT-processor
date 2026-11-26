"""Processor block diagram: two processing elements around a partitioned memory bank."""
from __future__ import annotations

from matplotlib.patches import Rectangle

from .style import (BF_EDGE, BF_FILL, CTL_EDGE, CTL_FILL, INK, INK2, IO_EDGE, IO_FILL, MEM_EDGE,
                    MEM_FILL, MR_EDGE, MR_FILL, arrow, box, canvas, dot, label, path, save)

DASH = (0, (3, 2))


def draw(path_out) -> None:
    fig, ax = canvas(21.5, 11.6, scale=0.58)

    # ------------------------------------------------------------ distributed controller
    label(ax, 1.3, 11.2, "distributed controller", fs=9.5, color=INK, ha="left", bold=True)
    label(ax, 5.0, 11.2, "a 3-bit phase counter and four small decoders, generated from the "
          "modulo schedule (rtl/dct8_ctrl.v)", fs=7.4, ha="left")
    box(ax, 1.3, 9.25, 19.0, 1.6, "", fill=CTL_FILL, edge=CTL_EDGE, radius=0.12)
    box(ax, 1.6, 9.5, 2.3, 1.1, "phase counter\n3 bit", fill="white", edge=CTL_EDGE, fs=7.4)
    decs = [("BF0\ndecoder", 5.2), ("BF1\ndecoder", 7.25), ("CORDIC\ndecoder", 14.1),
            ("I/O\ndecoder", 17.95)]
    ax.plot([3.9, 18.8], [9.4, 9.4], color=CTL_EDGE, lw=0.9, zorder=2)
    for t, xd in decs:
        box(ax, xd, 9.55, 1.65, 1.05, t, fill="white", edge=CTL_EDGE, fs=7.2)
        ax.plot([xd + 0.82, xd + 0.82], [9.4, 9.55], color=CTL_EDGE, lw=0.9)
    label(ax, 4.6, 9.4, "phase", fs=6.5, va="bottom")
    for xd, ytop in ((6.02, 8.4), (8.07, 8.4), (14.92, 8.4), (18.77, 6.65)):
        path(ax, [(xd, 9.55), (xd, ytop)], color=CTL_EDGE, lw=0.9, ls=DASH, ms=6)
    path(ax, [(2.75, 9.5), (2.75, 7.65)], color=CTL_EDGE, lw=0.9, ls=DASH, ms=6)
    label(ax, 2.9, 8.55, "write on\neven phases", fs=6.3, ha="left")

    # ------------------------------------------------------------ input side
    label(ax, 0.15, 6.45, "x[n]", fs=10, color=INK, ha="left", bold=True)
    label(ax, 0.15, 5.6, "$B_{IN}$ bits\n1 sample\nper clock", fs=6.6, ha="left")
    box(ax, 1.05, 5.75, 1.0, 0.6, r"$\times 2^{F}$", fill=IO_FILL, edge=IO_EDGE, fs=8.5)
    arrow(ax, (0.75, 6.05), (1.05, 6.05), ms=7)
    box(ax, 2.15, 6.85, 1.2, 0.8, "IB\n1 word", fill=MEM_FILL, edge=MEM_EDGE, fs=7.6)
    path(ax, [(2.05, 6.05), (2.45, 6.05), (2.45, 6.85)], ms=7)
    dot(ax, 2.45, 6.05, r=0.05)
    path(ax, [(2.45, 6.05), (5.0, 6.05)], ms=7)
    label(ax, 3.55, 5.85, "x[2n+1]", fs=6.3)
    path(ax, [(3.35, 7.25), (5.0, 7.25)], ms=7)
    label(ax, 4.05, 7.45, "x[2n]", fs=6.3)
    label(ax, 2.05, 7.25, "input\nbuffer", fs=6.3, ha="right")

    # ------------------------------------------------------------ butterfly unit
    box(ax, 4.55, 3.75, 4.45, 4.65, "", fill=BF_FILL, edge=BF_EDGE, radius=0.15, lw=1.3)
    label(ax, 6.77, 8.1, "butterfly unit", fs=9.5, color=INK, bold=True)
    for (yb, nm, src) in ((5.95, "BF0", "a: IB | M_B    b: x[n] | M_B"), (4.1, "BF1", "a, b: M_B")):
        box(ax, 5.0, yb, 3.6, 1.65, "", fill="white", edge=BF_EDGE, radius=0.1)
        label(ax, 5.15, yb + 1.38, nm, fs=8.5, color=INK, ha="left", bold=True)
        label(ax, 5.15, yb + 1.0, src, fs=6.3, ha="left")
        box(ax, 5.15, yb + 0.15, 1.5, 0.62, "a + b\na − b", fill=BF_FILL, edge=BF_EDGE, fs=7)
        box(ax, 6.95, yb + 0.15, 1.45, 0.62, "SS  ×½\n(optional)", fill=BF_FILL, edge=BF_EDGE, fs=6.6)
        arrow(ax, (6.65, yb + 0.46), (6.95, yb + 0.46), ms=6)
    label(ax, 6.77, 3.45, "12 butterflies in 16 slots: 75 % busy", fs=6.8)

    # M_B and the butterfly loop
    box(ax, 5.0, 1.35, 3.6, 1.2, "M_B  butterfly buffers\n8 words · 4 read / 4 write",
        fill=MEM_FILL, edge=MEM_EDGE, fs=7.5)
    path(ax, [(8.6, 6.4), (9.45, 6.4)], arrow_end=False)
    path(ax, [(8.6, 4.55), (9.45, 4.55)], arrow_end=False)
    path(ax, [(9.45, 6.4), (9.45, 1.95), (8.6, 1.95)], ms=7)
    for yy in (6.4, 4.55, 5.45, 2.85):
        dot(ax, 9.45, yy, r=0.05)
    path(ax, [(5.0, 1.95), (4.15, 1.95), (4.15, 4.95), (5.0, 4.95)], ms=7)
    path(ax, [(4.15, 4.95), (4.15, 6.65), (5.0, 6.65)], ms=7)
    dot(ax, 4.15, 4.95, r=0.05)
    label(ax, 3.9, 3.2, "operands", fs=6.5, rotation=90)
    label(ax, 9.7, 3.6, "results", fs=6.5, rotation=90)

    # ------------------------------------------------------------ memory bank
    box(ax, 10.25, 4.85, 2.0, 1.75, "memory bank\nMM · 5 words\n2 read / 3 write", fill=MEM_FILL,
        edge=MEM_EDGE, fs=7.4)
    path(ax, [(9.45, 5.45), (10.25, 5.45)], ms=7)
    label(ax, 9.85, 5.68, "stage 3", fs=6.2)

    # ------------------------------------------------------------ central CORDIC unit
    box(ax, 12.95, 3.75, 3.95, 4.65, "", fill=MR_FILL, edge=MR_EDGE, radius=0.15, lw=1.3)
    label(ax, 14.92, 8.1, "central CORDIC unit", fs=9.5, color=INK, bold=True)
    box(ax, 13.15, 6.35, 3.55, 1.4, "", fill="white", edge=MR_EDGE)
    label(ax, 14.92, 7.45, "stage A", fs=7.6, color=INK, bold=True)
    label(ax, 14.92, 6.95, r"Table 1: $\times 2^{G}$, rotation by $P_k$", fs=6.4, color=INK)
    label(ax, 14.92, 6.6, r"CORDIC-II: friend angle, USR $2^{-3}$", fs=6.4, color=INK)
    ax.add_patch(Rectangle((13.15, 5.98), 3.55, 0.18, facecolor=MR_EDGE, edgecolor="none", zorder=3))
    label(ax, 14.92, 5.82, "pipeline register", fs=6.2, va="top")
    box(ax, 13.15, 4.0, 3.55, 1.4, "", fill="white", edge=MR_EDGE)
    label(ax, 14.92, 5.1, "stage B", fs=7.6, color=INK, bold=True)
    label(ax, 14.92, 4.6, r"Table 1: radius scale-down $K_k$", fs=6.4, color=INK)
    label(ax, 14.92, 4.25, r"CORDIC-II: USR $2^{-5}$, nano, one $K$", fs=6.4, color=INK)
    arrow(ax, (14.92, 6.35), (14.92, 6.16), ms=6)
    label(ax, 14.92, 3.45, "5 rotations in 8 slots: 62.5 % busy", fs=6.8)
    path(ax, [(12.25, 6.1), (12.6, 6.1), (12.6, 7.05), (13.15, 7.05)], ms=7)
    label(ax, 12.5, 7.05, "u, v, k", fs=6.3, ha="right")

    # rotation results: to the output buffer, or back to MM as stage-4 operands
    path(ax, [(16.7, 4.7), (17.2, 4.7)], arrow_end=False)
    dot(ax, 17.2, 4.7, r=0.05)
    path(ax, [(17.2, 4.7), (17.2, 5.35), (17.5, 5.35)], ms=7)
    path(ax, [(17.2, 4.7), (17.2, 3.2), (11.25, 3.2), (11.25, 4.85)], ms=7)
    label(ax, 13.95, 2.97, "stage-3 rotations feed stage 4", fs=6.4)

    # ------------------------------------------------------------ output buffer and output
    box(ax, 17.45, 4.85, 2.0, 1.75, "output buffer\nOB · 5 words\nrearrange unit",
        fill=MEM_FILL, edge=MEM_EDGE, fs=7.2)
    path(ax, [(9.45, 2.85), (18.4, 2.85)], arrow_end=False)
    path(ax, [(18.4, 2.85), (18.4, 4.85)], ms=7)
    label(ax, 12.9, 2.62, "$Y_0$, $Y_4$ (no rotation)", fs=6.4)
    box(ax, 19.65, 5.4, 0.75, 0.6, "reg", fill=IO_FILL, edge=IO_EDGE, fs=7)
    arrow(ax, (19.35, 5.7), (19.65, 5.7), ms=7)
    arrow(ax, (20.4, 5.7), (20.85, 5.7), ms=7)
    label(ax, 21.4, 6.2, "$Y_k$", fs=10.5, color=INK, ha="right", bold=True)
    label(ax, 21.4, 5.0, "in order\nW bits\n+ valid,\nindex, last", fs=6.4, ha="right", va="top")

    # ------------------------------------------------------------ key figures
    facts = ("one sample in and one coefficient out per clock  ·  latency 16 clocks  ·  "
             "12 butterflies + 5 rotations per block  ·  19 memory words  ·  no multiplier")
    label(ax, 10.75, 0.55, facts, fs=7.6, color=INK)
    save(fig, path_out)
