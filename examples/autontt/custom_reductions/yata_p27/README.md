# YATA P27 Custom Reduction Notes

YATA uses:

```text
P = 40960001 = 5^4 * 2^16 + 1
```

The extracted YATA task is valuable for LLM RTL-generation and architecture
search, but it is not a direct AutoNTT input for two reasons:

- the task uses `N = 512`, while AutoNTT's documented range starts at `N = 1024`;
- the RTL uses signed 27-bit compressed RAINTT arithmetic rather than the
  unsigned HLS modular-multiplication interface expected by AutoNTT examples.

For an AutoNTT extension, the useful implementation direction is to model the
YATA/TFHEpp RAINTT reduction logic from `third_party/TFHEpp/include/raintt.hpp`:

```text
K = 625
shiftamount = 16
P = (K << shiftamount) + 1
wordbits = 27
```

The relevant TFHEpp operations are `REDC`, `SREDC`, `MulREDC`, and `MulSREDC`.
A search agent should treat this as a signed modular-reduction problem, not as a
generic 27-bit Barrett-reduction task.
