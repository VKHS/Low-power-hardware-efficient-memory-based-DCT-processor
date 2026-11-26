"""Data figures: accuracy versus word length, micro-rotation design space, images, dynamic range."""
from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np

from dct8 import analysis as A
from dct8 import cordic2, flowgraph, processor, reference, scalable
from dct8.fixedpoint import rne, rno
from dct8.processor import Config

from .style import (GRID, INK, INK2, MODE_COLOR, MODE_LABEL, NEUTRAL, S1, S2, S3, SURFACE,
                    marker_kw, panel_label, save)

# the paper's Table 3: average PSNR (dB) of the proposed processor, BSD-100 images
PAPER_TABLE3 = {16: 56.51, 14: 43.24, 12: 32.60, 10: 17.01, 8: 6.02}
WS = list(range(8, 17))


def _end_label(ax, x, y, text, dy=0.0):
    ax.text(x + 0.18, y + dy, text, fontsize=7.5, color=INK, va="center", ha="left")


def accuracy(path_out, images) -> dict:
    x = A.random_inputs(20000)
    rows1 = A.wl_sweep_1d(WS, x)
    rows2 = A.wl_sweep_2d(WS, images)
    fig, axs = plt.subplots(2, 2, figsize=(11.6, 8.4))
    fig.subplots_adjust(hspace=0.42, wspace=0.3)

    # (a) 1-D SQNR
    ax = axs[0, 0]
    ideal = [r["sqnr_ideal_rot"] for r in rows1 if r["mode"] == "table1"]
    ax.plot(WS, ideal, color=NEUTRAL, lw=1.6, **marker_kw(NEUTRAL, 6))
    _end_label(ax, WS[-1], ideal[-1], "exact rotations\n(same datapath)")
    for mode in cordic2.MODES:
        v = [r["sqnr"] for r in rows1 if r["mode"] == mode]
        ax.plot(WS, v, color=MODE_COLOR[mode], label=MODE_LABEL[mode], **marker_kw(MODE_COLOR[mode]))
        _end_label(ax, WS[-1], v[-1], f"{v[-1]:.1f} dB", dy=-1.5 if mode == "table1" else 1.5)
    ax.set_xlabel("internal word length W (bits)")
    ax.set_ylabel("SQNR (dB)")
    ax.set_title("1-D processor: SQNR, 8-bit random inputs", loc="left")
    ax.set_xticks(WS)
    ax.set_xlim(7.6, 18.6)
    ax.legend(loc="upper left")
    panel_label(ax, "a")

    # (b) 2-D PSNR against the double-precision DCT
    ax = axs[0, 1]
    for mode in cordic2.MODES:
        rr = [r for r in rows2 if r["mode"] == mode]
        m = np.array([r["mean"] for r in rr])
        lo = np.array([min(r["per_image"].values()) for r in rr])
        hi = np.array([max(r["per_image"].values()) for r in rr])
        ax.fill_between(WS, lo, hi, color=MODE_COLOR[mode], alpha=0.10, lw=0)
        ax.plot(WS, m, color=MODE_COLOR[mode], label=MODE_LABEL[mode], **marker_kw(MODE_COLOR[mode]))
        _end_label(ax, WS[-1], m[-1], f"{m[-1]:.1f} dB")
    pw = sorted(PAPER_TABLE3)
    ax.plot(pw, [PAPER_TABLE3[w] for w in pw], color=NEUTRAL, lw=1.4,
            marker="o", markersize=6, markerfacecolor=SURFACE, markeredgecolor=NEUTRAL,
            markeredgewidth=1.6, label="paper, Table 3 (BSD-100, as reported)")
    ax.set_xlabel("word length W of both passes (bits)")
    ax.set_ylabel("PSNR vs. IEEE-754 double DCT (dB)")
    ax.set_title(f"2-D processor: {len(images)} test images (band: min-max)", loc="left")
    ax.set_xticks(WS)
    ax.set_xlim(7.6, 18.0)
    ax.set_ylim(0, 92)
    ax.legend(loc="lower right")
    panel_label(ax, "b")

    # (c) error per coefficient at W = 14
    ax = axs[1, 0]
    k = np.arange(8)
    wbar = 0.36
    stats = {}
    for i, mode in enumerate(cordic2.MODES):
        st = A.error_stats_1d(Config(8, 14, 3, (0, 0, 0), mode), x)
        rms = np.sqrt(np.mean(st["err"] ** 2, axis=0))
        stats[mode] = st
        ax.bar(k + (i - 0.5) * (wbar + 0.04), rms, width=wbar, color=MODE_COLOR[mode],
               label=MODE_LABEL[mode], zorder=3)
    ax.set_xticks(k)
    ax.set_xticklabels([f"$X_{i}$" for i in k])
    ax.set_ylabel("rms error (DCT units)")
    ax.set_title("Error per coefficient, W = 14 (rotated: $X_1, X_2, X_3, X_5, X_6, X_7$)",
                 loc="left")
    for kk in (0, 4):
        ax.text(kk, 0.012, "exact", ha="center", va="bottom", fontsize=7.5, color=INK2)
    ax.set_ylim(0, 0.74)
    ax.legend(loc="upper left", ncol=2)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "c")

    # (d) micro-rotation angle errors
    ax = axs[1, 1]
    for mode, yy in (("table1", 2), ("cordic2x", 1)):
        rep = cordic2.analyze(mode)
        ax.scatter([abs(r.angle_err_rad) for r in rep], [yy] * len(rep), s=60,
                   color=MODE_COLOR[mode], edgecolor=SURFACE, linewidth=1.4, zorder=3)
        prev = None
        for r in sorted(rep, key=lambda r: abs(r.angle_err_rad)):
            e = abs(r.angle_err_rad)
            below = prev is not None and e / prev < 1.35
            ax.annotate(f"k={r.k}", (e, yy), xytext=(0, -13 if below else 7),
                        textcoords="offset points", ha="center", fontsize=7, color=INK2)
            prev = None if below else e
    t5 = scalable.table5_report()
    ax.scatter([abs(r["angle_err_rad"]) for r in t5], [0] * len(t5), s=60, color=S3,
               edgecolor=SURFACE, linewidth=1.4, zorder=3)
    prev = None
    for r in sorted(t5, key=lambda r: abs(r["angle_err_rad"])):
        e = abs(r["angle_err_rad"])
        below = prev is not None and e / prev < 1.15
        ax.annotate(f"{r['k']}", (e, 0), xytext=(0, -13 if below else 7),
                    textcoords="offset points", ha="center", fontsize=7, color=INK2)
        prev = None if below else e
    ax.set_xscale("log")
    ax.set_yticks([2, 1, 0])
    ax.set_yticklabels(["Table 1 (8-point)", "CORDIC-II extension", "Table 5 (16-point\nCORDIC array)"],
                       color=INK)
    ax.set_ylim(-0.6, 2.6)
    ax.set_xlim(1e-4, 2e-2)
    ax.set_xlabel(r"|angle error| (rad), target $k\pi/16$ (8-point) or $k\pi/32$ (16-point)")
    ax.set_title("Micro-rotation angle errors", loc="left")
    ax.grid(axis="y", visible=False)
    panel_label(ax, "d")
    save(fig, path_out)
    return {"rows1": rows1, "rows2": rows2}


def design_space(path_out) -> None:
    designs = cordic2.explore()
    fig, axs = plt.subplots(1, 2, figsize=(11.6, 4.6), gridspec_kw={"width_ratios": [1.25, 1]})
    fig.subplots_adjust(wspace=0.28)
    ax = axs[0]
    fam = {"conventional CORDIC": NEUTRAL, "USR CORDIC": S3, "CORDIC-II (friend angles)": S2}
    for f, c in fam.items():
        d = [x for x in designs if x.family == f]
        ax.scatter([x.adders for x in d], [x.max_err for x in d], s=22, color=c, alpha=0.85,
                   edgecolor=SURFACE, linewidth=0.6, label=f, zorder=3)
    front = cordic2.pareto([d for d in designs if d.family != "paper Table 1"])
    ax.plot([d.adders for d in front], [d.max_err for d in front], color=INK2, lw=1.0, zorder=2,
            drawstyle="steps-post", label="Pareto front")
    t1 = [d for d in designs if d.family == "paper Table 1"][0]
    ax.scatter([t1.adders], [t1.max_err], s=90, color=S1, edgecolor=SURFACE, linewidth=1.5, zorder=4,
               label="Table 1 (paper)")
    ch = [d for d in designs if d.chosen][0]
    ax.scatter([ch.adders], [ch.max_err], s=110, marker="D", color=S2, edgecolor=INK, linewidth=1.0,
               zorder=5, label="chosen CORDIC-II configuration")
    ax.annotate("Table 1", (t1.adders, t1.max_err), xytext=(8, 4), textcoords="offset points",
                fontsize=7.5, color=INK)
    ax.annotate("FA + USR 2$^{-3}$, 2$^{-5}$ + nano", (ch.adders, ch.max_err), xytext=(8, -12),
                textcoords="offset points", fontsize=7.5, color=INK)
    ax.set_yscale("log")
    ax.set_xlabel("two-input adders of the rotation unit (both components)")
    ax.set_ylabel("worst-case error |P - e$^{j\\theta}$| (angle + gain)")
    ax.set_title(r"Design space for $\{\pi/16,\ \pi/8,\ 3\pi/16\}$", loc="left")
    ax.legend(loc="upper right", fontsize=7)
    panel_label(ax, "a")

    ax = axs[1]
    th = np.linspace(0, math.radians(40), 200)
    ax.plot(np.cos(th), np.sin(th), color=GRID, lw=1.2)
    for k in cordic2.ANGLE_CODES:
        t = k * math.pi / 16
        ax.plot([0, 1.08 * math.cos(t)], [0, 1.08 * math.sin(t)], color=AXIS_C, lw=0.8, zorder=1)
        ax.text(1.1 * math.cos(t), 1.1 * math.sin(t), f"{k}π/16", fontsize=7.5, color=INK2,
                ha="left", va="center")
        tr = cordic2.trajectory(k, "cordic2x")
        ax.plot([p.real for p in tr], [p.imag for p in tr], color=S2, lw=1.4, zorder=3)
        ax.scatter([p.real for p in tr[1:]], [p.imag for p in tr[1:]], s=16, color=S2,
                   edgecolor=SURFACE, linewidth=0.8, zorder=4)
        p1 = cordic2.coefficient(k, "table1")
        ax.scatter([p1.real], [p1.imag], s=36, color=S1, edgecolor=SURFACE, linewidth=1.2, zorder=5)
    ax.scatter([], [], s=16, color=S2, label="CORDIC-II stage by stage")
    ax.scatter([], [], s=36, color=S1, label="Table 1 coefficient $K_k P_k$")
    ax.set_aspect("equal")
    ax.set_xlim(0.55, 1.32)
    ax.set_ylim(-0.03, 0.72)
    ax.set_xlabel("real")
    ax.set_ylabel("imaginary")
    ax.set_title("Micro-rotation trajectories", loc="left")
    ax.legend(loc="upper left", fontsize=7)
    panel_label(ax, "b")
    save(fig, path_out)


AXIS_C = "#c2c2c2"


def images_fig(path_out, images) -> list:
    names = ["chelsea", "gravel"]
    keeps = [10, 6, 3, 1]
    row, col = Config(8, 14, 3, (0, 0, 0), "table1"), Config(14, 16, 3, (1, 1, 1), "table1")
    fig, axs = plt.subplots(len(names), 5, figsize=(12.4, 5.4))
    fig.subplots_adjust(wspace=0.04, hspace=0.16)
    table = []
    for i, n in enumerate(names):
        img = images[n][:256, :256]
        axs[i, 0].imshow(img, cmap="gray", vmin=0, vmax=255)
        axs[i, 0].set_title(f"{n} (original)", fontsize=8.5, loc="left")
        for j, kk in enumerate(keeps):
            rec = A.reconstruct(img, row, col, keep=kk)
            ref = A.reconstruct(img, keep=kk)
            p, pf = A.psnr(img, rec), A.psnr(img, ref)
            table.append((n, kk, p, pf))
            axs[i, j + 1].imshow(rec, cmap="gray", vmin=0, vmax=255)
            axs[i, j + 1].set_title(f"64:{kk}   {p:.2f} dB", fontsize=8.5, loc="left")
        for a in axs[i]:
            a.set_xticks([])
            a.set_yticks([])
            a.grid(False)
            for s in a.spines.values():
                s.set_visible(False)
    fig.savefig(path_out, dpi=130, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return table


def dynamic_range(path_out) -> None:
    fig, axs = plt.subplots(1, 2, figsize=(11.6, 4.4), gridspec_kw={"width_ratios": [1.05, 1]})
    fig.subplots_adjust(wspace=0.32)
    ax = axs[0]
    gains = A.linear_gains()
    lv = {}
    for name, g in gains.items():
        lev = 0 if name.startswith("x") else max(op.level for op in flowgraph.OPS if name in op.outs)
        unit = "IN" if name.startswith("x") else next(op.unit for op in flowgraph.OPS if name in op.outs)
        lv.setdefault((lev, unit), []).append((name, float(np.sum(np.abs(g)))))
    xs = {(0, "IN"): 0, (1, "BF"): 1, (2, "BF"): 2, (3, "BF"): 3, (3, "MR"): 4, (4, "MR"): 5}
    labels = ["input", "stage 1", "stage 2", "stage 3", "rotations\n$-\\pi/8$", "rotations\n$-k\\pi/16$"]
    for key, items in lv.items():
        xx = xs[key]
        c = S1 if key[1] == "BF" else (S2 if key[1] == "MR" else NEUTRAL)
        uniq = {}
        for _, v in items:
            uniq[round(v, 3)] = uniq.get(round(v, 3), 0) + 1
        offs = np.linspace(-0.16, 0.16, len(uniq)) if len(uniq) > 1 else [0.0]
        for (v, n), dx in zip(sorted(uniq.items()), offs):
            ax.scatter([xx + dx], [v], s=46, color=c, edgecolor=SURFACE, linewidth=1.3, zorder=3)
            ax.text(xx + dx, v * 0.955, f"×{n}", fontsize=6.6, color=INK2, va="top", ha="center")
    for b in (1, 2, 4, 8):
        ax.axhline(b, color=GRID, lw=0.8, zorder=1)
    ax.text(5.45, 8, "  8 = 2$^3$: three headroom bits", fontsize=7.5, color=INK2, va="bottom",
            ha="right")
    ax.annotate("DC: 8 max|x|", (3, 8), xytext=(2.2, 6.6), fontsize=7.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.annotate("rotation nodes:\nat most 7.39 max|x|", (4, 7.2), xytext=(3.55, 5.0), fontsize=7.5,
                color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.set_xticks(range(6))
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_yscale("log", base=2)
    ax.set_yticks([1, 2, 4, 8])
    ax.set_yticklabels(["1", "2", "4", "8"])
    ax.set_ylabel("worst-case |node| / max|x|  (L1 gain)")
    ax.set_title("Growth through the flow graph", loc="left")
    ax.grid(axis="x", visible=False)
    panel_label(ax, "a")

    ax = axs[1]
    ss_list = [(0, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
    wlist = list(range(8, 13))
    for j, ss in enumerate(ss_list):
        for i, w in enumerate(wlist):
            if w - 8 - (3 - sum(ss)) < 0:
                ax.add_patch(plt.Rectangle((i - 0.46, j - 0.42), 0.92, 0.84, facecolor="#f4f4f4",
                                           edgecolor="none"))
                continue
            ok_rno = _overflow_free(Config(8, w, 3, ss), rno)
            ok_rne = _overflow_free(Config(8, w, 3, ss), rne)
            fc = "#e6f5e9" if ok_rno else "#fbe3e3"
            ax.add_patch(plt.Rectangle((i - 0.46, j - 0.42), 0.92, 0.84, facecolor=fc, edgecolor="none"))
            ax.text(i, j + 0.13, "✓" if ok_rno else "✗", ha="center", va="center", fontsize=9,
                    color="#006c10" if ok_rno else "#dc3c3d", fontweight="bold")
            ax.text(i, j - 0.2, "half-even " + ("✓" if ok_rne else "✗ overflow"), ha="center",
                    va="center", fontsize=5.6, color=INK2 if ok_rne else "#b02020")
    ax.set_xticks(range(len(wlist)))
    ax.set_xticklabels([str(w) for w in wlist])
    ax.set_yticks(range(len(ss_list)))
    ax.set_yticklabels(["SS " + "".join(map(str, s)) for s in ss_list], fontsize=7.5, color=INK)
    ax.set_xlim(-0.55, len(wlist) - 0.45)
    ax.set_ylim(-0.55, len(ss_list) - 0.45)
    ax.set_xlabel("word length W (8-bit inputs); grey: H = 3 - ΣSS does not fit")
    ax.set_title("No overflow for any input (✓: von Neumann SS rounding)", loc="left")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    panel_label(ax, "b")
    save(fig, path_out)


def _overflow_free(cfg: Config, rounding) -> bool:
    xs = np.vstack([A.corner_inputs(8), A.random_inputs(800, seed=3)])
    cols = [processor.align_input(xs[:, n], cfg) for n in range(8)]
    vals = flowgraph.evaluate_all(
        cols, bf=lambda p, q, st: (rounding(p + q, cfg.scale(st)), rounding(p - q, cfg.scale(st))),
        mr=lambda p, q, k: cordic2.mr_rotate(p, q, k, cfg.guard, cfg.mr_mode))
    lo, hi = -(1 << (cfg.w - 1)), (1 << (cfg.w - 1)) - 1
    return all(np.min(v) >= lo and np.max(v) <= hi for v in vals.values())
