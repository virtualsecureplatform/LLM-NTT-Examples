#include <iostream>
#include <cstdlib>
#include "tfhepp_exact_product.hpp"
#include <mulfft.hpp>

int main() {
    llmntt::TorusPolynomial a{}, b{}, expected{}, transported{};
    std::cin >> std::hex;
    while (std::cin >> a[0]) {
        for (std::size_t i=1; i<a.size(); ++i)
            if (!(std::cin >> a[i])) return 2;
        for (auto& value : b) if (!(std::cin >> value)) return 2;
        TFHEpp::PolyMulNaive<TFHEpp::lvl1param>(expected, a, b);
        llmntt::multiply_exact(transported, a, b,
            [&](const auto& pa, const auto& pb, auto& result) {
                if (pa != llmntt::pack(a) || pb != llmntt::pack(b)) std::exit(3);
                result = llmntt::pack(expected);
            });
        if (transported != expected) return 4;
        for (const auto value : expected) std::cout << std::hex << value << '\n';
    }
    return std::cin.eof() ? 0 : 2;
}
