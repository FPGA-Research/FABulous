(simulation_setup)=
# Simulation and emulation

This section describes how to verify and test a FABulous-generated fabric
using simulation and emulation.

**Simulation** is used to validate that the generated FPGA fabric itself
functions correctly. It exercises the fabric RTL with a test bitstream to
confirm that configuration loading, routing, and primitive behavior work as
expected. The purpose of simulation is to verify the fabric implementation,
not to validate end-user designs that would be mapped onto the fabric.

**Emulation** allows running a FABulous fabric on a commercial FPGA board.
Instead of loading a bitstream through the configuration port at runtime, the
bitstream is hardwired into the design at synthesis time. This provides a way
to test the fabric in actual hardware without needing a configuration
controller.


```{toctree}
simulation
emulation
```
