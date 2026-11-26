// ============================================================================
// tb_common.h -- helpers shared by the C-simulation test benches
// ============================================================================
#ifndef DCT8_TB_COMMON_H
#define DCT8_TB_COMMON_H

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace tb {

inline std::vector<std::vector<long long> > read_txt(const std::string& path) {
    std::ifstream f(path.c_str());
    if (!f) {
        std::fprintf(stderr, "cannot open %s\n", path.c_str());
        std::exit(2);
    }
    std::vector<std::vector<long long> > rows;
    std::string line;
    while (std::getline(f, line)) {
        std::istringstream is(line);
        std::vector<long long> r;
        long long v;
        while (is >> v) r.push_back(v);
        if (!r.empty()) rows.push_back(r);
    }
    return rows;
}

// hex words of `width` bits; sign-extended if `is_signed`
inline std::vector<long long> read_hex(const std::string& path, int width, bool is_signed) {
    std::ifstream f(path.c_str());
    if (!f) {
        std::fprintf(stderr, "cannot open %s\n", path.c_str());
        std::exit(2);
    }
    std::vector<long long> out;
    std::string tok;
    while (f >> tok) {
        unsigned long long u = std::strtoull(tok.c_str(), 0, 16);
        long long v = static_cast<long long>(u);
        if (is_signed && ((u >> (width - 1)) & 1ull)) v -= (1ll << width);
        out.push_back(v);
    }
    return out;
}

inline long long sext(unsigned long long u, int width) {
    u &= (width >= 64) ? ~0ull : ((1ull << width) - 1);
    long long v = static_cast<long long>(u);
    if ((u >> (width - 1)) & 1ull) v -= (1ll << width);
    return v;
}

}  // namespace tb

#endif
