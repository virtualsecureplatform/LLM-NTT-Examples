# Notices

This repository contains extracted NTT RTL variants from the following upstream
projects:

- `variants/yata-raintt`: extracted from `virtualsecureplatform/YATA`,
  `YATA/YATA-RTL`, commit `85ce5077133a7c12a2285d1bb201f4fb5e4962b0`.
- `variants/hoge`: extracted from `virtualsecureplatform/HOGE`, commit
  `06b3f12d5bdbd81007048b708cd69e6ec7f14526`, and consolidated into one
  namespaced Chisel project for the HOGE benchmark tops.
- `variants/kyber-polmul-hw`: copied from the local `kyber-polmul-hw` PE1
  CRYSTALS-Kyber polynomial multiplication reference.

The extracted YATA and HOGE RTL is licensed under AGPL-3.0; copies of the
source licenses are in `licenses/`. The existing repository license is retained
for original material that is not derived from those upstream projects.

The copied `kyber-polmul-hw` source file headers dedicate that RTL to the
public domain via CC0: <http://creativecommons.org/publicdomain/zero/1.0/>.

TFHEpp is included as a git submodule at `third_party/TFHEpp` from
`https://github.com/virtualsecureplatform/TFHEpp.git`.
