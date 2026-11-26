"""Signal-flow graph of the scalable radix-2 8-point DCT executed by the processor.

Decomposition (paper, Eqs. 4-13): with x_L[n] = x[2n] + x[2n+1] and
x_H[n] = x[2n] - x[2n+1] (adjacent pairs), the N-point DCT splits into an
N/2-point DCT of x_L, an N/2-point DCT of (-1)^n x_H, and N/2 - 1 rotations by
-k*pi/(2N) that merge them.  Applied recursively for N = 8 -> 4 -> 2 this gives
three butterfly levels and two rotation levels:

=======  ====  ===================  ===================  ==========================
op       unit  inputs               outputs              meaning
=======  ====  ===================  ===================  ==========================
S0..S3   BF    (x[2n], x[2n+1])     (L_n, H_n)           stage 1: x_L, x_H
T0, T1   BF    (L0,L1), (L2,L3)     (LL, LH)             stage 2: 4-pt DCT of x_L
T2, T3   BF    (H0,H1), (H2,H3)     (HH, HL)             stage 2: 4-pt DCT of (-1)^n x_H
U0..U3   BF    (LL0,LL1) ...        (S, D) ...           stage 3: 2-point DCTs
V0, V1   MR    (S', D), (SB', DB)   (A3, A1), (B3, B1)   stage 3: rotations by -pi/8
W1       MR    (B3, A1)             (Y7, Y1)             stage 4: rotation by -pi/16
W2       MR    (DB', D')            (Y6, Y2)             stage 4: rotation by -2pi/16
W3       MR    (B1, A3)             (Y5, Y3)             stage 4: rotation by -3pi/16
=======  ====  ===================  ===================  ==========================

``Y0 = S`` and ``Y4 = SB`` leave stage 3 without a rotation.  Every output is
``Y_k = 2*sqrt(2) * X_k`` (orthonormal DCT-II X) -- the paper's post-scaling
factor 1/(2 sqrt 2) is the only constant left, and it is common to all eight
outputs (for the 2-D DCT the two factors combine to 1/8, a pure shift).

The rotation unit (MR-PE) only rotates counter-clockwise; a rotation by
``-theta`` of ``(u, v)`` is obtained for free by swapping both its operands and
its results: ``Rot(-theta)(u, v) = swap(Rot(+theta)(v, u))``.  The table above
is written in that swapped form.  Every intermediate value has exactly one
consumer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Op:
    name: str
    unit: str            # "BF" or "MR"
    ins: tuple[str, str]
    outs: tuple[str, str]
    param: int           # BF: butterfly stage 1/2/3 (selects the safe scaling); MR: k (k*pi/16)
    level: int           # pipeline stage of the flow graph (1..4), for figures


OPS: tuple[Op, ...] = (
    # stage 1: adjacent pairs, x_L / x_H
    Op("S0", "BF", ("x0", "x1"), ("L0", "H0"), 1, 1),
    Op("S1", "BF", ("x2", "x3"), ("L1", "H1"), 1, 1),
    Op("S2", "BF", ("x4", "x5"), ("L2", "H2"), 1, 1),
    Op("S3", "BF", ("x6", "x7"), ("L3", "H3"), 1, 1),
    # stage 2: the two 4-point sub-DCTs, first level
    Op("T0", "BF", ("L0", "L1"), ("LL0", "LH0"), 2, 2),
    Op("T1", "BF", ("L2", "L3"), ("LL1", "LH1"), 2, 2),
    Op("T2", "BF", ("H0", "H1"), ("HH0", "HL0"), 2, 2),
    Op("T3", "BF", ("H2", "H3"), ("HH1", "HL1"), 2, 2),
    # stage 3: 2-point DCTs
    Op("U0", "BF", ("LL0", "LL1"), ("Y0", "D"), 3, 3),
    Op("U1", "BF", ("LH0", "LH1"), ("Sp", "Dp"), 3, 3),
    Op("U2", "BF", ("HL0", "HL1"), ("Y4", "DB"), 3, 3),
    Op("U3", "BF", ("HH0", "HH1"), ("SBp", "DBp"), 3, 3),
    # stage 3: rotations by -pi/8 of the two 4-point sub-DCTs
    Op("V0", "MR", ("Sp", "D"), ("A3", "A1"), 2, 3),
    Op("V1", "MR", ("SBp", "DB"), ("B3", "B1"), 2, 3),
    # stage 4: merging rotations by -k pi/16
    Op("W1", "MR", ("B3", "A1"), ("Y7", "Y1"), 1, 4),
    Op("W2", "MR", ("DBp", "Dp"), ("Y6", "Y2"), 2, 4),
    Op("W3", "MR", ("B1", "A3"), ("Y5", "Y3"), 3, 4),
)

OP_BY_NAME = {op.name: op for op in OPS}
INPUTS = tuple(f"x{n}" for n in range(8))
OUTPUTS = tuple(f"Y{k}" for k in range(8))
PRODUCER = {v: op.name for op in OPS for v in op.outs}
CONSUMER = {v: op.name for op in OPS for v in op.ins}
N_BF = sum(op.unit == "BF" for op in OPS)
N_MR = sum(op.unit == "MR" for op in OPS)


def evaluate(x, bf, mr) -> list:
    """Evaluate the flow graph with user-supplied primitives.

    ``bf(p, q, stage) -> (p+q, p-q)`` and ``mr(u, v, k) -> CCW rotation by k*pi/16``.
    Returns ``[Y0, ..., Y7]``.
    """
    val = evaluate_all(x, bf, mr)
    return [val[y] for y in OUTPUTS]


def evaluate_all(x, bf, mr) -> dict:
    """Like :func:`evaluate` but returns every node value."""
    val = {f"x{n}": x[n] for n in range(8)}
    for op in OPS:
        p, q = val[op.ins[0]], val[op.ins[1]]
        r = bf(p, q, op.param) if op.unit == "BF" else mr(p, q, op.param)
        val[op.outs[0]], val[op.outs[1]] = r
    return val
