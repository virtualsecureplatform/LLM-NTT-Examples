#pragma once

#include <array>
#include <cstdint>
#ifdef USE_CGGI19
// The pinned legacy parameter header omits these unused annihilation types,
// although params.hpp names them. Forward declarations allow this polynomial
// adapter to compile without inventing parameters or enabling those operations.
namespace TFHEpp { struct AHlvl1param; struct AHlvl2param; }
#endif
#include <params.hpp>

// Explicit application adapter: does not replace TFHEpp::PolyMul or change
// cryptographic parameters. The transport callback computes exactly one frame.
namespace llmntt {
using TorusPolynomial = TFHEpp::Polynomial<TFHEpp::lvl1param>;
static_assert(TFHEpp::lvl1param::n == 1024);
static_assert(sizeof(TFHEpp::lvl1param::T) == 4);
using PackedTorusPolynomial = std::array<std::uint64_t, 512>;

inline PackedTorusPolynomial pack(const TorusPolynomial& input) {
    PackedTorusPolynomial result{};
    for (std::size_t i = 0; i < result.size(); ++i)
        result[i] = std::uint64_t(input[2*i]) |
                    (std::uint64_t(input[2*i+1]) << 32);
    return result;
}

template<class Submit>
void multiply_exact(TorusPolynomial& output, const TorusPolynomial& a,
                    const TorusPolynomial& b, Submit&& submit) {
    const auto packed_a = pack(a), packed_b = pack(b);
    PackedTorusPolynomial result{};
    submit(packed_a, packed_b, result);
    for (std::size_t i = 0; i < result.size(); ++i) {
        output[2*i] = static_cast<std::uint32_t>(result[i]);
        output[2*i+1] = static_cast<std::uint32_t>(result[i] >> 32);
    }
}
}
