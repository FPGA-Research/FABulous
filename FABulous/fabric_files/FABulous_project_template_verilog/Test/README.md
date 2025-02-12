# FABulous simulation

This assumes FABulous is installed properly and the default instructions were followed to build the default fabric.
FABulous provides a simulation environment to test the fabric and the bitstream generated for it.
For simple use cases, there is the `run_simulation command` in the FABulous shell.
For more complex use cases it can be useful to create an own flow, like the following example `make` based flow.


Please make sure to use recent versions of (Yosys)[https://github.com/YosysHQ/yosys], (nextpnr-generic)[https://github.com/YosysHQ/nextpnr] (_not_ the old FABulous nextpnr fork)
and (iverilog)[https://github.com/steveicarus/iverilog] or use the (OSS-CAD-Suite)[https://github.com/YosysHQ/oss-cad-suite-build] which provides nightly builds of the necessary dependencies.

Also, make sure you have the `make` package installed:
```
$ sudo apt-get install make
```

Type `make build_test_design` to create the bitstream and `make run_simulation` to compare a simulation
of the fabric running the bitstream against the design.

Other useful make targets are:
- `make` or `make sim` to build the bitstream, run simulation and remove all generated files afterward.
- `make clean` to remove all generated files
- `make build_test_design` to build the bitstream
- `make run_simulation` to run the simulation
- `make run_FABulous_demo` to run the default FABulous flow
- `make run_GTKWave` to run the GTKWave waveform viewer with the generated simulation waveform

Take a look into the Makefile to build your own flow.
