"""Low-power hardware-efficient memory-based 8-point DCT processor -- reference models.

Modules
-------
reference   floating-point orthonormal DCT-II / IDCT (1-D and 8x8 2-D)
fixedpoint  rounding / wrap primitives that define the bit-exact behaviour
flowgraph   scalable radix-2 signal-flow graph: 12 butterflies + 5 rotations
cordic2     central CORDIC unit: Table 1 micro-rotations and the CORDIC-II extension
processor   bit-accurate functional model and fixed-point configuration
schedule    exact modulo schedule, value lifetimes, memory-bank allocation, microcode
machine     cycle-accurate model (register-for-register equivalent of the RTL)
dct2d       8x8 2-D processor: two 1-D processors + single 64-word transpose buffer
scalable    N-point radix-2 recursion and the 16-point processor (Table 5 CORDIC array)
analysis    overflow proof, word-length sweeps, image and compression experiments
vectors     golden vectors for the RTL / HLS / MATLAB test benches
cost        architecture-level operator and register counts
emit        generators of rtl/dct8_ctrl.v, rtl/dct8_sched_params.vh, hls/src/dct8_sched.h
"""
from .processor import Config, dct8_fixed, dct8_approx, dct8_fixed_batch   # noqa: F401
from .dct2d import Config2D, dct2d_fixed, dct2d_fixed_batch, dct2d_image    # noqa: F401
from .reference import dct8, idct8, dct2, idct2             # noqa: F401

__version__ = "1.0.0"
