// ============================================================================
// tb_dct8.cpp -- C-simulation test bench of the 1-D kernels
// ----------------------------------------------------------------------------
//   tb_dct8 <vectors-dir> <name>        e.g.  tb_dct8 vectors dct8_t1_w14
// The configuration macros (DCT_B_IN, DCT_W, DCT_G, DCT_SS1..3, DCT_MR_MODE)
// must match vectors/manifest.json (scripts/run_hls_csim.py passes them).
// Checks
//   1. dct8_block_top against <name>_in.txt / <name>_out.txt
//   2. dct8_cycle_top clock by clock against <name>_stim.hex / <name>_expect.hex:
//      data, index, last flag and the latency of the first coefficient.
// ============================================================================
#include <cstdio>
#include <string>
#include <vector>

#include "dct8_hls.h"
#include "tb_common.h"

#ifndef DCT_FIRST_OUT
#define DCT_FIRST_OUT 16
#endif

int main(int argc, char** argv) {
    const std::string dir = argc > 1 ? argv[1] : "vectors";
    const std::string name = argc > 2 ? argv[2] : "dct8_t1_w14";
    const std::string base = dir + "/" + name;
    const int W = DCT_W, B = DCT_B_IN;
    int errors = 0;

    // ---------------------------------------------------------------- block kernel
    std::vector<std::vector<long long> > xin = tb::read_txt(base + "_in.txt");
    std::vector<std::vector<long long> > yexp = tb::read_txt(base + "_out.txt");
    hls::stream<DefaultCfg::in_t> s_in("in");
    hls::stream<DefaultCfg::data_t> s_out("out");
    for (size_t b = 0; b < xin.size(); b++)
        for (int n = 0; n < 8; n++) s_in.write(DefaultCfg::in_t(xin[b][n]));
    dct8_block_top(s_in, s_out, static_cast<int>(xin.size()));
    int blk_err = 0;
    for (size_t b = 0; b < xin.size(); b++)
        for (int k = 0; k < 8; k++) {
            long long got = s_out.read();
            if (got != yexp[b][k]) {
                if (blk_err < 5)
                    std::printf("block kernel mismatch: block %zu Y%d got %lld expected %lld\n", b, k,
                                got, yexp[b][k]);
                blk_err++;
            }
        }
    errors += blk_err;

    // ---------------------------------------------------------------- cycle kernel
    std::vector<long long> stim = tb::read_hex(base + "_stim.hex", B + 1, false);
    std::vector<long long> expect = tb::read_hex(base + "_expect.hex", W, true);
    hls::stream<ap_uint<DCT_B_IN + 1> > c_in("c_in");
    hls::stream<ap_uint<DCT_W + 5> > c_out("c_out");
    for (size_t t = 0; t < stim.size(); t++) c_in.write(ap_uint<DCT_B_IN + 1>(stim[t]));
    dct8_cycle_top(c_in, c_out, static_cast<int>(stim.size()), true);
    size_t n = 0;
    int first = -1, cyc_err = 0;
    for (size_t t = 0; t < stim.size(); t++) {
        unsigned long long w = static_cast<unsigned long long>(static_cast<long long>(c_out.read()));
        bool valid = (w >> (W + 4)) & 1ull, last = (w >> (W + 3)) & 1ull;
        int idx = static_cast<int>((w >> W) & 7ull);
        long long data = tb::sext(w, W);
        if (!valid) continue;
        if (first < 0) first = static_cast<int>(t) + 1;
        if (n >= expect.size() || data != expect[n] || idx != static_cast<int>(n % 8) ||
            last != (idx == 7)) {
            if (cyc_err < 5)
                std::printf("cycle kernel mismatch #%zu (cycle %zu): got %lld idx %d, expected %lld\n", n,
                            t + 1, data, idx, n < expect.size() ? expect[n] : 0);
            cyc_err++;
        }
        n++;
    }
    if (n != expect.size()) {
        std::printf("cycle kernel: %zu outputs, expected %zu\n", n, expect.size());
        cyc_err++;
    }
    if (first != DCT_FIRST_OUT) {
        std::printf("cycle kernel: first output at cycle %d, expected %d\n", first, DCT_FIRST_OUT);
        cyc_err++;
    }
    errors += cyc_err;

    if (errors == 0)
        std::printf("PASS: %s  block kernel %zu blocks, cycle kernel %zu coefficients, latency %d\n",
                    name.c_str(), xin.size(), n, first);
    else
        std::printf("FAIL: %s  %d errors\n", name.c_str(), errors);
    return errors == 0 ? 0 : 1;
}
