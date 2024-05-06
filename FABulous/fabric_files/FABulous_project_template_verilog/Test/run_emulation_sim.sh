#!/usr/bin/env bash
set -ex
DESIGN=counter

rm -rf tmp
mkdir tmp
for i in $(find ../Tile -type f -name "*.v") $(find ../Fabric -type f -name "*.v")
do
    cp $i tmp/
done

iverilog -D EMULATION -s fab_tb -o fab_tb.vvp test_design/${DESIGN}.vh tmp/* test_design/${DESIGN}.v fabulous_tb.v
vvp fab_tb.vvp
rm -rf tmp
