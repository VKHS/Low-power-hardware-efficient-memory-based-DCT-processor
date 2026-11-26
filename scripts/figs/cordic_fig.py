"""Central CORDIC unit in detail: both micro-rotation modes, two pipeline stages each."""
from __future__ import annotations

from matplotlib.patches import Rectangle

from dct8 import cordic2

from .style import (INK, INK2, MEM_EDGE, MEM_FILL, MR_EDGE, MR_FILL, arrow, box, canvas, label,
                    path, save)


def _k_str(terms) -> str:
    s = ""
    for sh, sg in terms:
        s += ("+" if sg > 0 else "−") + (f"2$^{{-{sh}}}$" if sh else "1")
    return s.lstrip("+")


def _column(ax, x0, title, subtitle, stages_a, reg_w, stages_b, footer):
    w = 7.6
    box(ax, x0, 0.9, w, 10.6, "", fill=MR_FILL, edge=MR_EDGE, radius=0.18, lw=1.3)
    label(ax, x0 + w / 2, 11.1, title, fs=10, color=INK, bold=True)
    label(ax, x0 + w / 2, 10.65, subtitle, fs=7.3)
    # operand inputs
    box(ax, x0 + 0.5, 9.55, 2.9, 0.65, "u  (memory bank)", fill=MEM_FILL, edge=MEM_EDGE, fs=7.2)
    box(ax, x0 + 4.2, 9.55, 2.9, 0.65, "v  (memory bank)", fill=MEM_FILL, edge=MEM_EDGE, fs=7.2)
    y = 9.55
    for i, (t1, t2) in enumerate(stages_a):
        top = y - 0.35
        h = 0.95
        box(ax, x0 + 0.5, top - h, w - 1.0, h, "", fill="white", edge=MR_EDGE)
        label(ax, x0 + 0.7, top - 0.3, t1, fs=7.6, color=INK, ha="left", bold=True)
        label(ax, x0 + 0.7, top - 0.68, t2, fs=6.9, color=INK, ha="left")
        arrow(ax, (x0 + w / 2, y), (x0 + w / 2, top), ms=6)
        y = top - h
    # pipeline register
    ax.add_patch(Rectangle((x0 + 0.5, y - 0.55), w - 1.0, 0.22, facecolor=MR_EDGE,
                           edgecolor="none", zorder=3))
    arrow(ax, (x0 + w / 2, y), (x0 + w / 2, y - 0.33), ms=6)
    label(ax, x0 + w - 0.55, y - 0.78, f"pipeline register: 2 × {reg_w} bits (+ k)", fs=6.9,
          ha="right")
    y -= 0.95
    for t1, t2 in stages_b:
        top = y - 0.3
        h = 0.95
        box(ax, x0 + 0.5, top - h, w - 1.0, h, "", fill="white", edge=MR_EDGE)
        label(ax, x0 + 0.7, top - 0.3, t1, fs=7.6, color=INK, ha="left", bold=True)
        label(ax, x0 + 0.7, top - 0.68, t2, fs=6.9, color=INK, ha="left")
        arrow(ax, (x0 + w / 2, y), (x0 + w / 2, top), ms=6)
        y = top - h
    arrow(ax, (x0 + w / 2, y), (x0 + w / 2, y - 0.4), ms=6)
    label(ax, x0 + w / 2, y - 0.62, "u', v'  (W bits)  →  memory bank or output buffer", fs=7.0,
          color=INK)
    for i, line in enumerate(footer):
        label(ax, x0 + 0.35, 0.55 - 0.32 * i, line, fs=6.9, ha="left", color=INK2)


def draw(path_out) -> None:
    fig, ax = canvas(16.6, 12.0, scale=0.68)
    ax.set_ylim(-0.4, 12.0)
    deg1 = {r.k: r.realised_deg for r in cordic2.analyze("table1")}
    deg2 = {r.k: r.realised_deg for r in cordic2.analyze("cordic2x")}
    t1 = [(f"k = {k}", f"P = {a}+j{b} ({deg1[k]:.3f}°),  K = {_k_str(cordic2.T1_K[k])}")
          for k, (a, b) in cordic2.T1_P.items()]
    _column(ax, 0.3, "Table 1 mode (paper)", "one Gaussian-integer rotation per angle, "
            "gain restored per angle",
            [("radius scale-up", r"$x_0 = u \cdot 2^{G}$,  $y_0 = v \cdot 2^{G}$  (G guard bits)"),
             ("shared partial products", r"$2x_0,\ 8x_0,\ 48x_0,\ 21x_0,\ 33x_0$ (and for $y_0$): shifts + adds"),
             ("rotation by $P_k = a_k + j b_k$",
              r"$x_a = 2x_0 + (a_k{-}2)x_0 - b_k y_0$,  $y_a = b_k x_0 + 2y_0 + (a_k{-}2)y_0$")],
            "W+G+8",
            [("radius scale-down", r"$K_k \approx 1/|P_k|$: four signed shifts, selected by k"),
             ("rounding", r"round half to even, remove the G guard bits, wrap to W bits")],
            [t1[0][0] + ":  " + t1[0][1], t1[1][0] + ":  " + t1[1][1], t1[2][0] + ":  " + t1[2][1]])
    rows = []
    for k in cordic2.ANGLE_CODES:
        f, s3, s5, n7, n9 = cordic2.CTRL[k]
        rows.append(f"k = {k} ({deg2[k]:.3f}°):  FA {'(5+5j)/8' if f else '(7+j)/8'},  s3 {s3:+d},  "
                    f"s5 {s5:+d},  n7 {n7:+d},  n9 {n9:+d}")
    _column(ax, 8.7, "CORDIC-II mode (extension)", "shared stages, one radius scaling for all angles",
            [("radius scale-up", r"$x_0 = u \cdot 2^{G}$,  $y_0 = v \cdot 2^{G}$"),
             ("friend angle", r"$(7+j)/8$ (8.13°) or $(5+5j)/8$ (45°): two adders, /8 by shift"),
             (r"USR stage $2^{-3}$", r"rotation $s_3 \cdot 2\,\arctan 2^{-3}$, $s_3 \in \{-1, 0, +1\}$")],
            "W+G+1",
            [(r"USR stage $2^{-5}$ + nano-rotation",
              r"$s_5 \cdot 2\,\arctan 2^{-5}$, then $n_7 2^{-7} + n_9 2^{-9}$"),
             ("one radius scaling, rounding",
              r"$K = 1 + 2^{-3} - 2^{-6} + 2^{-8} - 2^{-11}$, round half to even")],
            rows)
    save(fig, path_out)
