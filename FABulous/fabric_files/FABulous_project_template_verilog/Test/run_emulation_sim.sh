#!/usr/bin/env bash
set -ex
DESIGN=counter
BITSTREAM=test_design/${DESIGN}.bin
VERILOG=../../fabric_generator/verilog_output
MAX_BITBYTES=16384

rm -rf tmp
mkdir tmp
for i in $(find ../Tile -type f -name "*.v") $(find ../Fabric -type f -name "*.v")
do 
    cp $i tmp/
done

iverilog -D EMULATION -s fab_tb -o fab_tb.vvp test_design/${DESIGN}.vh tmp/* test_design/${DESIGN}.v fabulous_tb.v 
vvp fab_tb.vvp
rm -rf tmp