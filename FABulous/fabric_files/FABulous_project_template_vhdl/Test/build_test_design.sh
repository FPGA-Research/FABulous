#!/usr/bin/env bash
SYNTH_TCL=./synth/synth_fabulous.tcl
BIT_GEN=bit_gen

DESIGN=counter

set -ex
yosys -m ghdl -p "ghdl test_design/${DESIGN}.vhdl -e top; read_verilog test_design/top_wrapper.v; tcl $SYNTH_TCL 4 top_wrapper test_design/${DESIGN}.json;"

FAB_ROOT=.. nextpnr-generic --uarch fabulous --json test_design/${DESIGN}.json -o fasm=test_design/${DESIGN}_des.fasm
${BIT_GEN} -genBitstream test_design/${DESIGN}_des.fasm ../.FABulous/bitStreamSpec.bin test_design/${DESIGN}.bin
