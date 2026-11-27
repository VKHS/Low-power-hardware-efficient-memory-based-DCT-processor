#!/usr/bin/env python3
"""Build the results page ``artifact/index.html`` and its data ``artifact/data/evidence.json``.

    python3 scripts/make_artifact.py              # recompute everything (about 70 s), write both
    python3 scripts/make_artifact.py --assemble   # keep evidence.json, rebuild index.html only
    python3 scripts/make_artifact.py --check      # recompute and compare with what is committed

Every number on the page is computed by ``dct8.evidence`` from the bit-accurate models, the golden
vectors and the schedule, or is quoted from the paper and labelled as such.  The page embeds the
vector files, so a browser can re-run the checks without any other file.

``--check`` fails when the committed evidence differs from a fresh run (integers, text and
booleans exactly; floating-point values within a small tolerance, so that another NumPy build
does not trip it; the ``environment`` block is ignored) or when ``index.html`` is not the page that
the committed inputs produce.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from dct8 import evidence  # noqa: E402

ART = ROOT / "artifact"
SRC = ART / "src"
DATA = ART / "data"
JS_FILES = ("sha256.js", "model.js", "sched.js", "app.js")
ABS_TOL, REL_TOL = 2e-4, 1e-6


def vector_files() -> dict:
    """Raw text of every file the page verifies (all ASCII)."""
    vdir = ROOT / "vectors"
    man = json.loads((vdir / "manifest.json").read_text())
    out = {"manifest.json": (vdir / "manifest.json").read_text(),
           "schedule.json": (vdir / "schedule.json").read_text(), "sets": {}}
    for name in man:
        out["sets"][name] = {k: (vdir / f"{name}_{suf}").read_text()
                             for k, suf in (("in", "in.txt"), ("out", "out.txt"),
                                            ("stim", "stim.hex"), ("expect", "expect.hex"))}
    blob = json.dumps(out)
    blob.encode("ascii")                                    # the page hashes ASCII bytes
    return out


def js_json(obj) -> str:
    """JSON that is safe inside a <script type="application/json"> element."""
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")


FPGA_TEXT = ("device", "tool", "config")
FPGA_INT = ("wl", "lut", "ff", "dsp")
FPGA_REAL = ("fmax_mhz", "power_mw")


def fpga_measured(path: Path | None = None) -> dict | None:
    """The Vivado figures of this repository's RTL, or ``None`` while they have not been measured.

    ``artifact/data/fpga_measured.json`` is written by hand from the reports of
    ``scripts/vivado_synth.tcl`` (template: ``fpga_measured.template.json``).  Every field must be
    present and of the right kind; a template left unfilled stops the build instead of reaching
    the page.
    """
    p = DATA / "fpga_measured.json" if path is None else path
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    bad = [k for k in FPGA_TEXT if not (isinstance(d.get(k), str) and d[k].strip())]
    bad += [k for k in FPGA_INT if not (isinstance(d.get(k), int) and not isinstance(d.get(k), bool)
                                        and d[k] >= 0)]
    bad += [k for k in FPGA_REAL if not (isinstance(d.get(k), (int, float))
                                         and not isinstance(d.get(k), bool) and d[k] > 0)]
    if bad:
        raise SystemExit(f"{p}: missing or invalid fields {sorted(bad)} "
                         "(text for device/tool/config, whole numbers for wl/lut/ff/dsp, "
                         "positive numbers for fmax_mhz/power_mw)")
    return {k: d[k] for k in FPGA_TEXT + FPGA_INT + FPGA_REAL}


def assemble(ev: dict) -> str:
    html = (SRC / "template.html").read_text(encoding="utf-8")
    css = (SRC / "style.css").read_text(encoding="utf-8")
    js = "\n".join((SRC / f).read_text(encoding="utf-8") for f in JS_FILES)
    parts = {
        "/*{{CSS}}*/": css,
        "/*{{JS}}*/": js,
        "{{EVIDENCE_JSON}}": js_json(ev),
        "{{VECTORS_JSON}}": js_json(vector_files()),
        "{{FPGA_JSON}}": js_json(fpga_measured()),
        "{{BUILD_ID}}": ev["meta"]["source"]["sha256"][:12],
    }
    for key, val in parts.items():
        if html.count(key) != 1:
            raise SystemExit(f"template placeholder {key!r} occurs {html.count(key)} times")
        html = html.replace(key, val)
    return html


def diff(a, b, path="") -> list[str]:
    """Differences between two JSON trees (floats within tolerance, ``environment`` ignored)."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if path == "/meta" and k == "environment":
                continue
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'committed' if k in a else 'fresh run'}")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float))
                and math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)):
            out.append(f"{path}: {a!r} vs {b!r}")
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="recompute and compare, change nothing")
    ap.add_argument("--assemble", action="store_true", help="keep evidence.json, rebuild index.html")
    args = ap.parse_args()
    log = lambda s: print(f"  {s}", file=sys.stderr, flush=True)                      # noqa: E731
    jpath, hpath = DATA / "evidence.json", ART / "index.html"

    if args.assemble:
        ev = json.loads(jpath.read_text(encoding="utf-8"))
        hpath.write_text(assemble(ev), encoding="utf-8")
        print(f"wrote {hpath.relative_to(ROOT)} ({hpath.stat().st_size:,} bytes)")
        return 0

    print("computing evidence ...", file=sys.stderr)
    fresh = evidence.collect(ROOT, log=log)
    failed = [c["id"] for c in fresh["cross_checks"] if not c["ok"]]
    if failed:
        print(f"cross-checks failed: {failed}", file=sys.stderr)
        return 1

    if args.check:
        bad = 0
        if not jpath.exists():
            print(f"{jpath.relative_to(ROOT)} is missing", file=sys.stderr)
            return 1
        committed = json.loads(jpath.read_text(encoding="utf-8"))
        d = diff(committed, fresh)
        if d:
            bad += 1
            print(f"{jpath.relative_to(ROOT)} differs from a fresh run ({len(d)} differences):", file=sys.stderr)
            for line in d[:25]:
                print("   ", line, file=sys.stderr)
        if not hpath.exists() or hpath.read_text(encoding="utf-8") != assemble(committed):
            bad += 1
            print(f"{hpath.relative_to(ROOT)} is not the page the committed inputs produce; "
                  "run python3 scripts/make_artifact.py --assemble", file=sys.stderr)
        if bad:
            return 1
        print("artifact up to date: evidence.json matches a fresh run; index.html matches its inputs")
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    jpath.write_text(evidence.to_json(fresh), encoding="utf-8")
    hpath.write_text(assemble(fresh), encoding="utf-8")
    print(f"wrote {jpath.relative_to(ROOT)} ({jpath.stat().st_size:,} bytes) and "
          f"{hpath.relative_to(ROOT)} ({hpath.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
