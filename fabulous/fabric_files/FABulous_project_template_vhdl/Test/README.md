# FABulous simulation

This assumes FABulous is installed properly and the default instructions were followed to build the default fabric.
FABulous provides a simulation environment to test the fabric and the bitstream generated for it.
For simple use cases, there is the `run_simulation command` in the FABulous shell.
For more complex use cases it can be useful to create an own flow, like the following example `make` based flow.

Please make sure to use recent versions of [Yosys](https://github.com/YosysHQ/yosys), [nextpnr-generic](https://github.com/YosysHQ/nextpnr) (_not_ the old FABulous nextpnr fork)
and either [NVC](https://github.com/nickg/nvc) or [GHDL with mcode backend](https://github.com/ghdl/ghdl/releases), or use the [OSS-CAD-Suite](https://github.com/YosysHQ/oss-cad-suite-build) which provides nightly builds of the necessary dependencies.

> [!NOTE]
>
>**NVC is significantly faster than GHDL for our simulation.** We recommend installing NVC first. The simulation will automatically use NVC if available, otherwise it falls back to GHDL.
>
>If using GHDL, we recommend the mcode backend for better simulation performance. The OSS-CAD-Suite provides only LLVM backend, which is slower than mcode.

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

## Simulating with Vivado xsim

`task run-simulation-xsim` runs the same testbench under AMD Vivado's xsim, and
`task fab-sim-xsim` wraps it in the full build-fabric, build-design, simulate,
clean cycle. It needs `xvhdl`, `xelab` and `xsim` on `PATH` from a Vivado
installation.

xvhdl analyses the fabric as VHDL-2008, the same standard nvc and ghdl are
given, so this is a second opinion on the generated VHDL rather than a
stricter one. The analysis order is the same as the nvc path, since a design
unit has to reach the library before anything that instantiates it.

Two behaviours are worth knowing. The run produces no waveform, because the
testbench has no dump mechanism of its own and xsim takes no equivalent of
nvc's `-w`; use the nvc or ghdl path when a waveform is wanted. And a mismatch
between the fabric and the golden reference is reported at severity error,
which leaves xsim's exit status at 0, so the task greps its log for that report
instead of trusting the status.

If `xelab` stops at `cannot find crt1.o`, its linker is not picking up the host
C runtime; point it at the directory holding those objects, for example
`LIBRARY_PATH=/usr/lib/x86_64-linux-gnu task run-simulation-xsim`.
