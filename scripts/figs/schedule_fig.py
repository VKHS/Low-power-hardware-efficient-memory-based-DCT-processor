"""Modulo schedule (three overlapped blocks) and register occupancy of the memory banks."""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from dct8 import flowgraph as fg
from dct8 import schedule

from .style import AXIS, CTL_EDGE, GRID, INK, INK2, NEUTRAL, S1, S2, S3, panel_label, save

BLOCK_COLORS = (S1, S2, S3)
BLOCK_NAMES = ("block A", "block B", "block C")


def _cell(ax, x, y, w, h, color, text, fs=6.6, tc="white"):
    ax.add_patch(FancyBboxPatch((x + 0.06, y - h / 2), w - 0.12, h,
                                boxstyle="round,pad=0,rounding_size=0.12", facecolor=color,
                                edgecolor="none", zorder=3))
    if text:
        ax.text(x + w / 2, y, text, ha="center", va="center", fontsize=fs, color=tc, zorder=4)


def draw(path_out) -> None:
    sch = schedule.build()
    fig = plt.figure(figsize=(12.0, 8.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.35], hspace=0.32)

    # ---------------------------------------------------------- (a) Gantt chart
    ax = fig.add_subplot(gs[0])
    rows = ["input x[n]", "BF0", "BF1", "CORDIC stage A", "CORDIC stage B", "output $Y_k$"]
    ypos = {r: len(rows) - 1 - i for i, r in enumerate(rows)}
    T = 41
    for b in range(3):
        c = BLOCK_COLORS[b]
        t0 = 8 * b
        for n in range(8):
            _cell(ax, t0 + n, ypos["input x[n]"], 1, 0.62, c, f"x{n}")
        for op in fg.OPS:
            t = t0 + sch.times[op.name]
            if op.unit == "BF":
                _cell(ax, t, ypos[f"BF{sch.units[op.name]}"], 1, 0.62, c, op.name)
            else:
                _cell(ax, t, ypos["CORDIC stage A"], 1, 0.62, c, op.name)
                _cell(ax, t + 1, ypos["CORDIC stage B"], 1, 0.62, c, op.name)
        for k in range(8):
            _cell(ax, t0 + sch.t0 + 1 + k, ypos["output $Y_k$"], 1, 0.62, c, f"Y{k}")
    ax.set_xlim(-0.3, T)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks([ypos[r] for r in rows])
    ax.set_yticklabels(rows, fontsize=8, color=INK)
    ax.set_xticks(range(0, T, 4))
    ax.set_xticks(range(0, T), minor=True)
    ax.grid(axis="x", which="minor", color=GRID, lw=0.6)
    ax.grid(axis="x", which="major", color=GRID, lw=0.9)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("clock cycle (x0 of block A enters in cycle 0)")
    ax.annotate("", xy=(16, -0.48), xytext=(0, -0.48),
                arrowprops=dict(arrowstyle="<|-|>", color=INK2, lw=0.9, mutation_scale=7))
    ax.text(8, -0.38, "latency 16 cycles", fontsize=7.5, color=INK2, ha="center", va="bottom")
    ax.set_title("Modulo schedule: a new block every 8 cycles, two butterfly datapaths and one "
                 "CORDIC unit time-shared by all blocks", loc="left")
    for b in range(3):
        ax.plot([], [], color=BLOCK_COLORS[b], lw=6, label=BLOCK_NAMES[b])
    ax.legend(loc="upper right", ncol=3, bbox_to_anchor=(1.0, 1.0), handlelength=1.2,
              borderaxespad=0.2)
    panel_label(ax, "a")

    # ---------------------------------------------------------- (b) register occupancy
    ax = fig.add_subplot(gs[1])
    regs = [("IB", 0)] + [("BM", i) for i in range(8)] + [("MM", i) for i in range(5)] + \
        [("OB", i) for i in range(5)]
    yrow = {r: len(regs) - 1 - i for i, r in enumerate(regs)}
    unit_color = {"BF": S1, "MR": S2, "IN": NEUTRAL}
    busy = {b: 0 for b in schedule.BANKS}
    for name, v in sch.values.items():
        prod = "IN" if name.startswith("x") else fg.OP_BY_NAME[fg.PRODUCER[name]].unit
        busy[v.bank] += v.length
        start, n = v.avail % schedule.PERIOD, v.length
        pieces = [(start, min(n, schedule.PERIOD - start))]
        if start + n > schedule.PERIOD:
            pieces.append((0, start + n - schedule.PERIOD))
        main = max(range(len(pieces)), key=lambda i: pieces[i][1])
        for i, (x0, w) in enumerate(pieces):
            _cell(ax, x0, yrow[(v.bank, v.reg)], w, 0.66, unit_color[prod],
                  name.replace("p", "'") if i == main else "", fs=6.4, tc="white")
    ax.set_xlim(-0.1, 8.1)
    ax.set_ylim(-0.6, len(regs) - 0.4)
    ax.set_yticks([yrow[r] for r in regs])
    ax.set_yticklabels([f"{b}[{i}]" for b, i in regs], fontsize=7.5, color=INK)
    ax.set_xticks([p + 0.5 for p in range(8)])
    ax.set_xticklabels([str(p) for p in range(8)])
    ax.set_xticks(range(9), minor=True)
    ax.grid(axis="x", which="minor", color=GRID, lw=0.8)
    ax.grid(axis="x", which="major", visible=False)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="both", which="both", length=0)
    ax.set_xlabel("phase (cycle mod 8): each value lives at most 8 cycles, so its register "
                  "address depends on the phase only")
    tot = {"IB": 1, "BM": 8, "MM": 5, "OB": 5}
    for b, n in tot.items():
        ys = [yrow[(b, i)] for i in range(n)]
        ax.text(8.25, (max(ys) + min(ys)) / 2, f"{b}: {n} word{'s' if n > 1 else ''}\n"
                f"{100 * busy[b] / (8 * n):.0f} % occupied", fontsize=7.3, color=INK2,
                va="center", ha="left")
        if b != "OB":
            ax.axhline(min(ys) - 0.5, color=AXIS, lw=0.8)
    for lab, col in (("written by the butterfly unit", S1), ("written by the CORDIC unit", S2),
                     ("input sample", NEUTRAL)):
        ax.plot([], [], color=col, lw=6, label=lab)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, handlelength=1.2,
              borderaxespad=0.2)
    ax.set_title("Register occupancy in steady state: 19 words in four banks", loc="left", pad=22)
    panel_label(ax, "b", y=1.075)
    save(fig, path_out)
