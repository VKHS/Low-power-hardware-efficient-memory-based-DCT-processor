# MATLAB / Octave

Bit-accurate model of the processor, identical word for word to the Python, RTL and HLS
implementations.

| function | content |
|---|---|
| `dct8_cfg` | fixed-point configuration (B_IN, W, G, SS, mode) and derived H, F, E |
| `dct8_fixed` | 1-D processor, vectorised over the rows of an N×8 matrix |
| `dct8_cordic` | central CORDIC unit (Table 1 or CORDIC-II), counter-clockwise by ~kπ/16 |
| `dct2d_fixed` | 8×8 2-D processor on an 8×8×N stack of blocks |
| `dct16_fixed` | 16-point processor: two 8-point engines + Table 5 CORDIC array |
| `dct8_rnd`, `dct8_rne`, `dct8_rno`, `dct8_wrap` | rounding and wrap-around primitives |
| `dct8_ref` | orthonormal DCT-II matrix |
| `run_tests` | bit-exact check against `../vectors` and accuracy checks |
| `demo_dct8` | micro-rotation table, accuracy versus word length, zonal compression |

```matlab
addpath('matlab'); run_tests                  % MATLAB R2016b+ or GNU Octave 7+
cfg = dct8_cfg(8, 14, 3, [0 0 0], 'table1');
Y = dct8_fixed([12 -7 100 3 -128 127 0 45], cfg)     % the RTL output words
```
