#!/usr/bin/env python3
"""Generate every figure in figures/ from the models in python/dct8.

    python3 scripts/make_figures.py            # all figures
    python3 scripts/make_figures.py flowgraph  # selected figures
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from figs import style  # noqa: E402

FIGS = {}


def register(name):
    def deco(fn):
        FIGS[name] = fn
        return fn
    return deco


@register("flowgraph")
def _flowgraph(out):
    from figs import flowgraph_fig
    flowgraph_fig.draw(out / "radix2_flowgraph.png")


@register("architecture")
def _architecture(out):
    from figs import architecture_fig
    architecture_fig.draw(out / "processor_architecture.png")


@register("cordic")
def _cordic(out):
    from figs import cordic_fig
    cordic_fig.draw(out / "cordic_unit.png")


@register("schedule")
def _schedule(out):
    from figs import schedule_fig
    schedule_fig.draw(out / "schedule.png")


_IMAGES = {}


def _images():
    if not _IMAGES:
        from dct8 import analysis
        _IMAGES.update(analysis.test_images())
    return _IMAGES


@register("accuracy")
def _accuracy(out):
    from figs import charts
    charts.accuracy(out / "accuracy_wordlength.png", _images())


@register("design_space")
def _design_space(out):
    from figs import charts
    charts.design_space(out / "cordic_design_space.png")


@register("images")
def _images_fig(out):
    from figs import charts
    for row in charts.images_fig(out / "zonal_compression.png", _images()):
        print("   %-8s 64:%-2d  processor %.2f dB   double %.2f dB" % row)


@register("dynamic_range")
def _dynamic_range(out):
    from figs import charts
    charts.dynamic_range(out / "dynamic_range.png")


@register("dct2d")
def _dct2d(out):
    from figs import diagrams2
    diagrams2.dct2d(out / "dct2d_processor.png")


@register("dct16")
def _dct16(out):
    from figs import diagrams2
    diagrams2.dct16(out / "dct16_extension.png")


@register("flow")
def _flow(out):
    from figs import diagrams2
    diagrams2.flow(out / "verification_flow.png")


@register("timing")
def _timing(out):
    from figs import diagrams2
    diagrams2.timing(out / "io_timing.png")


def main(argv) -> int:
    style.setup()
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    names = argv or list(FIGS)
    for n in names:
        FIGS[n](out)
        print("figure:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
