"""Modulo schedule: resource, precedence, lifetime and register-allocation invariants."""
import pytest

from dct8 import flowgraph as fg
from dct8 import schedule

SCH = schedule.build()


def test_latency_and_memory():
    assert SCH.t0 == 15
    assert SCH.nregs == {"IB": 1, "BM": 8, "MM": 5, "OB": 5}
    assert SCH.out_block_offset == 1


def test_resources_per_phase():
    for row in SCH.table:
        assert sum(1 for b in row["bf"] if b) <= schedule.BF_UNITS
    issues = [SCH.times[op.name] % schedule.PERIOD for op in fg.OPS if op.unit == "MR"]
    assert len(issues) == len(set(issues)) == 5              # one CORDIC issue per phase
    bf_slots = [(SCH.times[op.name] % 8, SCH.units[op.name]) for op in fg.OPS if op.unit == "BF"]
    assert len(bf_slots) == len(set(bf_slots)) == 12


def test_precedence():
    lat = {"BF": schedule.BF_LAT, "MR": SCH.mr_lat}
    for op in fg.OPS:
        for v in op.ins:
            if v in fg.PRODUCER:
                p = fg.OP_BY_NAME[fg.PRODUCER[v]]
                assert SCH.times[op.name] >= SCH.times[p.name] + lat[p.unit]
    for name, t in schedule.S_TIMES.items():
        assert SCH.times[name] == t


def test_lifetimes_and_allocation():
    by_bank = {}
    for v in SCH.values.values():
        assert 1 <= v.length <= schedule.PERIOD
        by_bank.setdefault((v.bank, v.reg), []).append(v)
    # two values sharing a register never overlap (modulo the period)
    for vs in by_bank.values():
        occ = set()
        for v in vs:
            cyc = {c % schedule.PERIOD for c in range(v.avail, v.last + 1)}
            assert not (occ & cyc) or len(vs) == 1
            occ |= cyc


@pytest.mark.parametrize("key,limit", [("BM.rd", 4), ("BM.wr", 4), ("MM.rd", 2), ("OB.rd", 1)])
def test_port_usage(key, limit):
    assert schedule.port_usage(SCH)[key] <= limit


def test_utilisation():
    u = schedule.utilisation(SCH)
    assert u["butterfly unit"] == 12 / 16 and u["CORDIC unit"] == 5 / 8
