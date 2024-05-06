This assumes the default instructions were followed to build a 8x14 fabric in `../fabric_generator`.

Latest Yosys and `nextpnr-generic` from upstream (_not_ the old FABulous nextpnr fork) are used
to build the test design.

Run `build_test_design.sh` to create the bitstream and `run_simulation.sh` to compare a simulation
of the fabric running the bitstream against the design.
