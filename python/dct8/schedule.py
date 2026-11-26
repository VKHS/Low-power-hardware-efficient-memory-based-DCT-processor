"""Modulo schedule, value lifetimes and memory-bank allocation of the processor.

The processor accepts one sample per clock in natural order, i.e. one 8-point
block every ``PERIOD = 8`` cycles, and returns the coefficients in natural order.
Per block it executes 12 butterflies and 5 rotations on two processing elements
that are time-shared by all blocks:

* **butterfly unit** -- two butterfly datapaths, each with its SS unit
  (12 butterflies / 16 slots = 75 % busy); datapath BF0 also receives the
  incoming sample directly, so the stage-1 butterfly (x[2n], x[2n+1]) fires in
  the very cycle x[2n+1] arrives, with x[2n] held one cycle in the input
  buffer -- the one-delay feedback of the paper's first butterfly stage;
* **central CORDIC unit** -- the shared micro-rotation unit, two pipeline
  stages (latency ``L = 2``): 5 rotations / 8 slots = 62.5 % busy.

Every other operation is placed by an exact branch-and-bound modulo scheduler
that minimises the output latency ``T0`` (Y0..Y7 leave at cycles T0..T0+7), then
the number of memory words, then the total storage time.  Values live in four
small register-file banks, partitioned by who reads them:

* ``IB``  input buffer            x[2n] waiting one cycle for x[2n+1]
* ``BM``  butterfly buffers (M_B) stage-1/2 results read by the butterfly unit
* ``MM``  memory bank             operands of the central CORDIC unit
                                  (written by the butterfly unit and by the
                                  CORDIC unit itself, read only by the CORDIC unit)
* ``OB``  output buffer           Y values: the rearrange unit that turns the
                                  out-of-order results into in-order output

Every value has one reader and lives at most ``PERIOD`` cycles, so each value
of each block occupies the *same* register and the address generator is a
pure function of the 3-bit phase counter (low-complexity distributed control).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import flowgraph as fg

PERIOD = 8
BF_LAT = 1
BF_UNITS = 2
DEFAULT_MR_LAT = 2
S_TIMES = {"S0": 1, "S1": 3, "S2": 5, "S3": 7}   # x[2n+1] arrives in cycle 2n+1
BANKS = ("IB", "BM", "MM", "OB")


@dataclass
class Value:
    name: str
    bank: str
    avail: int          # first cycle in which it can be read
    last: int           # cycle in which it is read (its single use)
    reg: int = -1

    @property
    def length(self) -> int:
        return self.last - self.avail + 1


@dataclass
class Schedule:
    mr_lat: int
    times: dict
    units: dict
    t0: int
    values: dict
    nregs: dict
    maxlive: dict
    table: list = field(default_factory=list)

    @property
    def out_phase(self) -> int:
        return self.t0 % PERIOD

    @property
    def out_block_offset(self) -> int:
        return self.t0 // PERIOD

    def to_json(self) -> str:
        d = {"period": PERIOD, "bf_latency": BF_LAT, "mr_latency": self.mr_lat, "t0": self.t0,
             "op_times": self.times, "bf_units": self.units, "nregs": self.nregs,
             "maxlive": self.maxlive, "values": {k: v.__dict__ for k, v in self.values.items()},
             "phase_table": self.table}
        return json.dumps(d, indent=2)


def _lat(op: fg.Op, mr_lat: int) -> int:
    return BF_LAT if op.unit == "BF" else mr_lat


def _avail(name: str, times: dict, mr_lat: int) -> int:
    if name.startswith("x"):
        return int(name[1:]) + 1
    op = fg.OP_BY_NAME[fg.PRODUCER[name]]
    return times[op.name] + _lat(op, mr_lat)


def _t0(times: dict, mr_lat: int) -> int:
    return max(_avail(f"Y{k}", times, mr_lat) - k for k in range(8))


def _storage(times: dict, mr_lat: int) -> int:
    t0 = _t0(times, mr_lat)
    tot = 0
    for op in fg.OPS:
        for v in op.outs:
            last = t0 + int(v[1:]) if v.startswith("Y") else times[fg.CONSUMER[v]]
            tot += last - _avail(v, times, mr_lat) + 1
    return tot


def _max_lifetime(times: dict, mr_lat: int) -> int:
    t0 = _t0(times, mr_lat)
    worst = max(times[fg.CONSUMER[f"x{n}"]] - n for n in range(0, 8, 2))
    for op in fg.OPS:
        for v in op.outs:
            last = t0 + int(v[1:]) if v.startswith("Y") else times[fg.CONSUMER[v]]
            worst = max(worst, last - _avail(v, times, mr_lat) + 1)
    return worst


def solve(mr_lat: int = DEFAULT_MR_LAT) -> dict:
    """Exact branch-and-bound modulo scheduling (2 butterfly datapaths, 1 CORDIC unit)."""
    order = [op.name for op in fg.OPS if op.name not in S_TIMES]
    deps = {n: [fg.OP_BY_NAME[fg.PRODUCER[v]] for v in fg.OP_BY_NAME[n].ins] for n in order}
    best: list = [None, None]

    def asap(t):
        tt = dict(t)
        for n in order:
            if n not in tt:
                tt[n] = max(tt[d.name] + _lat(d, mr_lat) for d in deps[n])
        return tt

    def rec(i, t, used):
        if best[0] is not None and _t0(asap(t), mr_lat) > best[0][0]:
            return
        if i == len(order):
            if _max_lifetime(t, mr_lat) > PERIOD:      # keeps every address phase-only
                return
            t0_, vals_ = lifetimes(t, mr_lat)
            nregs_, _ = allocate(vals_)
            key = (_t0(t, mr_lat), sum(nregs_.values()), _storage(t, mr_lat))
            if best[0] is None or key < best[0]:
                best[0], best[1] = key, dict(t)
            return
        n = order[i]
        op = fg.OP_BY_NAME[n]
        cap = BF_UNITS if op.unit == "BF" else 1
        est = max(t[d.name] + _lat(d, mr_lat) for d in deps[n])
        for tt in range(est, est + PERIOD):
            slot = (op.unit, tt % PERIOD)
            if used.get(slot, 0) >= cap:
                continue
            t[n] = tt
            used[slot] = used.get(slot, 0) + 1
            rec(i + 1, t, used)
            used[slot] -= 1
            del t[n]

    used = {("BF", v % PERIOD): 1 for v in S_TIMES.values()}
    rec(0, dict(S_TIMES), used)
    return best[1]


def assign_units(times: dict) -> dict:
    """Stage-1 butterflies on BF0 (it owns the input bypass); others fill free datapaths."""
    units, busy = {}, set()
    for n in S_TIMES:
        units[n] = 0
        busy.add((0, times[n] % PERIOD))
    for op in fg.OPS:
        if op.unit != "BF" or op.name in units:
            continue
        ph = times[op.name] % PERIOD
        u = 0 if (0, ph) not in busy else 1
        assert (u, ph) not in busy
        units[op.name] = u
        busy.add((u, ph))
    return units


def _bank_of(name: str) -> str:
    if name.startswith("x"):
        return "IB"
    if name.startswith("Y"):
        return "OB"
    return "MM" if fg.OP_BY_NAME[fg.CONSUMER[name]].unit == "MR" else "BM"


def lifetimes(times: dict, mr_lat: int) -> tuple[int, dict]:
    t0 = _t0(times, mr_lat)
    vals: dict = {}
    for n in range(0, 8, 2):                        # x[2n] waits for its partner
        name = f"x{n}"
        vals[name] = Value(name, "IB", n + 1, times[fg.CONSUMER[name]])
    for op in fg.OPS:
        for v in op.outs:
            avail = times[op.name] + _lat(op, mr_lat)
            last = t0 + int(v[1:]) if v.startswith("Y") else times[fg.CONSUMER[v]]
            vals[v] = Value(v, _bank_of(v), avail, last)
    return t0, vals


def _conflict(a: Value, b: Value) -> bool:
    for m in range(-3, 4):
        s, e = b.avail + PERIOD * m, b.last + PERIOD * m
        if not (a.last < s or e < a.avail):
            return True
    return False


def _maxlive(vs: list) -> int:
    best = 0
    for ph in range(PERIOD):
        best = max(best, sum(sum(1 for t in range(v.avail, v.last + 1) if t % PERIOD == ph)
                             for v in vs))
    return best


def allocate(vals: dict) -> tuple[dict, dict]:
    """Exact minimum-register colouring of the periodic lifetime arcs, per bank."""
    nregs, maxlive = {}, {}
    for bank in BANKS:
        vs = sorted((v for v in vals.values() if v.bank == bank), key=lambda v: (v.avail, v.name))
        for v in vs:
            if v.length > PERIOD:
                raise ValueError(f"{v.name} lives {v.length} > {PERIOD} cycles")
        ml = _maxlive(vs)
        maxlive[bank] = ml
        for r in range(ml, ml + 4):
            assign: dict = {}

            def rec(i):
                if i == len(vs):
                    return True
                for reg in range(r):
                    if all(not (assign.get(u.name) == reg and _conflict(u, vs[i])) for u in vs[:i]):
                        assign[vs[i].name] = reg
                        if rec(i + 1):
                            return True
                        del assign[vs[i].name]
                return False

            if rec(0):
                for v in vs:
                    v.reg = assign[v.name]
                nregs[bank] = r
                break
    return nregs, maxlive


def phase_table(times, units, t0, vals, mr_lat) -> list:
    """Per-phase control words decoded by the distributed controller."""
    tab = [dict(phase=p, ib_w=None, bf=[None, None], mr_issue=None, mr_done=None, ob_r=None,
                out_k=None) for p in range(PERIOD)]
    for n in range(0, 8, 2):
        tab[n]["ib_w"] = vals[f"x{n}"].reg
    for op in fg.OPS:
        ph = times[op.name] % PERIOD
        if op.unit == "BF":
            srcs = [("IN", None) if (v.startswith("x") and int(v[1:]) % 2) else
                    (vals[v].bank, vals[v].reg) for v in op.ins]
            dsts = [(vals[v].bank, vals[v].reg) for v in op.outs]
            tab[ph]["bf"][units[op.name]] = dict(op=op.name, ins=op.ins, outs=op.outs, src=srcs,
                                                 dst=dsts, stage=op.param)
        else:
            tab[ph]["mr_issue"] = dict(op=op.name, k=op.param, ins=op.ins,
                                       src=[(vals[v].bank, vals[v].reg) for v in op.ins])
            phd = (times[op.name] + mr_lat - 1) % PERIOD
            tab[phd]["mr_done"] = dict(op=op.name, outs=op.outs,
                                       dst=[(vals[v].bank, vals[v].reg) for v in op.outs])
    for k in range(8):
        ph = (t0 + k) % PERIOD
        tab[ph]["ob_r"] = vals[f"Y{k}"].reg
        tab[ph]["out_k"] = k
    return tab


def build(mr_lat: int = DEFAULT_MR_LAT) -> Schedule:
    times = solve(mr_lat)
    units = assign_units(times)
    t0, vals = lifetimes(times, mr_lat)
    nregs, maxlive = allocate(vals)
    sch = Schedule(mr_lat, times, units, t0, vals, nregs, maxlive)
    sch.table = phase_table(times, units, t0, vals, mr_lat)
    return sch


def utilisation(sch: Schedule) -> dict:
    n_bf = sum(1 for r in sch.table for b in r["bf"] if b)
    n_mr = sum(1 for r in sch.table if r["mr_issue"])
    return {"BF0": sum(1 for r in sch.table if r["bf"][0]) / PERIOD,
            "BF1": sum(1 for r in sch.table if r["bf"][1]) / PERIOD,
            "butterfly unit": n_bf / (BF_UNITS * PERIOD), "CORDIC unit": n_mr / PERIOD}


def port_usage(sch: Schedule) -> dict:
    """Peak simultaneous reads / writes per bank."""
    rd = {b: [0] * PERIOD for b in BANKS}
    wr = {b: [0] * PERIOD for b in BANKS}
    for r in sch.table:
        p = r["phase"]
        if r["ib_w"] is not None:
            wr["IB"][p] += 1
        for b in r["bf"]:
            if b:
                for bank, _ in b["src"]:
                    if bank != "IN":
                        rd[bank][p] += 1
                for bank, _ in b["dst"]:
                    wr[bank][p] += 1
        if r["mr_issue"]:
            for bank, _ in r["mr_issue"]["src"]:
                rd[bank][p] += 1
        if r["mr_done"]:
            for bank, _ in r["mr_done"]["dst"]:
                wr[bank][p] += 1
        if r["ob_r"] is not None:
            rd["OB"][p] += 1
    return {f"{b}.{k}": max(v) for b in BANKS for k, v in (("rd", rd[b]), ("wr", wr[b]))}
