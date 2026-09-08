"""Independent integer NTT oracle; no generator code or generated tables imported."""
from __future__ import annotations
import random


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        s, d = s + 1, d // 2
    # Deterministic Miller-Rabin bases for unsigned 64-bit integers.
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        x = pow(a % n, d, n)
        if a % n == 0 or x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def field(n: int, bits: int) -> dict:
    if n < 2 or n & (n - 1) or not 3 <= bits <= 64:
        raise ValueError("field requires power-of-two N and 3..64 bits")
    step = 2 * n
    q = ((1 << (bits - 1)) // step + 1) * step + 1
    while q < 1 << bits and not is_prime(q):
        q += step
    if q >= 1 << bits:
        raise ValueError("no prime in requested bit range")
    a = 2
    while True:
        psi = pow(a, (q - 1) // step, q)
        if pow(psi, n, q) == q - 1:
            return {"n": n, "q": str(q), "root": str(psi * psi % q), "psi": str(psi)}
        a += 1


def validate(workload: dict) -> None:
    n, q, root = int(workload['n']), int(workload['q']), int(workload['root'])
    if n < 2 or n & (n - 1) or q >= 1 << 64 or not is_prime(q):
        raise ValueError("expected power-of-two N and a prime below 2^64")
    if pow(root, n, q) != 1 or pow(root, n // 2, q) == 1:
        raise ValueError("root must have exact order N")
    if workload.get('negacyclic', False):
        psi = int(workload['psi'])
        if psi * psi % q != root % q or pow(psi, n, q) != q - 1:
            raise ValueError("psi must have order 2N and square to root")
    if workload.get('direction', 'forward') not in ('forward', 'inverse'):
        raise ValueError("direction must be forward or inverse")


def transform(values: list[int], workload: dict, direct: bool = False) -> list[int]:
    n, q, w = int(workload['n']), int(workload['q']), int(workload['root'])
    if len(values) != n:
        raise ValueError("input length differs from N")
    inverse = workload.get('direction', 'forward') == 'inverse'
    psi = int(workload['psi']) if workload.get('negacyclic', False) else 1
    a = [v % q for v in values]
    if inverse:
        w = pow(w, -1, q)
    else:
        a = [v * pow(psi, i, q) % q for i, v in enumerate(a)]
    if direct:
        a = [sum(v * pow(w, i * j, q) for j, v in enumerate(a)) % q for i in range(n)]
    else:
        j = 0
        for i in range(1, n):
            bit = n >> 1
            while j & bit:
                j ^= bit
                bit >>= 1
            j ^= bit
            if i < j:
                a[i], a[j] = a[j], a[i]
        length = 2
        while length <= n:
            omega = pow(w, n // length, q)
            for base in range(0, n, length):
                tw = 1
                for k in range(length // 2):
                    x, y = a[base + k], a[base + k + length // 2] * tw % q
                    a[base + k] = (x + y) % q
                    a[base + k + length // 2] = (x - y) % q
                    tw = tw * omega % q
            length *= 2
    if inverse:
        scale, untwist = pow(n, -1, q), pow(psi, -1, q)
        a = [v * scale * pow(untwist, i, q) % q for i, v in enumerate(a)]
    return a


def vectors(workload: dict, seed: int = 1) -> list[list[int]]:
    n, q = int(workload['n']), int(workload['q'])
    rng = random.Random(seed)
    return [[0] * n, [q - 1] * n, [1] + [0] * (n - 1),
            [i % q for i in range(n)], [q - 1 if i & 1 else 0 for i in range(n)],
            *[[rng.randrange(q) for _ in range(n)] for _ in range(3)]]
