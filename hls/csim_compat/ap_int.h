// ============================================================================
// ap_int.h -- minimal stand-in for the Vitis HLS arbitrary-precision types,
// used ONLY for C simulation with a plain C++ compiler (make -C hls csim).
// ----------------------------------------------------------------------------
// Supports exactly the subset used by hls/src (signed/unsigned words up to 62
// bits): construction and assignment wrap to W bits, arithmetic is carried out
// at 64 bits and wraps on assignment, shifts keep the operand width (as in
// Vitis), bit select z[i], and range(hi, lo).  Vitis HLS uses its own ap_int.h;
// CI additionally compiles the C simulation against the official open-source
// headers (github.com/Xilinx/HLS_arbitrary_Precision_Types).
// ============================================================================
#ifndef DCT8_CSIM_AP_INT_H
#define DCT8_CSIM_AP_INT_H

#include <cstdint>

template <int W, bool S>
struct ap_word {
    static_assert(W >= 1 && W <= 62, "csim ap_int supports 1..62 bits");
    int64_t v;

    static int64_t norm(int64_t x) {
        const uint64_t m = (W == 64) ? ~0ull : ((1ull << W) - 1);
        uint64_t u = static_cast<uint64_t>(x) & m;
        if (S && (u >> (W - 1)) & 1ull) u |= ~m;
        return static_cast<int64_t>(u);
    }
    ap_word() : v(0) {}
    ap_word(long long x) : v(norm(x)) {}
    ap_word(int x) : v(norm(x)) {}
    ap_word(unsigned x) : v(norm(static_cast<int64_t>(x))) {}
    ap_word(unsigned long long x) : v(norm(static_cast<int64_t>(x))) {}
    ap_word(long x) : v(norm(x)) {}
    ap_word(bool x) : v(x ? 1 : 0) {}
    template <int W2, bool S2>
    ap_word(const ap_word<W2, S2>& o) : v(norm(o.v)) {}

    operator long long() const { return v; }

    bool operator[](int i) const { return (static_cast<uint64_t>(v) >> i) & 1ull; }
    ap_word<62, false> range(int hi, int lo) const {
        const uint64_t m = (hi - lo + 1 >= 64) ? ~0ull : ((1ull << (hi - lo + 1)) - 1);
        return ap_word<62, false>(static_cast<long long>((static_cast<uint64_t>(v) >> lo) & m));
    }
    void set_range(int hi, int lo, long long x) {
        const uint64_t m = ((1ull << (hi - lo + 1)) - 1) << lo;
        uint64_t u = (static_cast<uint64_t>(v) & ~m) | ((static_cast<uint64_t>(x) << lo) & m);
        v = norm(static_cast<int64_t>(u));
    }
    void set_bit(int i, bool b) {
        uint64_t u = static_cast<uint64_t>(v);
        u = b ? (u | (1ull << i)) : (u & ~(1ull << i));
        v = norm(static_cast<int64_t>(u));
    }
    ap_word operator<<(int s) const { return ap_word(static_cast<long long>(static_cast<uint64_t>(v) << s)); }
    ap_word operator>>(int s) const {
        if (S) return ap_word(static_cast<long long>(v >> s));
        return ap_word(static_cast<long long>(static_cast<uint64_t>(v) >> s));
    }
    ap_word& operator+=(long long x) { v = norm(v + x); return *this; }
    ap_word& operator-=(long long x) { v = norm(v - x); return *this; }
    ap_word& operator++() { v = norm(v + 1); return *this; }
    ap_word operator++(int) { ap_word t = *this; v = norm(v + 1); return t; }
};

template <int W> using ap_int = ap_word<W, true>;
template <int W> using ap_uint = ap_word<W, false>;

#endif
