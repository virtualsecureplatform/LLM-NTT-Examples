# Apptainer

Build the default image:

```bash
scripts/build_llm_ntt_sif.sh
```

Run the native build and tests inside the image:

```bash
apptainer run --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif
```

The `%runscript` expects the repository to be mounted at `/work`. The build
wrapper uses single-threaded squashfs by default to avoid `mksquashfs` orderer
failures seen on some unprivileged Apptainer hosts.

## Rootless And Sudo Builds

When rootless Apptainer works:

```bash
scripts/build_llm_ntt_sif.sh --output llm-ntt-rootless.sif
```

If the host cannot use unprivileged Apptainer builds:

```bash
scripts/build_llm_ntt_sif.sh --sudo
```

With `--sudo`, the wrapper stages the SIF under `SIF_TMPDIR`, `TMPDIR`, or
`/tmp`, changes ownership back to the caller, then moves it to `--output`.
Use `--sudo-temp-dir DIR` if `/tmp` is not suitable.

## Vitis Binding

Vitis is not copied into the image. It remains a host-side licensed tool.

Use `--bind-xilinx` only when a build-time `%post` step needs the host Xilinx
tree. The bind is read-only. At run time, bind the same host path explicitly:

```bash
apptainer exec --no-home --pwd /work \
  --bind "$(pwd):/work" \
  --bind /home/opt/xilinx:/home/opt/xilinx \
  llm-ntt.sif \
  scripts/check_autontt_hls_deps.sh
```

## TAPA Runtime

The base image installs the non-Xilinx packages needed by the HLS path,
including `libgflags-dev`, `libgoogle-glog-dev`, OpenCL headers/libraries,
Boost coroutine/context/thread/stacktrace, nlohmann-json, tinyxml2, yaml-cpp,
and the Python TAPA frontend.

The full RapidStream TAPA/Pasta C++ runtime is optional:

```bash
scripts/build_llm_ntt_sif.sh \
  --with-tapa-runtime \
  --tapa-build-jobs 4 \
  --output llm-ntt-rootless.sif
```

This downloads Bazelisk, uses Bazel `8.4.2`, clones `rapidstream-tapa`, patches
its Vitis path to `/home/opt/xilinx` version `2023.2`, builds
`//:tapa-pkg-tar`, and installs `tapacc`, `tapa.h`, `libtapa`, and `libfrt`
under `/opt/rapidstream-tapa` in the SIF.

For sudo builds with the TAPA runtime:

```bash
scripts/build_llm_ntt_sif.sh \
  --sudo \
  --with-tapa-runtime \
  --tapa-build-jobs 2
```

Use `--tapa-bazel-version VERSION` if the selected TAPA branch requires a
different Bazel release.

## Checks

Image-only check:

```bash
apptainer exec --no-home --pwd /work --bind "$(pwd):/work" llm-ntt.sif \
  scripts/check_autontt_hls_deps.sh --image-only
```

Full HLS dependency check with host Vitis bound:

```bash
apptainer exec --no-home --pwd /work \
  --bind "$(pwd):/work" \
  --bind /home/opt/xilinx:/home/opt/xilinx \
  llm-ntt-rootless.sif \
  scripts/check_autontt_hls_deps.sh
```
