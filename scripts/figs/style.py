"""Shared visual language of every figure: palette, ink, chart chrome and diagram primitives.

Charts follow one system: categorical slots in a fixed order (validated for colour-
vision deficiency), 2 px lines, >= 8 px markers with a surface ring, hairline solid
grid, text always in the ink colours.  Block diagrams use light tints of the same
hues: blue = butterfly unit, orange = central CORDIC unit, aqua = memory, grey =
control.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

# ------------------------------------------------------------------ palette
S1, S2, S3, S4 = "#257de0", "#f47230", "#00b894", "#6a4ce2"     # blue, orange, aqua, violet
MODE_COLOR = {"table1": S1, "cordic2x": S2}
MODE_LABEL = {"table1": "Table 1 micro-rotations (paper)", "cordic2x": "CORDIC-II extension"}
INK, INK2 = "#191919", "#666666"
GRID, AXIS = "#e7e7e7", "#c2c2c2"
SURFACE = "#ffffff"
NEUTRAL = "#9c9c9c"

# diagram tints (fill, edge)
BF_FILL, BF_EDGE = "#dcebfc", "#257de0"
MR_FILL, MR_EDGE = "#fde5d8", "#e0611f"
MEM_FILL, MEM_EDGE = "#d4f3ec", "#00a383"
CTL_FILL, CTL_EDGE = "#f1f1f1", "#8a8a8a"
IO_FILL, IO_EDGE = "#ffffff", "#8a8a8a"
HL_FILL, HL_EDGE = "#ece8fc", "#6a4ce2"

DPI = 200


def setup() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "text.color": INK,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 10, "axes.titleweight": "bold", "axes.labelsize": 9,
        "axes.linewidth": 0.8, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "grid.linestyle": "-", "axes.axisbelow": True, "axes.spines.top": False,
        "axes.spines.right": False, "xtick.color": INK2, "ytick.color": INK2,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.frameon": False,
        "legend.fontsize": 8, "lines.linewidth": 2.0, "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round", "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "mathtext.fontset": "dejavusans",
    })


def save(fig, path) -> None:
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def marker_kw(color: str, size: float = 7) -> dict:
    """Filled marker with a 2 px surface ring."""
    return dict(marker="o", markersize=size, markerfacecolor=color, markeredgecolor=SURFACE,
                markeredgewidth=1.4)


def panel_label(ax, s: str, x: float = -0.02, y: float = 1.04) -> None:
    ax.text(x, y, s, transform=ax.transAxes, fontsize=11, fontweight="bold", color=INK,
            ha="right", va="bottom")


# ------------------------------------------------------------- diagram primitives
def canvas(w: float, h: float, scale: float = 1.0):
    fig, ax = plt.subplots(figsize=(w * scale, h * scale))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text="", fill=IO_FILL, edge=IO_EDGE, fs=8.5, bold=False, lw=1.1,
        radius=0.08, color=INK, va="center", ha="center", tx=None, ty=None, z=2, style="round"):
    """Rounded box with lower-left corner (x, y)."""
    if style == "round":
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                           facecolor=fill, edgecolor=edge, linewidth=lw, zorder=z)
    else:
        p = Rectangle((x, y), w, h, facecolor=fill, edgecolor=edge, linewidth=lw, zorder=z)
    ax.add_patch(p)
    if text:
        ax.text(x + w / 2 if tx is None else tx, y + h / 2 if ty is None else ty, text, fontsize=fs,
                fontweight="bold" if bold else "normal", ha=ha, va=va, color=color, zorder=z + 1,
                linespacing=1.25)
    return p


def arrow(ax, p0, p1, color=INK, lw=1.1, style="-|>", ms=8, ls="-", z=3, shrink=0.0,
          connection="arc3,rad=0"):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=ms, color=color, linewidth=lw,
                        linestyle=ls, zorder=z, shrinkA=shrink, shrinkB=shrink,
                        connectionstyle=connection)
    ax.add_patch(a)
    return a


def path(ax, pts, color=INK, lw=1.1, ls="-", z=3, arrow_end=True, ms=8):
    """Orthogonal polyline through ``pts``, arrowhead on the last segment."""
    for (x0, y0), (x1, y1) in zip(pts[:-2], pts[1:-1]):
        ax.plot([x0, x1], [y0, y1], color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")
    if arrow_end:
        arrow(ax, pts[-2], pts[-1], color=color, lw=lw, ls=ls, z=z, ms=ms)
    else:
        ax.plot([pts[-2][0], pts[-1][0]], [pts[-2][1], pts[-1][1]], color=color, lw=lw, ls=ls,
                zorder=z)


def dot(ax, x, y, color=INK, r=0.045, z=4):
    from matplotlib.patches import Circle
    ax.add_patch(Circle((x, y), r, facecolor=color, edgecolor=color, zorder=z))


def label(ax, x, y, s, fs=8, color=INK2, ha="center", va="center", bold=False, z=5, **kw):
    return ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va, zorder=z,
                   fontweight="bold" if bold else "normal", **kw)
