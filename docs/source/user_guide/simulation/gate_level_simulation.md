(gate_level_simulation)=
# Gate-level simulation

Gate-level (GL) simulation is the post-layout counterpart of
[RTL simulation](./simulation.md). It simulates the hardened
post-place-and-route fabric netlists from the [GDS flow](../building_doc/fabric_gds.md)
against the PDK standard cells, instead of the behavioural Verilog FABulous emits.

It runs *mixed-level*: only the inner `eFPGA` core and its tiles are swapped for
the hardened netlists. The behavioural wrapper, the configuration controller, and
the same `<design>_tb.v` are reused, so one testbench drives both RTL and GL. GL
simulation is opt-in, because it needs a fabric already hardened through the GDS
flow.

## Running it

Inside the FABulous shell of a hardened project, in the Nix environment:

```bash
FABulous> compile_design ./user_design/sequential_16bit_en.v
FABulous> run_simulation --gl fst ./user_design/sequential_16bit_en.bin
```

`run_simulation --gl` resolves the fabric netlist, the tile netlists, and the PDK
cell models from the project, compiles them with the behavioural wrapper and the
testbench, and runs it under `iverilog` / `vvp`. The waveform is written to
`Test/build/<design>_gl.<fst|vcd>`; open it with `task gtkwave` in `Test/`.

From a fresh project the full path is:

```text
run_FABulous_fabric                                  # 1. generate the fabric HDL
gen_all_tile_macros --parallel
gen_fabric_macro                                     # 2. harden it (long; see fabric_gds.md)
compile_design ./user_design/<design>.v              # 3. build a bitstream
run_simulation --gl fst ./user_design/<design>.bin   # 4. gate-level simulate
```


## What to be aware of

- **gf180 runs on real cell delays.** Of the three PDKs, only gf180's Verilog
   models carry non-zero timing, so its hardened gates have a real critical path:
   a design clocked faster than it produces wrong but *defined* values.
   The testbench clocks at 1 MHz to stay under it. sky130 and IHP ship
   zero-delay models (their real timing lives in SDF, which this flow does not
   back-annotate).
- **X-pessimism is scrubbed automatically.** A hardened fabric powers up all-X.
   Once config upload finishes (`config_done`), the generated `force_block.vh`
   deposits 0 onto undriven nets and clears flop state. The scrub is **X-only**,
   it only adds definedness where the design left X.
- **Verilog only.** `run_simulation --gl` rejects VHDL projects, because the
  hardened netlists and PDK models are Verilog and `nvc` / `ghdl` cannot
  co-simulate them with a VHDL wrapper.

## Prerequisites

1. **The Nix environment** (`FABulous nix-env`) for Yosys, nextpnr, and Icarus
   Verilog. See the [Nix setup guide](../../getting_started/installation/nix-env.md).

2. **A hardened fabric project** — produced by the GDS flow, or unpacked from the
   `fabric-output-<pdk>` artifact of `gds-flow-ci.yml`. The layout must be:

   ```text
   <project>/
   ├── .FABulous/.env                                # FAB_PDK (+ FAB_PDK_ROOT)
   ├── Fabric/macro/final_views/nl/eFPGA.nl.v        # exactly one fabric netlist
   └── Tile/<tile>/macro/final_views/nl/<tile>.nl.v  # one netlist per tile
   ```

   Source resolution fails with a clear error if the layout is incomplete.

3. **PDK standard-cell models**, auto-resolved (best-effort) from `FAB_PDK`. The
   library is hard-coded in `_SCL_BY_PDK` (`cmd_run_simulation.py`) for the three
   PDKs FABulous hardens for:

   | PDK | Standard-cell library |
   |---|---|
   | `ihp-sg13g2` | `sg13g2_stdcell` |
   | `sky130A` | `sky130_fd_sc_hd` |
   | `gf180mcuD` | `gf180mcu_fd_sc_mcu7t5v0` |

   For any other PDK or variant the auto-resolve raises a clear error; pass the
   cell models explicitly with `--gl-sim-libs` instead (see below).

## Options

| Flag | Description |
|---|---|
| `--gl` | Run mixed-level gate-level simulation instead of RTL. |
| `--gl-sim-libs=<file-or-glob>` | Verilog sim-cell library, repeatable and glob-expanded. Overrides PDK auto-resolution. |
| `fst` / `vcd` | Waveform output format (positional, as for RTL). |

`--gl-sim-libs` takes multiple files: repeat the flag and/or pass a glob. Any use
of it skips PDK auto-resolution entirely.

```bash
FABulous> run_simulation --gl fst ./user_design/sequential_16bit_en.bin \
    --gl-sim-libs '/path/to/<scl>.v' \
    --gl-sim-libs '/path/to/primitives.v'
```

## Running the test suite

A GL smoke test lives in
`tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py` (marked
`@pytest.mark.gl`, skipped by default). It compiles the demo design against a
hardened project and gate-level simulates it. Opt in with `--gl` and point at the
project (or set `FAB_GL_FABRIC_PROJECT`):

```bash
$ pytest tests/fabric_gen_test/integration_test/test_designs_pattern_gl.py \
       --gl --gl-fabric-project=/path/to/hardened/project -v
```

The project is copied per test before `compile_design`, so the original is left
untouched.
