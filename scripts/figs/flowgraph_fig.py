"""Complete radix-2 signal-flow graph of the 8-point DCT (in-place layout)."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.patches import FancyBboxPatch

from dct8 import flowgraph as fg

from .style import (BF_EDGE, BF_FILL, INK, INK2, MEM_EDGE, MEM_FILL, MR_EDGE, MR_FILL, canvas,
                    dot, label, save)

# operation -> x position of its symbol; rows are assigned in place
X_POS = {"S0": 2.3, "S1": 2.3, "S2": 2.3, "S3": 2.3,
         "T0": 3.8, "T1": 3.8, "T2": 4.7, "T3": 4.7,
         "U0": 6.2, "U3": 7.1, "U1": 8.0, "U2": 8.9,
         "V0": 10.5, "V1": 11.35,
         "W1": 12.8, "W2": 12.8, "W3": 13.65}
HW = 0.34                      # half width of a butterfly symbol
ANGLE = {1: r"$\pi/16$", 2: r"$\pi/8$", 3: r"$3\pi/16$"}


def _rows():
    row = {f"x{n}": n for n in range(8)}
    for op in fg.OPS:                        # in place: outputs take the rows of the inputs
        row[op.outs[0]], row[op.outs[1]] = row[op.ins[0]], row[op.ins[1]]
    return row


def draw(path) -> None:
    row = _rows()
    fig, ax = canvas(17.6, 10.6, scale=0.62)
    y = lambda r: 8.2 - r * 1.0                                          # noqa: E731
    x_end = 14.4

    # unit bands and stage headers
    bands = [(1.85, 5.25, BF_FILL, "butterfly unit (BF0, BF1)", "stages 1-3"),
             (5.6, 9.45, BF_FILL, None, None),
             (9.95, 14.1, MR_FILL, "central CORDIC unit", "rotations"),
             (14.3, 16.05, MEM_FILL, "output buffer", "rearrange")]
    for x0, x1, fc, t1, t2 in bands:
        ax.add_patch(FancyBboxPatch((x0, 0.55), x1 - x0, 8.55, boxstyle="round,pad=0,rounding_size=0.15",
                                    facecolor=fc, edgecolor="none", alpha=0.55, zorder=0))
    heads = [(2.3, "stage 1", r"$x_L,\ x_H$  (SS1)"), (4.25, "stage 2", "4-point inputs  (SS2)"),
             (7.55, "stage 3", "2-point DCTs  (SS3)"), (10.92, "rotations", r"$-\pi/8$"),
             (13.22, "rotations", r"$-k\pi/16$"), (15.17, "rearrange", "in-order output")]
    for xh, t1, t2 in heads:
        label(ax, xh, 9.75, t1, fs=9, color=INK, bold=True)
        label(ax, xh, 9.38, t2, fs=7.5)
    label(ax, 3.55, 0.25, "butterfly unit: 12 butterflies / block", fs=7.5, color=BF_EDGE)
    label(ax, 12.0, 0.25, "central CORDIC unit: 5 rotations / block", fs=7.5, color=MR_EDGE)
    label(ax, 15.17, 0.25, "output buffer", fs=7.5, color=MEM_EDGE)

    # wires: every value runs from its producer to its consumer on its row
    start = {f"x{n}": 1.2 for n in range(8)}
    for op in fg.OPS:
        for v in op.outs:
            start[v] = X_POS[op.name] + HW
    end = {}
    for op in fg.OPS:
        for v in op.ins:
            end[v] = X_POS[op.name] - HW
    for v in fg.OUTPUTS:
        end[v] = x_end
    for v, x0 in start.items():
        ax.plot([x0, end[v]], [y(row[v]), y(row[v])], color=INK, lw=0.9, zorder=2,
                solid_capstyle="butt")
        if not v.startswith("x") and end[v] - x0 > 0.55:
            nm = v.replace("p", "'")
            label(ax, x0 + 0.08, y(row[v]) + 0.17, nm, fs=6.3, ha="left")

    # inputs
    for n in range(8):
        label(ax, 1.05, y(n), f"x[{n}]", fs=8.5, color=INK, ha="right")
        dot(ax, 1.2, y(n), r=0.05)

    # butterflies (classic crossing) and rotators
    for op in fg.OPS:
        xc = X_POS[op.name]
        ra, rb = row[op.ins[0]], row[op.ins[1]]
        ya, yb = y(ra), y(rb)
        if op.unit == "BF":
            xl, xr = xc - HW, xc + HW
            for (p0, p1) in (((xl, ya), (xr, ya)), ((xl, yb), (xr, yb)),
                             ((xl, ya), (xr, yb)), ((xl, yb), (xr, ya))):
                ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=BF_EDGE, lw=1.25, zorder=3)
            dot(ax, xr, ya, color=BF_EDGE, r=0.055)
            dot(ax, xr, yb, color=BF_EDGE, r=0.055)
            label(ax, xr - 0.16, yb - 0.2, "−", fs=8, color=BF_EDGE, bold=True)
            label(ax, xc, ya + 0.27, op.name, fs=6.8, color=BF_EDGE, bold=True)
        else:
            w = 0.5
            for yy in (ya, yb):
                ax.add_patch(FancyBboxPatch((xc - w / 2, yy - 0.15), w, 0.3,
                                            boxstyle="round,pad=0,rounding_size=0.12",
                                            facecolor=MR_FILL, edgecolor=MR_EDGE, lw=1.2, zorder=4))
            ax.plot([xc, xc], [ya - 0.15, yb + 0.15], color=MR_EDGE, lw=1.6, zorder=3)
            mid = (ra + rb) / 2
            if abs(mid - round(mid)) < 1e-9:
                mid -= 0.5
            ax.add_patch(FancyBboxPatch((xc - 0.36, y(mid) - 0.17), 0.72, 0.34,
                                        boxstyle="round,pad=0,rounding_size=0.1",
                                        facecolor="white", edgecolor=MR_EDGE, lw=1.0, zorder=5))
            label(ax, xc, y(mid), ANGLE[op.param], fs=7.2, color=INK, z=6)
            label(ax, xc, y(min(ra, rb)) + 0.3, op.name, fs=6.8, color=MR_EDGE, bold=True)
            label(ax, xc - 0.17, ya, "u", fs=6, color=MR_EDGE)
            label(ax, xc - 0.17, yb, "v", fs=6, color=MR_EDGE)

    # rearrange unit: row -> natural order
    for k in range(8):
        r = row[f"Y{k}"]
        t = np.linspace(0, 1, 60)
        s = 3 * t ** 2 - 2 * t ** 3
        ax.plot(x_end + (15.9 - x_end) * t, y(r) + (y(k) - y(r)) * s, color=MEM_EDGE, lw=1.1, zorder=2)
        dot(ax, 15.9, y(k), color=INK, r=0.05)
        label(ax, 16.05, y(k), f"$Y_{k}$", fs=9, color=INK, ha="left")
    label(ax, 16.9, 4.7, r"$Y_k = 2\sqrt{2}\,X_k$", fs=8, color=INK2, rotation=90)

    # notation
    ax.set_ylim(-0.75, 10.6)
    fig.set_size_inches(17.6 * 0.62, 11.35 * 0.62)
    xs = 1.5
    ax.plot([xs, xs + 0.45], [-0.42, -0.42], color=BF_EDGE, lw=1.25)
    label(ax, xs + 0.55, -0.42, r"butterfly $(a, b) \mapsto (a + b,\ a - b)$, safe scaling "
          r"$\times\frac{1}{2}$ (SS)", fs=7.5, color=INK, ha="left")
    xr = 8.6
    ax.add_patch(FancyBboxPatch((xr, -0.55), 0.42, 0.26, boxstyle="round,pad=0,rounding_size=0.1",
                                facecolor=MR_FILL, edgecolor=MR_EDGE, lw=1.1))
    label(ax, xr + 0.55, -0.42, r"rotator $(u, v) \mapsto (u\cos\theta - v\sin\theta,\ "
          r"u\sin\theta + v\cos\theta)$; swapped operands realise $-\theta$", fs=7.5, color=INK,
          ha="left")
    save(fig, path)
