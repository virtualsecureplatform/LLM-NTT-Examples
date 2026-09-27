#!/bin/sh
exec /usr/local/lib/python3.10/dist-packages/verilator/bin/verilator \
  -MAKEFLAGS CFG_CXXFLAGS_PCH_I=-include "$@"
