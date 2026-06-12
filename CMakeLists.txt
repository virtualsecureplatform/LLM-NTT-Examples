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

function(add_ntt_verilator_test target source top_verilog)
  add_executable(${target} ${source})
  target_include_directories(${target} PRIVATE ${TFHEPP_INCLUDE_DIR})
  target_compile_options(${target} PRIVATE -Wall -Wextra -Wno-sign-compare)
  verilate(${target} SOURCES ${top_verilog})
  add_test(NAME ${target} COMMAND ${target})
endfunction()

add_ntt_verilator_test(
  yata_raintt_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/yata_raintt_reference_test.cpp
  ${PROJECT_SOURCE_DIR}/variants/yata-raintt/chisel/YataRainttTop.v
)
target_compile_definitions(yata_raintt_reference_test PRIVATE USE_COMPRESS)

add_ntt_verilator_test(
  hoge_streaming_reference_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/hoge_streaming_reference_test.cpp
  ${PROJECT_SOURCE_DIR}/variants/hoge-streaming/chisel/INTTWrap.v
)

add_ntt_verilator_test(
  hoge_nttid_identity_test
  ${PROJECT_SOURCE_DIR}/tests/cpp/hoge_nttid_identity_test.cpp
  ${PROJECT_SOURCE_DIR}/variants/hoge-nttid/chisel/NTTidPackedTop.v
)
