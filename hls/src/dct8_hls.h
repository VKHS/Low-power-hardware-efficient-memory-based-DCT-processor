// ============================================================================
// dct8_hls.h -- Vitis HLS model of the low-power memory-based DCT processor
// ----------------------------------------------------------------------------
// Three synthesizable kernels (top functions in dct8_top.cpp):
//
//   dct8_block_top  idiomatic HLS: the 17-operation radix-2 flow graph per
//                   block (12 butterflies + 5 rotations) with ALLOCATION
//                   limit=2 on the butterfly datapath and limit=1 on the
//                   central CORDIC unit, block loop pipelined at II = 8
//                   (one sample per clock).
//   dct8_cycle_top  the RTL micro-architecture in C++: phase counter, input
//                   buffer, butterfly buffers M_B, memory bank, output buffer
//                   and the two-stage CORDIC pipeline, driven by the same
//                   generated microcode as rtl/dct8_ctrl.v; one loop
//                   iteration = one clock (II = 1), cycle-exact with the RTL.
//   dct2d_top       8x8 2-D DCT: row pass -> single-buffer transpose ->
//                   column pass -> final scaling, as a DATAFLOW region.
//
// All kernels are bit-exact with python/dct8 and rtl/.
// ============================================================================
#ifndef DCT8_HLS_H
#define DCT8_HLS_H

#include "ap_int.h"
#include "hls_stream.h"
#include "dct8_arith.h"
#include "dct8_sched.h"

// ------------------------------------------------------- default configuration
#ifndef DCT_B_IN
#define DCT_B_IN 8        // input word length
#endif
#ifndef DCT_W
#define DCT_W 14          // internal word length (WL)
#endif
#ifndef DCT_G
#define DCT_G 3           // CORDIC guard bits (radius scale-up)
#endif
#ifndef DCT_SS1
#define DCT_SS1 0         // safe scaling after butterfly stage 1 / 2 / 3
#endif
#ifndef DCT_SS2
#define DCT_SS2 0
#endif
#ifndef DCT_SS3
#define DCT_SS3 0
#endif
#ifndef DCT_MR_MODE
#define DCT_MR_MODE 0     // 0: Table 1 micro-rotations, 1: extended CORDIC-II
#endif
// 2-D processor: row pass = (B_IN, W_ROW, ...), column pass = (W_ROW, W_COL, ...)
#ifndef DCT2D_W_ROW
#define DCT2D_W_ROW 14
#endif
#ifndef DCT2D_G_ROW
#define DCT2D_G_ROW 3
#endif
#ifndef DCT2D_SS_ROW
#define DCT2D_SS_ROW 0, 0, 0
#endif
#ifndef DCT2D_W_COL
#define DCT2D_W_COL 16
#endif
#ifndef DCT2D_G_COL
#define DCT2D_G_COL 3
#endif
#ifndef DCT2D_SS_COL
#define DCT2D_SS_COL 1, 1, 1
#endif
#ifndef DCT2D_OUT_W
#define DCT2D_OUT_W 12
#endif
#ifndef DCT2D_OUT_FRAC
#define DCT2D_OUT_FRAC 0
#endif

namespace dct8 {

// Static description of one 1-D processor configuration
template <int B_IN, int W, int G, int SS1, int SS2, int SS3, int MODE>
struct Cfg {
    static const int b_in = B_IN, w = W, g = G, mode = MODE;
    static const int ss1 = SS1, ss2 = SS2, ss3 = SS3;
    static const int H = 3 - SS1 - SS2 - SS3;   // headroom bits
    static const int F = W - B_IN - H;          // input fractional bits
    static const int E = F - SS1 - SS2 - SS3;   // output: Y = 2 sqrt(2) X 2^E
    typedef ap_int<B_IN> in_t;
    typedef ap_int<W> data_t;
    typedef MR<W, G, MODE> mr_t;
    static bool scale(const int stage) {
#pragma HLS INLINE
        return (stage == 1) ? (SS1 != 0) : ((stage == 2) ? (SS2 != 0) : (SS3 != 0));
    }
};

// ---------------------------------------------------- block-level processing elements
template <class C>
void bf_pe(typename C::data_t a, typename C::data_t b, int stage,
           typename C::data_t& s, typename C::data_t& d) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    bf_core<C::w>(a, b, C::scale(stage), s, d);
}

template <class C>
void mr_pe(typename C::data_t u, typename C::data_t v, int k,
           typename C::data_t& uo, typename C::data_t& vo) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
    typename C::mr_t::wm_t xa, ya;
    C::mr_t::stage_a(u, v, k, xa, ya);
    C::mr_t::stage_b(xa, ya, k, uo, vo);
}

// One 8-point block through the radix-2 flow graph (python/dct8/flowgraph.py).
// A rotation by -theta is a counter-clockwise rotation of swapped operands.
template <class C>
void dct8_block(const typename C::in_t x[8], typename C::data_t y[8]) {
#pragma HLS INLINE
#pragma HLS ALLOCATION function instances=bf_pe<C> limit=2
#pragma HLS ALLOCATION function instances=mr_pe<C> limit=1
    typedef typename C::data_t D;
    D xi[8];
    for (int n = 0; n < 8; n++) {
#pragma HLS UNROLL
        D t = x[n];
        xi[n] = t << C::F;
    }
    D L0, H0, L1, H1, L2, H2, L3, H3;
    D LL0, LH0, LL1, LH1, HH0, HL0, HH1, HL1;
    D Dd, Sp, Dp, DB, SBp, DBp, A3, A1, B3, B1;
    bf_pe<C>(xi[0], xi[1], 1, L0, H0);       // S0  stage 1: x_L, x_H
    bf_pe<C>(xi[2], xi[3], 1, L1, H1);       // S1
    bf_pe<C>(xi[4], xi[5], 1, L2, H2);       // S2
    bf_pe<C>(xi[6], xi[7], 1, L3, H3);       // S3
    bf_pe<C>(L0, L1, 2, LL0, LH0);           // T0  stage 2
    bf_pe<C>(L2, L3, 2, LL1, LH1);           // T1
    bf_pe<C>(H0, H1, 2, HH0, HL0);           // T2
    bf_pe<C>(H2, H3, 2, HH1, HL1);           // T3
    bf_pe<C>(LL0, LL1, 3, y[0], Dd);         // U0  stage 3: 2-point DCTs
    bf_pe<C>(LH0, LH1, 3, Sp, Dp);           // U1
    bf_pe<C>(HL0, HL1, 3, y[4], DB);         // U2
    bf_pe<C>(HH0, HH1, 3, SBp, DBp);         // U3
    mr_pe<C>(Sp, Dd, 2, A3, A1);             // V0  -pi/8
    mr_pe<C>(SBp, DB, 2, B3, B1);            // V1  -pi/8
    mr_pe<C>(B3, A1, 1, y[7], y[1]);         // W1  -pi/16
    mr_pe<C>(DBp, Dp, 2, y[6], y[2]);        // W2  -2pi/16
    mr_pe<C>(B1, A3, 3, y[5], y[3]);         // W3  -3pi/16
}

// Block-level streaming kernel: in-order samples in, in-order coefficients out.
template <class C>
void dct8_block_stream(hls::stream<typename C::in_t>& in,
                       hls::stream<typename C::data_t>& out, int n_blocks) {
    for (int b = 0; b < n_blocks; b++) {
#pragma HLS PIPELINE II=8
        typename C::in_t x[8];
        typename C::data_t y[8];
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=y complete
        for (int n = 0; n < 8; n++) x[n] = in.read();
        dct8_block<C>(x, y);
        for (int k = 0; k < 8; k++) out.write(y[k]);
    }
}

// ------------------------------------------------------------ cycle-level kernel
// Input word  : {in_valid, in_data[B_IN-1:0]}, one per clock.
// Output word : {out_valid, out_last, out_index[2:0], out_data[W-1:0]}, one per
//               clock -- the registered outputs of rtl/dct8_core.v after the edge.
// reset = true clears the state first (synchronous reset of the RTL).
template <class C>
void dct8_cycle_stream(hls::stream<ap_uint<C::b_in + 1> >& in,
                       hls::stream<ap_uint<C::w + 5> >& out, int n_cycles, bool reset) {
    typedef typename C::data_t D;
    typedef typename C::mr_t::wm_t WM;
    typedef ap_uint<C::w + 5> word_t;
    static D ib;
    static D bm[SCHED_BM_WORDS];
    static D mm[SCHED_MM_WORDS];
    static D ob[SCHED_OB_WORDS];
#pragma HLS ARRAY_PARTITION variable=bm complete
#pragma HLS ARRAY_PARTITION variable=mm complete
#pragma HLS ARRAY_PARTITION variable=ob complete
    static WM xr, yr;
    static int kr;
    static ap_uint<3> phase;
    static ap_uint<SCHED_OUT_BLOCK + 1> tags;
    static bool out_tag;
    if (reset) {
        ib = 0;
        for (int i = 0; i < SCHED_BM_WORDS; i++) bm[i] = 0;
        for (int i = 0; i < SCHED_MM_WORDS; i++) mm[i] = 0;
        for (int i = 0; i < SCHED_OB_WORDS; i++) ob[i] = 0;
        xr = 0; yr = 0; kr = 1; phase = 0; tags = 0; out_tag = false;
    }

    for (int t = 0; t < n_cycles; t++) {
#pragma HLS PIPELINE II=1
        ap_uint<C::b_in + 1> w_in = in.read();
        const bool in_valid = w_in[C::b_in];
        ap_uint<C::b_in> raw = w_in;             // drop the valid bit
        typename C::in_t xs = raw;               // reinterpret as signed
        D x_in = xs;
        x_in = x_in << C::F;
        const int p = phase;

        // butterfly unit: BF0 (with the input bypass) and BF1
        D a0 = BF0_A_IB[p] ? ib : bm[BF0_A_ADDR[p]];
        D b0 = BF0_B_IN[p] ? x_in : bm[BF0_B_ADDR[p]];
        D s0, d0, s1, d1;
        bf_core<C::w>(a0, b0, C::scale(BF0_STAGE[p]), s0, d0);
        bf_core<C::w>(bm[BF1_A_ADDR[p]], bm[BF1_B_ADDR[p]], C::scale(BF1_STAGE[p]), s1, d1);

        // central CORDIC unit: stage B of the rotation issued last clock, stage A of a new one
        D uo, vo;
        C::mr_t::stage_b(xr, yr, kr, uo, vo);
        WM xa, ya;
        C::mr_t::stage_a(mm[MR_A_ADDR[p]], mm[MR_B_ADDR[p]], MR_K[p], xa, ya);

        // output register (reads before this clock's writes)
        D y_out = ob[OB_RADDR[p]];
        const bool out_start = (p == SCHED_OUT_PHASE);
        const bool tag_now = out_start ? (bool)tags[SCHED_OUT_BLOCK] : out_tag;
        ap_uint<C::w> data = y_out;
        word_t w_out = data;
        word_t k_bits = OUT_K[p];
        w_out = w_out | (k_bits << C::w);
        if (OUT_K[p] == 7) w_out = w_out | (word_t(1) << (C::w + 3));
        if (tag_now) w_out = w_out | (word_t(1) << (C::w + 4));
        out.write(w_out);

        // clock edge: commit all writes (fixed wiring, enabled by the decoders)
        if (IB_WE[p]) ib = x_in;
        if (BF0_EN[p]) {
            if (BF0_SUM_BANK[p] == BANK_BM) bm[BF0_SUM_ADDR[p]] = s0;
            else if (BF0_SUM_BANK[p] == BANK_MM) mm[BF0_SUM_ADDR[p]] = s0;
            else ob[BF0_SUM_ADDR[p]] = s0;
            if (BF0_DIFF_BANK[p] == BANK_BM) bm[BF0_DIFF_ADDR[p]] = d0;
            else if (BF0_DIFF_BANK[p] == BANK_MM) mm[BF0_DIFF_ADDR[p]] = d0;
            else ob[BF0_DIFF_ADDR[p]] = d0;
        }
        if (BF1_EN[p]) {
            if (BF1_SUM_BANK[p] == BANK_BM) bm[BF1_SUM_ADDR[p]] = s1;
            else if (BF1_SUM_BANK[p] == BANK_MM) mm[BF1_SUM_ADDR[p]] = s1;
            else ob[BF1_SUM_ADDR[p]] = s1;
            if (BF1_DIFF_BANK[p] == BANK_BM) bm[BF1_DIFF_ADDR[p]] = d1;
            else if (BF1_DIFF_BANK[p] == BANK_MM) mm[BF1_DIFF_ADDR[p]] = d1;
            else ob[BF1_DIFF_ADDR[p]] = d1;
        }
        if (MR_DONE[p]) {
            if (MR_DST_OB[p]) { ob[MR_U_ADDR[p]] = uo; ob[MR_V_ADDR[p]] = vo; }
            else              { mm[MR_U_ADDR[p]] = uo; mm[MR_V_ADDR[p]] = vo; }
        }
        if (MR_ISSUE[p]) { xr = xa; yr = ya; kr = MR_K[p]; }
        if (out_start) out_tag = tag_now;
        if (p == 0) tags = (tags << 1) | ap_uint<SCHED_OUT_BLOCK + 1>(in_valid ? 1 : 0);
        phase = phase + 1;
    }
}

// ------------------------------------------------------------------ 2-D kernel
typedef Cfg<DCT_B_IN, DCT2D_W_ROW, DCT2D_G_ROW, DCT2D_SS_ROW, DCT_MR_MODE> RowCfg2D;
typedef Cfg<DCT2D_W_ROW, DCT2D_W_COL, DCT2D_G_COL, DCT2D_SS_COL, DCT_MR_MODE> ColCfg2D;
static const int OUT_SHIFT_2D = RowCfg2D::E + ColCfg2D::E + 3 - DCT2D_OUT_FRAC;
typedef ap_int<DCT2D_OUT_W> out2d_t;

// final scaling: round half to even by S bits (S >= 1) or exact left shift by -S
template <int W, int S, bool RIGHT = (S >= 1)>
struct ShiftRound;
template <int W, int S>
struct ShiftRound<W, S, true> {
    static ap_int<W> apply(const ap_int<W> z) { return rne<W, S>(z); }
};
template <int W, int S>
struct ShiftRound<W, S, false> {
    static ap_int<W> apply(const ap_int<W> z) { return z << (-S); }
};

void dct2d_row_pass(hls::stream<RowCfg2D::in_t>& in, hls::stream<RowCfg2D::data_t>& mid,
                    int n_blocks);
void dct2d_transpose(hls::stream<RowCfg2D::data_t>& mid, hls::stream<ColCfg2D::in_t>& tr,
                     int n_blocks);
void dct2d_col_pass(hls::stream<ColCfg2D::in_t>& tr, hls::stream<out2d_t>& out, int n_blocks);

}  // namespace dct8

// ------------------------------------------------------------------ synthesis tops
typedef dct8::Cfg<DCT_B_IN, DCT_W, DCT_G, DCT_SS1, DCT_SS2, DCT_SS3, DCT_MR_MODE> DefaultCfg;

void dct8_block_top(hls::stream<DefaultCfg::in_t>& in, hls::stream<DefaultCfg::data_t>& out,
                    int n_blocks);
void dct8_cycle_top(hls::stream<ap_uint<DCT_B_IN + 1> >& in,
                    hls::stream<ap_uint<DCT_W + 5> >& out, int n_cycles, bool reset);
void dct2d_top(hls::stream<dct8::RowCfg2D::in_t>& in, hls::stream<dct8::out2d_t>& out,
               int n_blocks);

#endif
