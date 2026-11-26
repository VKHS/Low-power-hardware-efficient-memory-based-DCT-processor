// ============================================================================
// dct8_top.cpp -- synthesis top functions (configuration: dct8_hls.h macros)
// ============================================================================
#include "dct8_hls.h"

void dct8_block_top(hls::stream<DefaultCfg::in_t>& in, hls::stream<DefaultCfg::data_t>& out,
                    int n_blocks) {
#pragma HLS INTERFACE axis port=in
#pragma HLS INTERFACE axis port=out
#pragma HLS INTERFACE s_axilite port=n_blocks
#pragma HLS INTERFACE s_axilite port=return
    dct8::dct8_block_stream<DefaultCfg>(in, out, n_blocks);
}

void dct8_cycle_top(hls::stream<ap_uint<DCT_B_IN + 1> >& in,
                    hls::stream<ap_uint<DCT_W + 5> >& out, int n_cycles, bool reset) {
#pragma HLS INTERFACE axis port=in
#pragma HLS INTERFACE axis port=out
#pragma HLS INTERFACE s_axilite port=n_cycles
#pragma HLS INTERFACE s_axilite port=reset
#pragma HLS INTERFACE s_axilite port=return
    dct8::dct8_cycle_stream<DefaultCfg>(in, out, n_cycles, reset);
}

namespace dct8 {

void dct2d_row_pass(hls::stream<RowCfg2D::in_t>& in, hls::stream<RowCfg2D::data_t>& mid,
                    int n_blocks) {
    dct8_block_stream<RowCfg2D>(in, mid, 8 * n_blocks);
}

// Single 64-word transpose buffer: every location is read (previous block,
// transposed order) and re-written (current block) in the same step; the
// address order alternates between row-major and column-major per block.
void dct2d_transpose(hls::stream<RowCfg2D::data_t>& mid, hls::stream<ColCfg2D::in_t>& tr,
                     int n_blocks) {
    static RowCfg2D::data_t buf[64];
    for (int f = 0; f <= n_blocks; f++) {
        for (int tau = 0; tau < 64; tau++) {
#pragma HLS PIPELINE II=1
            const int a = (f & 1) ? (8 * (tau & 7) + (tau >> 3)) : tau;
            RowCfg2D::data_t old = buf[a];
            if (f < n_blocks) buf[a] = mid.read();
            if (f > 0) tr.write(old);
        }
    }
}

void dct2d_col_pass(hls::stream<ColCfg2D::in_t>& tr, hls::stream<out2d_t>& out, int n_blocks) {
    const int WR = DCT2D_W_COL + DCT2D_OUT_W;
    for (int b = 0; b < 8 * n_blocks; b++) {
#pragma HLS PIPELINE II=8
        ColCfg2D::in_t x[8];
        ColCfg2D::data_t y[8];
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=y complete
        for (int n = 0; n < 8; n++) x[n] = tr.read();
        dct8_block<ColCfg2D>(x, y);
        for (int k = 0; k < 8; k++) {
            ap_int<WR> z = y[k];
            ap_int<WR> q = ShiftRound<WR, OUT_SHIFT_2D>::apply(z);
            out2d_t o = q;                            // wrap to OUT_W bits
            out.write(o);
        }
    }
}

}  // namespace dct8

void dct2d_top(hls::stream<dct8::RowCfg2D::in_t>& in, hls::stream<dct8::out2d_t>& out,
               int n_blocks) {
#pragma HLS INTERFACE axis port=in
#pragma HLS INTERFACE axis port=out
#pragma HLS INTERFACE s_axilite port=n_blocks
#pragma HLS INTERFACE s_axilite port=return
#pragma HLS DATAFLOW
    hls::stream<dct8::RowCfg2D::data_t> mid("mid");
    hls::stream<dct8::ColCfg2D::in_t> tr("tr");
#pragma HLS STREAM variable=mid depth=16
#pragma HLS STREAM variable=tr depth=16
    dct8::dct2d_row_pass(in, mid, n_blocks);
    dct8::dct2d_transpose(mid, tr, n_blocks);
    dct8::dct2d_col_pass(tr, out, n_blocks);
}
