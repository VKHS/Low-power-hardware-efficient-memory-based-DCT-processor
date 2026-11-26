// ============================================================================
// hls_stream.h -- minimal stand-in for hls::stream, for C simulation only.
// ============================================================================
#ifndef DCT8_CSIM_HLS_STREAM_H
#define DCT8_CSIM_HLS_STREAM_H

#include <cstdio>
#include <cstdlib>
#include <deque>

namespace hls {
template <typename T>
class stream {
  public:
    stream() {}
    explicit stream(const char*) {}
    T read() {
        if (q_.empty()) {
            std::fprintf(stderr, "hls::stream read from an empty stream\n");
            std::exit(2);
        }
        T v = q_.front();
        q_.pop_front();
        return v;
    }
    void read(T& v) { v = read(); }
    void write(const T& v) { q_.push_back(v); }
    bool empty() const { return q_.empty(); }
    size_t size() const { return q_.size(); }

  private:
    std::deque<T> q_;
};
}  // namespace hls

#endif
