#include "seal/seal.h"
#include "seal/util/ntt.h"
#include <iostream>
int main() {
    auto primes = seal::CoeffModulus::Create(8192, {60,40,40,60});
    std::cout << "[";
    for (std::size_t i=0; i<primes.size(); ++i) {
        seal::util::NTTTables table(13, primes[i]);
        if (i) std::cout << ",";
        std::cout << "{\"position\":" << i << ",\"q\":\"" << primes[i].value()
                  << "\",\"psi\":\"" << table.get_root() << "\",\"bits\":" << primes[i].bit_count()
                  << ",\"special_key_prime\":" << (i==3 ? "true" : "false") << "}";
    }
    std::cout << "]\n";
}
