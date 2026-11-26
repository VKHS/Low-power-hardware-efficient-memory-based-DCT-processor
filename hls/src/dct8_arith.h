// ============================================================================
// dct8_arith.h -- bit-accurate arithmetic of the memory-based DCT processor
// ----------------------------------------------------------------------------
// The two processing elements, written once and shared by every HLS kernel:
//   bf_core : butterfly datapath with its safe-scaling (SS) unit
//             (x 1/2 with von Neumann rounding: (z >> 1) | z[0])
//   MR      : central CORDIC unit, counter-clockwise rotation by ~k*pi/16,
//             k = 1, 2, 3, two pipeline stages, two micro-rotation modes:
//             MODE 0 = Table 1 of the paper (10+j2, 50+j21, 50+j33 with
//             radius scale-up / scale-down), MODE 1 = extended CORDIC-II.
// Bit-exact with python/dct8 and rtl/ (same rnd / rne / rno primitives).
// Every intermediate lives in an explicitly sized variable that is wide enough
// for its value, so the code means the same with the Vitis HLS ap_int types
// and with the C-simulation stand-in in hls/csim_compat.
// ============================================================================
#ifndef DCT8_ARITH_H
#define DCT8_ARITH_H

#include "ap_int.h"

namespace dct8 {

// round half up: (z >> S) + z[S-1]
template <int W, int S>
inline ap_int<W> rnd(const ap_int<W> z) {
#pragma HLS INLINE
    ap_int<W> sh = z >> S;
    ap_int<W> q = sh + (z[S - 1] ? 1 : 0);
    return q;
}

// round half to even: (z >> S) + (z[S-1] & (z[S] | z[S-2:0] != 0))
template <int W, int S>
inline ap_int<W> rne(const ap_int<W> z) {
#pragma HLS INLINE
    ap_int<W> sh = z >> S;
    bool half = z[S - 1];
    bool stick = false;
    for (int i = 0; i < S - 1; i++) {
#pragma HLS UNROLL
        stick = stick || z[i];
    }
    bool odd = z[S];
    ap_int<W> q = sh + ((half && (stick || odd)) ? 1 : 0);
    return q;
}

// von Neumann rounding by one bit (round half to odd): (z >> 1) | z[0]
template <int W>
inline ap_int<W> rno1(const ap_int<W> z) {
#pragma HLS INLINE
    ap_int<W> sh = z >> 1;
    ap_int<W> lsb = z[0] ? 1 : 0;
    ap_int<W> q = sh | lsb;
    return q;
}

// ------------------------------------------------------- butterfly datapath
template <int W>
inline void bf_core(const ap_int<W> a, const ap_int<W> b, const bool scale,
                    ap_int<W>& sum, ap_int<W>& diff) {
#pragma HLS INLINE
    ap_int<W + 1> aw = a;
    ap_int<W + 1> bw = b;
    ap_int<W + 1> s = aw + bw;
    ap_int<W + 1> d = aw - bw;
    if (scale) {
        s = rno1<W + 1>(s);
        d = rno1<W + 1>(d);
    }
    sum = s;      // W bits: never overflows (headroom H = 3 - SS1 - SS2 - SS3)
    diff = d;
}

// ----------------------------------------------------- central CORDIC unit
template <int W, int G, int MODE>
struct MR;

// MODE 0: Table 1 micro-rotations, radius scale-up -> rotation by P_k -> scale-down K_k
template <int W, int G>
struct MR<W, G, 0> {
    static const int WM = W + G + 8;   // pipeline register: |a| + |b| < 2^7
    typedef ap_int<WM> wm_t;

    static void stage_a(const ap_int<W> u, const ap_int<W> v, const int k, wm_t& xa, wm_t& ya) {
#pragma HLS INLINE
        wm_t x0 = u;
        wm_t y0 = v;
        x0 = x0 << G;
        y0 = y0 << G;
        // shared partial products: 2x, 8x | 48x, 2y | 21y | 33y
        wm_t x2 = x0 << 1, y2 = y0 << 1;
        wm_t x8 = x0 << 3, y8 = y0 << 3;
        wm_t x16 = x0 << 4, y16 = y0 << 4;
        wm_t x32 = x0 << 5, y32 = y0 << 5;
        wm_t x4 = x0 << 2, y4 = y0 << 2;
        wm_t x48 = x32 + x16, y48 = y32 + y16;
        wm_t x21 = x16 + x4 + x0, y21 = y16 + y4 + y0;
        wm_t x33 = x32 + x0, y33 = y32 + y0;
        wm_t ax = (k == 1) ? x8 : x48;                      // (a - 2) x0
        wm_t ay = (k == 1) ? y8 : y48;
        wm_t bx = (k == 1) ? x2 : ((k == 2) ? x21 : x33);   // b x0
        wm_t by = (k == 1) ? y2 : ((k == 2) ? y21 : y33);
        xa = x2 + ax - by;                                  // a x0 - b y0
        ya = bx + y2 + ay;                                  // b x0 + a y0
    }

    // K_1 = 2^-3 - 2^-5 + 2^-8 + 2^-11, K_2 = 2^-6 + 2^-8 - 2^-10 - 2^-13,
    // K_3 = 2^-6 + 2^-10 + 2^-13 - 2^-15
    static wm_t scale_down(const wm_t x, const int k) {
#pragma HLS INLINE
        wm_t r;
        if (k == 1)
            r = rnd<WM, 3>(x) - rnd<WM, 5>(x) + rnd<WM, 8>(x) + rnd<WM, 11>(x);
        else if (k == 2)
            r = rnd<WM, 6>(x) + rnd<WM, 8>(x) - rnd<WM, 10>(x) - rnd<WM, 13>(x);
        else
            r = rnd<WM, 6>(x) + rnd<WM, 10>(x) + rnd<WM, 13>(x) - rnd<WM, 15>(x);
        return r;
    }

    static void stage_b(const wm_t xa, const wm_t ya, const int k, ap_int<W>& uo, ap_int<W>& vo) {
#pragma HLS INLINE
        wm_t xs = scale_down(xa, k);
        wm_t ys = scale_down(ya, k);
        uo = rne<WM, G>(xs);
        vo = rne<WM, G>(ys);
    }
};

// MODE 1: CORDIC-II -- friend angle + USR 2^-3 | USR 2^-5 + nano + one radius scaling
template <int W, int G>
struct MR<W, G, 1> {
    static const int WM = W + G + 1;
    static const int WP = WM + 3;      // friend-angle products before the /8
    typedef ap_int<WM> wm_t;
    typedef ap_int<WP> wp_t;

    static void stage_a(const ap_int<W> u, const ap_int<W> v, const int k, wm_t& x2, wm_t& y2) {
#pragma HLS INLINE
        wp_t x0 = u;
        wp_t y0 = v;
        x0 = x0 << G;
        y0 = y0 << G;
        wp_t s = x0 + y0;
        wp_t d = x0 - y0;
        wp_t fx, fy;
        if (k == 3) {                     // (5 + 5j)/8 : 45 deg
            wp_t d4 = d << 2;
            wp_t s4 = s << 2;
            fx = d4 + d;
            fy = s4 + s;
        } else {                          // (7 + j)/8 : 8.130 deg
            wp_t x8 = x0 << 3;
            wp_t y8 = y0 << 3;
            fx = x8 - s;
            fy = y8 + d;
        }
        wp_t fxr = rnd<WP, 3>(fx);
        wp_t fyr = rnd<WP, 3>(fy);
        wm_t x1 = fxr;
        wm_t y1 = fyr;
        // USR 2^-3: s3 = 0 (k=1), +1 (k=2), -1 (k=3)
        wm_t x1r6 = rnd<WM, 6>(x1), y1r6 = rnd<WM, 6>(y1);
        wm_t x1r2 = rnd<WM, 2>(x1), y1r2 = rnd<WM, 2>(y1);
        if (k == 2) {
            x2 = x1 - x1r6 - y1r2;
            y2 = y1 - y1r6 + x1r2;
        } else if (k == 3) {
            x2 = x1 - x1r6 + y1r2;
            y2 = y1 - y1r6 - x1r2;
        } else {
            x2 = x1 + x1r6;
            y2 = y1 + y1r6;
        }
    }

    static void stage_b(const wm_t x2, const wm_t y2, const int k, ap_int<W>& uo, ap_int<W>& vo) {
#pragma HLS INLINE
        // USR 2^-5: s5 = +1 (k=1, 3), 0 (k=2)
        wm_t x3, y3;
        if (k == 2) {
            x3 = x2 + rnd<WM, 10>(x2);
            y3 = y2 + rnd<WM, 10>(y2);
        } else {
            x3 = x2 - rnd<WM, 10>(x2) - rnd<WM, 4>(y2);
            y3 = y2 - rnd<WM, 10>(y2) + rnd<WM, 4>(x2);
        }
        // nano-rotation: k=1: -2^-7, k=2: +2^-9, k=3: -2^-7 - 2^-9
        wm_t x3r7 = rnd<WM, 7>(x3), y3r7 = rnd<WM, 7>(y3);
        wm_t x3r9 = rnd<WM, 9>(x3), y3r9 = rnd<WM, 9>(y3);
        wm_t x4, y4;
        if (k == 1) {
            x4 = x3 + y3r7;
            y4 = y3 - x3r7;
        } else if (k == 2) {
            x4 = x3 - y3r9;
            y4 = y3 + x3r9;
        } else {
            x4 = x3 + y3r7 + y3r9;
            y4 = y3 - x3r7 - x3r9;
        }
        // radius scaling K = 1 + 2^-3 - 2^-6 + 2^-8 - 2^-11
        wm_t x5 = x4 + rnd<WM, 3>(x4) - rnd<WM, 6>(x4) + rnd<WM, 8>(x4) - rnd<WM, 11>(x4);
        wm_t y5 = y4 + rnd<WM, 3>(y4) - rnd<WM, 6>(y4) + rnd<WM, 8>(y4) - rnd<WM, 11>(y4);
        uo = rne<WM, G>(x5);
        vo = rne<WM, G>(y5);
    }
};

}  // namespace dct8

#endif
