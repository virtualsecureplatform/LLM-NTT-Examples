# Matched routed N=256 comparison

All three implementations pass functional verification and routed setup/hold
checks under `campaigns/threeway256-two-buffer-fabric.json`. This is one workload
and interface comparison, not a claim of general superiority or board performance.

The workload is a forward negacyclic NTT with N=256, q=2147484161,
psi=1421553366, root=2141337746, and four external coefficient lanes. The target
is xcu280-fsvh2892-2L-e, Vivado 2023.2, 4 ns. The shared fabric timing contract
uses BUFGCE_X0Y0 and the boundary input register clock as its I/O reference,
input delays 0.5–1 ns and output delays 0–1 ns. Two preserved identity LUTs
per output bit are inserted before placement; their cost is included below.
See [the complete contract](fabric-timing-contract.md).

| Implementation | LUT | FF | DSP | BRAM tiles | WNS ns | WHS ns | Latency cycles | Frame interval cycles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NGen, PE=2, one stage group, seven-stage Montgomery | 4889 | 1742 | 22 | 4 | 0.238 | 0.001 | 791 | 852 |
| OpenNTT, PE=2, RoutOpt | 10193 | 11142 | 32 | 3 | 0.791 | 0.010 | 1132 | 1194 |
| Modified Proteus, MDC | 17366 | 21750 | 64 | 0 | 0.407 | 0.010 | 740 | 802 |

All use zero URAM. At the timing-qualified 250 MHz target, normalized frame
rates computed from measured RTL frame intervals are 293427, 209380, and
311721 transforms/s respectively. These are interface-level RTL rates, not
measured host, PCIe, or board throughput.

NGen provides 1.4014 times OpenNTT's normalized frame rate with 52.0% fewer
LUTs, 84.4% fewer FFs, and 31.25% fewer DSPs, at the cost of one additional
BRAM tile. Proteus is 6.2% faster than NGen by frame rate; NGen uses 71.8%
fewer LUTs and 65.6% fewer DSPs, but four additional BRAM tiles. All three
remain on the resource/latency/throughput Pareto frontier. NGen does not
dominate either baseline across every resource dimension.

The normalized adapters include buffering and order conversion. OpenNTT's
upstream scalar host-memory port serializes coefficient transfers; its adapter
cost and transfer cycles are included. Proteus uses the explicitly modified
portable MDC tree with the [recorded inverse-ROM repair](proteus-inverse-repair.md).
This forward measurement does not establish the performance of an unmodified
upstream Proteus release. Independent oracle vectors, saturation, stalls, and
reset checks qualify each stream before hardware measurement.

The artifact is `build/comparison-threeway256-two-buffer`. Its manifest and
candidate records retain source, verification, measurement report, and target
identities. Reconstruct the report from the measured artifacts with:

```sh
python3 scripts/compare_openntt_ngen.py \
  --campaign campaigns/threeway256-two-buffer-fabric.json \
  --ngen-report build/ngen256-two-buffer-fabric/report.json \
  --openntt-dirs build/openntt-256-32 \
  --proteus-dirs build/proteus-mdc-forward256-portable \
  --measured-records build/openntt256-two-buffer-fabric/record.json \
                     build/proteus256-two-buffer-fabric/record.json \
  --output-dir build/comparison-threeway256-two-buffer
```

The output directory must be empty. The importer rejects changed verification
or measurement artifacts and mismatched targets. Older one-buffer hold failures
remain failed evidence. Two buffers do not guarantee closure: placement changed
NGen's minimum hold margin to only 0.001 ns. Wider workloads, alternative core
configurations, and additional placement runs remain necessary to establish a
robust generator-level advantage.
