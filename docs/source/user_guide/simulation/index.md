(simulation_setup)=
# Simulation and emulation

This section describes how to verify and test a FABulous-generated fabric
using simulation and emulation.

**Simulation** is used to validate that the generated FPGA fabric itself
functions correctly. It exercises the fabric RTL with a test bitstream to
confirm that configuration loading, routing, and primitive behavior work as
expected. The purpose of simulation is to verify the fabric implementation,
not to validate end-user designs that would be mapped onto the fabric.

**Emulation** allows running a FABulous fabric on a commercial FPGA board. Two
approaches are available. In the *hardwired-bitstream* approach the bitstream is
baked into the design at synthesis time, so the fabric runs in hardware without
a configuration controller but changing the mapped design means re-synthesizing.
In the *runtime-reconfigurable* approach the fabric is synthesized onto the host
FPGA once with its configuration port intact, and user-design bitstreams are
streamed in over UART at runtime — the same path a taped-out fabric would use.

**Gate-level simulation** is the post-layout counterpart of simulation. It
exercises the hardened fabric netlist produced by the GDS flow against the PDK
standard cells, verifying the fabric all the way down to the placed-and-routed
cells.


```{toctree}
simulation
gate_level_simulation
emulation
emulation_on_fpga
```
