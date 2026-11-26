// ============================================================================
// tb_dct2d.cpp -- C-simulation test bench of the 2-D DATAFLOW kernel
// ----------------------------------------------------------------------------
//   tb_dct2d <vectors-dir> <name>       e.g.  tb_dct2d vectors dct2d_t1
// Streams the blocks of <name>_in.txt (row-major pixels) through dct2d_top and
// compares the column-major coefficient stream with <name>_expect.hex.
// ============================================================================
#include <cstdio>
#include <string>
#include <vector>

#include "dct8_hls.h"
#include "tb_common.h"

int main(int argc, char** argv) {
    const std::string dir = argc > 1 ? argv[1] : "vectors";
    const std::string name = argc > 2 ? argv[2] : "dct2d_t1";
    const std::string base = dir + "/" + name;
    std::vector<std::vector<long long> > blocks = tb::read_txt(base + "_in.txt");
    std::vector<long long> expect = tb::read_hex(base + "_expect.hex", DCT2D_OUT_W, true);

    hls::stream<dct8::RowCfg2D::in_t> s_in("in");
    hls::stream<dct8::out2d_t> s_out("out");
    for (size_t b = 0; b < blocks.size(); b++)
        for (int i = 0; i < 64; i++) s_in.write(dct8::RowCfg2D::in_t(blocks[b][i]));
    dct2d_top(s_in, s_out, static_cast<int>(blocks.size()));

    int errors = 0;
    for (size_t n = 0; n < expect.size(); n++) {
        long long got = s_out.read();
        if (got != expect[n]) {
            if (errors < 5)
                std::printf("mismatch #%zu (block %zu, u=%zu v=%zu): got %lld expected %lld\n", n, n / 64,
                            n % 8, (n / 8) % 8, got, expect[n]);
            errors++;
        }
    }
    if (!s_out.empty()) {
        std::printf("extra outputs\n");
        errors++;
    }
    if (errors == 0)
        std::printf("PASS: %s  %zu blocks, %zu coefficients bit-exact (OUT_SHIFT %d)\n", name.c_str(),
                    blocks.size(), expect.size(), dct8::OUT_SHIFT_2D);
    else
        std::printf("FAIL: %s  %d errors\n", name.c_str(), errors);
    return errors == 0 ? 0 : 1;
}
