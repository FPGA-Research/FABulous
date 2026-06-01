(gate_level_simulation)=
# Gate-level simulation

Gate-level (GL) simulation is the post-layout analogue of the
[RTL simulation](./simulation.md) flow. Instead of exercising the behavioural
Verilog that FABulous emits, it simulates the **post-place-and-route fabric
netlist** produced by the [GDS flow](../building_doc/fabric_gds.md): the
structural `*.nl.v` netlists written by LibreLane, wired up against the PDK
standard-cell simulation models.

## Mixed-level approach

FABulous emits two fabric modules. `eFPGA` is the raw fabric core, configured
through frame ports (`FrameData` / `FrameStrobe`). `eFPGA_top` wraps that core
with the configuration controller (`eFPGA_Config`, `Frame_Data_Reg`,
`Frame_Select`), the block RAMs, and a flattened pad interface, so a bitstream
can be streamed in over `SelfWriteData` / `SelfWriteStrobe`. The RTL testbench
drives `eFPGA_top`.

The GDS flow only hardens the **core** `eFPGA` (the configuration controller and
UART are behavioural glue, not part of the silicon fabric). GL simulation
therefore runs *mixed-level*: the behavioural wrapper and configuration logic
are kept, and only the inner `eFPGA` core and its tiles are swapped for the
hardened netlists plus the PDK cell models. Because the wrapper interface is
unchanged, **the same testbench drives RTL and GL** with no edits.

```{mermaid}
flowchart TB
    subgraph harden ["GDS flow (run once, see fabric_gds.md)"]
        T[Tiles] --> M[gen_all_tile_macros]
        M --> S[gen_fabric_macro]
        S --> NL["Fabric/macro/final_views/nl/eFPGA.nl.v
        Tile/*/macro/final_views/nl/*.nl.v"]
    end

    subgraph design ["Per design"]
        U[User design Verilog] --> C[compile_design]
        C --> B[Bitstream .bin]
    end

    subgraph sim ["Gate-level simulation (run_simulation --gl)"]
        direction LR
        W["Behavioural eFPGA_top
        + config logic"] --> H["iverilog / vvp"]
        NL --> H
        PDK[PDK std-cell models] --> H
        B --> H
        H --> R{Pass / Fail}
    end
```

:::{important}
GL simulation needs a fabric that has already been hardened through the GDS
flow. Producing that artifact takes a long time and is not always wanted, so GL
simulation is opt-in: you point it at an existing hardened project rather than
hardening one on the fly.
:::

## Prerequisites

1. **The Nix environment.** GL simulation needs Yosys, nextpnr, and Icarus
   Verilog from the pinned toolchain. Enter it first:

   ```bash
   FABulous nix-env
   ```

   See the [Nix environment setup guide](../../getting_started/installation/nix-env.md)
   for details and `nix develop` as the manual alternative.

2. **A hardened fabric project.** Run a project through the
   [GDS flow](../building_doc/fabric_gds.md) (`gen_all_tile_macros` then
   `gen_fabric_macro`, or the automated `run_FABulous_eFPGA_macro`). CI also
   publishes this as the `fabric-output-<pdk>` artifact from `gds-flow-ci.yml`,
   which unpacks directly into the expected layout.

3. **PDK standard-cell simulation models.** Resolved automatically from
   `FAB_PDK` (and `FAB_PDK_ROOT`, or the ciel install) in the project's
   `.FABulous/.env`. The defaults are known for these PDKs:

   | PDK | Standard-cell library |
   |---|---|
   | `ihp-sg13g2` | `sg13g2_stdcell` |
   | `sky130A` | `sky130_fd_sc_hd` |
   | `gf180mcuD` | `gf180mcu_fd_sc_mcu7t5v0` |

   For any other PDK, or a non-standard install, pass the cell models explicitly
   with `--gl-sim-libs` (see below).

### Expected project layout

The hardened project must contain the LibreLane outputs in place:

```text
<project>/
├── .FABulous/.env                               # FAB_PDK (+ FAB_PDK_ROOT)
├── Fabric/macro/final_views/nl/eFPGA.nl.v        # exactly one fabric netlist
└── Tile/<tile>/macro/final_views/nl/<tile>.nl.v  # one netlist per tile
```

The fabric netlist is *structural*: it instantiates tile macros by name, so the
tile netlists are passed to the simulator alongside it. Source resolution fails
with a clear error (rather than silently skipping) if the layout is incomplete,
for example if `gen_fabric_macro` has not been run.

## Running from the CLI

Gate-level simulation is the `--gl` mode of `run_simulation`. The flow is
identical to RTL simulation up to the final step: compile the design to a
bitstream, then simulate it with `--gl`.

```bash
# Inside a hardened project, in the Nix environment
compile_design ./user_design/sequential_16bit_en.v
run_simulation --gl fst ./user_design/sequential_16bit_en.bin
```

`run_simulation --gl` resolves the fabric netlist, the tile netlists, and the
PDK cell models from the project, then runs the `run-gl-simulation` Taskfile
task. That task compiles the behavioural wrapper (everything in `Fabric/` except
the behavioural `eFPGA.v` core) together with the gate-level sources, the user
design, and the existing `<design>_tb.v`, and runs it under `iverilog` / `vvp`.

The output waveform is written to `Test/build/<design>_gl.<fst|vcd>` and can be
opened the same way as the RTL waveform:

```bash
task gtkwave        # in the project Test/ directory
```

:::{note}
GL simulation is Verilog-only. The hardened netlists and PDK cell models are
Verilog, which `nvc` / `ghdl` cannot co-simulate with a VHDL wrapper, so
`run_simulation --gl` rejects VHDL projects.
:::

### Options

| Flag | Description |
|---|---|
| `--gl` | Run mixed-level gate-level simulation instead of RTL. |
| `--gl-sim-libs=<file-or-glob>` | Verilog sim-cell library file or glob. Repeatable. Overrides PDK auto-resolution. |
| `fst` / `vcd` | Waveform output format (positional, as for RTL). |

If the PDK is not in the table above, or it is installed in a non-standard
location, point at the cell models directly:

```bash
run_simulation --gl fst ./user_design/sequential_16bit_en.bin \
    --gl-sim-libs '/path/to/<scl>.v'
```

## Running the test suite

A GL smoke test for the demo design lives in
`tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py`, is marked
`@pytest.mark.gl`, and is excluded from the default run. It compiles the demo
`sequential_16bit_en` design against a hardened project and gate-level simulates
it through `run_simulation --gl`. Opt in with `--rungl` and point at the
hardened project:

```bash
pytest tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py \
       --rungl --gl-fabric-project=/path/to/hardened/project -v

# Supply the cell models explicitly (skips PDK auto-resolution)
pytest tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py \
       --rungl --gl-fabric-project=/path/to/hardened/project \
       --gl-sim-libs='/path/to/<scl>.v' -v
```

The hardened project is copied per test before `compile_design` runs, so the
original artifact is left untouched.

### Test options

| Flag | Description |
|---|---|
| `--rungl` | Enable the GL-marked test (otherwise skipped via the default `-m 'not gl'` filter). |
| `--gl-fabric-project=<path>` | Path to the hardened FABulous project. Required (or set `FAB_GL_FABRIC_PROJECT`); without it the test skips. |
| `--gl-sim-libs=<file-or-glob>` | Verilog sim-cell library file or glob. Repeatable. Overrides PDK auto-resolution. |

`--gl-fabric-project` may also be supplied via the `FAB_GL_FABRIC_PROJECT`
environment variable:

```bash
FAB_GL_FABRIC_PROJECT=/path/to/hardened/project \
    pytest tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py --rungl -v
```
