(yosys)=

# Yosys compilation

Yosys is used for logic synthesis and technology mapping of the Verilog Hardware Description Language (HDL) into a JSON netlist.

## Building

To build you may use the Makefile wrapper in the cloned repository (<https://github.com/YosysHQ/yosys.git>) `make` and `sudo make install`

:::{note}
Yosys 0.67 reworked `synth_fabulous`: it no longer ships the FABulous primitives
and technology maps, which a FABulous project now carries in its `yosys/` folder.
FABulous works with Yosys on either side of the rework. Support for Yosys 0.66
and older ends in FABulous 3.0.
:::

## Upgrading a project created before Yosys 0.67

A project created before the rework has no `yosys/` folder, and its
`Test/Taskfile.yml` and `Test/Makefile` pass no library to `synth_fabulous`.
`compile_design` still works in such a project, because FABulous adds the
library it ships with and logs a deprecation warning. Running `task` or `make`
by hand in `Test/` fails on Yosys 0.67 and newer, with an error such as
``Module `\Global_Clock' ... is not part of the design``. To fix this, upgrade
the project:

```console
FABulous -p <project_dir> update-project-version
```

The upgrade does the following, then updates the project version:

1. Copies the library files the project lacks into `yosys/`. Files already
   there are kept, so an edited map survives.
2. Adds the library to the `synth_fabulous` invocation in `Test/Taskfile.yml`
   and `Test/Makefile`, in the form new projects use, which works on Yosys
   before and after the rework. Every other line of both files stays as it is.
   The original of each changed file is kept next to it as
   `Test/Taskfile.yml.bak` and `Test/Makefile.bak`.

The upgrade checks everything before it writes anything, and fails without
changing the project if:

- a synthesis line was edited by hand and matches no FABulous template since
  2.0.0. The error names the file and the lines it expected; restore the line
  or apply the change yourself.
- a `.bak` file it would write already exists. Move it away and run the
  upgrade again.
- `Test/Taskfile.yml` is missing. A missing `Test/Makefile` is skipped.

Running the upgrade again on an upgraded project changes nothing.

## User guide

We have provided two methods for synthesis. The first is done using the CLI and the second is done directly by calling
Yosys to do synthesis. The first method is provided for easy access and the second is provided for advanced users.

### CLI Synthesis

Assuming you have started the FABulous shell and working with a default structured project, we can run synthesis by
calling the following command:

```console
# Nextpnr backend synthesis (JSON)
FABulous> synthesis <path_to_user_design>
```

The result of the synthesis will be located in the directory that contains the design file. For example, if the design
file is located at `user_design/sequential_16bit_en.v` then the result of the synthesis will be located at
`user/design`. For the above example, the file generated will call `sequential_16bit_en.json` or
`sequential_16bit_en.blif` depends on which command is being used.

:::{note}
The underlying of the command is a python subprocess call to the Yosys command line with the exact command example used in manual synthesis If some extra toggles need to be used for Yosys then the CLI synthesis is not sufficient for now. (We might add flag pass-through from the CLI in later iterations).
:::

### Manual Synthesis

FABulous is supported by upstream Yosys, using the `synth_fabulous` pass. The pass
reads the fabric's primitives and technology maps from the project's `yosys/`
folder:

| File                          | `synth_fabulous` option | Content                                                   |
| ----------------------------- | ----------------------- | --------------------------------------------------------- |
| `primitives/prims.v`          | `-extra-plib`           | Blackboxes for the LUTs, flip-flops and BELs, `Global_Clock` included |
| `techmap/cells_map.v`         | `-cells-map`            | LUTs onto `LUT1` to `LUT6`                                |
| `techmap/arith_map.v`         | `-arith-map`            | Adders onto `LUT4_HA` with `-carry ha`                    |
| `techmap/ff_map.v`            | `-extra-map`            | Flip-flops onto `LUTFF`                                   |
| `techmap/latches_map.v`       | `-extra-map`            | Latches onto LUT logic                                    |
| `techmap/io_map.v`            | `-extra-map`            | Pads onto `IO_1_bidirectional_frame_config_pass`          |
| `memlib/ram_regfile.txt`      | `-extra-mlibmap`        | Memories that fit the `RegFile_32x4` BEL                  |
| `techmap/regfile_map.v`       | `-extra-map`            | Those memories onto `RegFile_32x4`                        |

From the project's `Test/` folder, for Verilog projects run this command:

```bash
yosys -p "synth_fabulous -top <toplevel> -json <out.json> \
  -extra-plib ../yosys/primitives/prims.v \
  -cells-map ../yosys/techmap/cells_map.v \
  -arith-map ../yosys/techmap/arith_map.v \
  -extra-map ../yosys/techmap/ff_map.v \
  -extra-map ../yosys/techmap/latches_map.v \
  -extra-map ../yosys/techmap/io_map.v \
  -extra-mlibmap ../yosys/memlib/ram_regfile.txt \
  -extra-map ../yosys/techmap/regfile_map.v \
  -ff \$_DFF_P_ 0 -ff \$_DLATCH_?_ x" <files.v>
```

For VHDL projects, elaborate the design with GHDL first and pass the same
options:

```bash
yosys -m ghdl -p "ghdl <files.vhdl> -e <top-entity>; read_verilog <top_wrapper(verilog constraint)>;
synth_fabulous -top <top_wrapper> -json <out.json> <options as above>"
```

Yosys 0.66 and older bundle this library themselves and reject these options, so
there `synth_fabulous -top <toplevel> -json <out.json>` is the whole command.
The project's `Test/Taskfile.yml` and `Test/Makefile` pick the right form for the
Yosys they run.

:::{note}
For VHDL projects we used the top_wrapper as verilog because ghdl doesn't interpret the attributes(`*BEL*`);

:::

For any clocked benchmark, a clock tile blackbox module must be instantiated in the top module for clock generation.

```verilog
wire clk;
(* keep *) Global_Clock inst_clk (.CLK(clk));
```
