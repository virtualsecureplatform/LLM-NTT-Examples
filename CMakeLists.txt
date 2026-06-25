cmake_minimum_required(VERSION 3.20)
project(llm_ntt_examples CXX)

if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

find_package(verilator REQUIRED)
enable_testing()

set(TFHEPP_INCLUDE_DIR ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/include)
set(TFHEPP_THIRDPARTY_INCLUDE_DIRS
    ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/thirdparties/BLAKE3/c
    ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/thirdparties/cereal/include
    ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/thirdparties/randen
    ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/thirdparties/spqlios
    ${PROJECT_SOURCE_DIR}/third_party/TFHEpp/thirdparties/spqlios-stockham)

set(YATA_RAINTT_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/yata-raintt/chisel/YataRainttTop.v
    CACHE FILEPATH "Verilog source for the YataRainttTop test")
set(HOGE_STREAMING_INTT_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/hoge/chisel/INTTWrap.v
    CACHE FILEPATH "Verilog source for the INTTWrap test")
set(HOGE_NTTID_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/hoge/chisel/NTTidPackedTop.v
    CACHE FILEPATH "Verilog source for the NTTidPackedTop test")
set(HOGE_EXTERNALPRODUCT_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/hoge/chisel/ExternalProductWrap.v
    CACHE FILEPATH "Verilog source for the ExternalProductWrap test")
set(SMALL_HOGE32_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/small-ntt/rtl/SmallHoge32P64Rtl.sv
    CACHE FILEPATH "Verilog source for the SmallHoge32P64Rtl test")
set(SMALL_YATA8_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/small-ntt/rtl/SmallYata8RainttP27Rtl.sv
    CACHE FILEPATH "Verilog source for the SmallYata8RainttP27Rtl test")
set(SMALL_YATA8X8_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/small-ntt/rtl/SmallYata8x8RainttP27Rtl.sv
    CACHE FILEPATH "Verilog source for the SmallYata8x8RainttP27Rtl test")
set(KYBER_PE1_VERILOG
    ${PROJECT_SOURCE_DIR}/variants/kyber-polmul-hw/pe1/KyberHPM1PE.v
    CACHE FILEPATH "Verilog source for the KyberHPM1PE test")
set(KYBER_PE1_RTL_DIR ${PROJECT_SOURCE_DIR}/variants/kyber-polmul-hw/pe1)
set(KYBER_PE1_RTL_SOURCES
    ${KYBER_PE1_RTL_DIR}/addressgenerator.v
    ${KYBER_PE1_RTL_DIR}/butterfly.v
    ${KYBER_PE1_RTL_DIR}/modadd.v
    ${KYBER_PE1_RTL_DIR}/modsub.v
    ${KYBER_PE1_RTL_DIR}/modmul.v
    ${KYBER_PE1_RTL_DIR}/modred.v
    ${KYBER_PE1_RTL_DIR}/intmul.v
    ${KYBER_PE1_RTL_DIR}/BRAM.v
    ${KYBER_PE1_RTL_DIR}/BROM.v
    ${KYBER_PE1_RTL_DIR}/shiftreg.v
    ${KYBER_PE1_RTL_DIR}/div2.v
    ${KYBER_PE1_RTL_DIR}/dt0.v
    ${KYBER_PE1_RTL_DIR}/dt1.v
    ${KYBER_PE1_RTL_DIR}/dt2.v
    ${KYBER_PE1_RTL_DIR}/dt3.v
    ${KYBER_PE1_RTL_DIR}/FA.v
    ${KYBER_PE1_RTL_DIR}/HA.v)

function(add_ntt_verilator_test target source top_verilog)
  add_executable(${target} ${source})
  target_include_directories(${target} PRIVATE
      ${TFHEPP_INCLUDE_DIR}
      ${TFHEPP_THIRDPARTY_INCLUDE_DIRS})
  target_compile_options(${target} PRIVATE -Wall -Wextra -Wno-sign-compare)
  verilate(${target} VERILATOR_ARGS -Wno-fatal SOURCES ${top_verilog} ${ARGN})
  add_test(NAME ${target} COMMAND ${target})
endfunction()

add_ntt_verilator_test(
  yata_raintt_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/yata_raintt_reference_test.cpp
  ${YATA_RAINTT_VERILOG}
)
target_compile_definitions(yata_raintt_reference_test PRIVATE USE_COMPRESS)

add_ntt_verilator_test(
  hoge_streaming_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/hoge_streaming_reference_test.cpp
  ${HOGE_STREAMING_INTT_VERILOG}
)

add_ntt_verilator_test(
  hoge_nttid_identity_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/hoge_nttid_identity_test.cpp
  ${HOGE_NTTID_VERILOG}
)

add_ntt_verilator_test(
  hoge_externalproduct_ntt_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/hoge_externalproduct_ntt_reference_test.cpp
  ${HOGE_EXTERNALPRODUCT_VERILOG}
  THREADS 2
)

add_ntt_verilator_test(
  small_hoge32_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/small_hoge32_reference_test.cpp
  ${SMALL_HOGE32_VERILOG}
)

add_ntt_verilator_test(
  small_yata8_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/small_yata_reference_test.cpp
  ${SMALL_YATA8_VERILOG}
)
target_compile_definitions(small_yata8_reference_test PRIVATE
    USE_COMPRESS
    SMALL_YATA_NBIT=3
    SMALL_YATA_CYCLES=1
    SMALL_YATA_TOP_HEADER=<VSmallYata8RainttP27Rtl.h>
    SMALL_YATA_TOP_TYPE=VSmallYata8RainttP27Rtl
    SMALL_YATA_METRIC_PREFIX="small_yata8_raintt_p27")

add_ntt_verilator_test(
  small_yata8x8_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/small_yata_reference_test.cpp
  ${SMALL_YATA8X8_VERILOG}
)
target_compile_definitions(small_yata8x8_reference_test PRIVATE
    USE_COMPRESS
    SMALL_YATA_NBIT=6
    SMALL_YATA_CYCLES=8
    SMALL_YATA_TOP_HEADER=<VSmallYata8x8RainttP27Rtl.h>
    SMALL_YATA_TOP_TYPE=VSmallYata8x8RainttP27Rtl
    SMALL_YATA_METRIC_PREFIX="small_yata8x8_raintt_p27")

add_ntt_verilator_test(
  kyber_pe1_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/kyber_pe1_reference_test.cpp
  ${KYBER_PE1_VERILOG}
  ${KYBER_PE1_RTL_SOURCES}
)
target_compile_definitions(kyber_pe1_reference_test PRIVATE
    KYBER_PE1_DATA_DIR="${PROJECT_SOURCE_DIR}/variants/kyber-polmul-hw/pe1/test_pe1")
