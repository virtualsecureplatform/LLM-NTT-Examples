// Instrumentation for the pinned Microsoft SEAL example; no arithmetic changes.
#pragma once
#include <cstdlib>
#include <fstream>
#include <set>
#include <string>
#include <stdexcept>
#include <vector>
namespace ntt_trace {
inline const char *&phase() { static const char *p = "setup"; return p; }
inline void set_phase(const char *p) { phase() = p; }
struct Capture {
    std::uint64_t *operand;
    std::size_t n;
    std::uint64_t q, psi;
    std::string direction, directory, key;
    std::vector<std::uint64_t> input;
    Capture(std::uint64_t *op, std::size_t size, std::uint64_t modulus,
            std::uint64_t root, const char *dir): operand(op), n(size), q(modulus), psi(root), direction(dir) {
        const char *base = std::getenv("NTT_TRACE_DIR");
        if (!base) return;
        directory = base;
        key = std::to_string(n) + "_" + std::to_string(q) + "_" + direction;
        static std::set<std::string> sampled;
        if (sampled.insert(key).second) input.assign(op, op + n);
        std::ofstream events(directory + "/events.jsonl", std::ios::app);
        if (!events) throw std::runtime_error("cannot write NTT trace");
        events << "{\"n\":" << n << ",\"q\":\"" << q << "\",\"psi\":\"" << psi
               << "\",\"direction\":\"" << direction << "\",\"phase\":\"" << phase() << "\"}\n";
    }
    ~Capture() {
        if (input.empty()) return;
        std::ofstream sample(directory + "/" + key + ".txt");
        if (!sample) std::abort();
        for (std::size_t i = 0; i < n; ++i) sample << input[i] << " " << operand[i] << "\n";
    }
};
}
