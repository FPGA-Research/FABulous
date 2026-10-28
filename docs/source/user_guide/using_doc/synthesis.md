(yosys)=

# Synthesis with Yosys

Yosys is used for logic synthesis and technology mapping of the Verilog Hardware Description Language (HDL) into a JSON netlist.

## Building

To build you may use the Makefile wrapper in the cloned repository (<https://github.com/YosysHQ/yosys.git>) `make` and `sudo make install`

:::{warning}
Do **not** use the latest nightly build of Yosys. Nightly builds after **29 June** are **not** compatible with current FABulous and will fail. Install Yosys **0.66**, or any build dated **before 29 June**, instead.
:::

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

FABulous is supported by upstream Yosys, using the `synth_fabulous` pass. First, run `yosys`, which will open up an interactive Yosys shell.

For Verilog projects run this command:

```bash
yosys -p "synth_fabulous -top <toplevel> -json <out.json>" <files.v>
```

For VHDL projects run the following command:

```bash
yosys -m ghdl -p ghdl <files.vhdl> -e <top-entity>;read_verilog <top_wrapper(verilog constraint)>
synth_fabulous -top <top_wrapper> -json <out.json>
```

:::{note}
For VHDL projects we used the top_wrapper as verilog because ghdl doesn't interpret the attributes(`*BEL*`);

:::

For any clocked benchmark, a clock tile blackbox module must be instantiated in the top module for clock generation.

```verilog
wire clk;
(* keep *) Global_Clock inst_clk (.CLK(clk));
```

## Yosys models

All Yosys model files can be found in the [Yosys repository](https://github.com/YosysHQ/yosys) under `$YOSYS_ROOT/techlibs/fabulous/`. These files are listed below.

| File Name      | Description                                                            |
| -------------- | ---------------------------------------------------------------------- |
| prims_ff.v     | Fabric primitives definition                                           |
| ff_map.v       | Abitrary D-type Flip-flop with SET/RESET and ENABLE technology mapping |
| latches_map.v  | Latches technology mapping                                             |
| cells_map_ff.v | LUT-4 technology mapping (can be modified to LUT-6)                    |

The current synthesis pass is built for FABulous version3. Unlike the previous two versions, the new version supports **ENABLE** and **SET/RESET** functions in D-type Flip-flops (DFF). In the pass, Yosys represents cells `$_DFF_P_`, `$_DFFE_PP_`, `$_SDFF_PP?_` and `$_SDFFCE_PP?P_` for DFFs (More DFF cells definitions can be found in the
[Yosys manual](https://github.com/YosysHQ/yosys-manual-build/releases/download/manual/manual.pdf)
Chapter 5.2). User should also define different types of DFF in the `ff_map.v` for DFF technology mapping.

| Type           | Descriptions                                          |
|----------------|-------------------------------------------------------|
| $_DFF_P_       | Positive Clock edge DFF                               |
| $_DFFE_PP_     | Positive Clock edge, High active Enable               |
| $_SDFF_PP?_    | Positive Clock edge, High active Set/Reset            |
| $_SDFFCE_PP?P_ | Positive Clock edge, High active Enable and Set/Reset |


We have made a comparison between synthesis with and without `ENABLE` and `SET/RESET DFF` on the `Murax core` benchmark, as shown below:

| Name         | LUT1 | LUT2 | LUT3 | LUT4 | LUT_total | LUTFF | LUTFF_E | LUTFF_SR | LUTFF_SS | LUTFF_ESR | LUTFF_ESS | RegFile_32x4 |
| ------------ | ---- | ---- | ---- | ---- | --------- | ----- | ------- | -------- | -------- | --------- | --------- | ------------ |
| Murax        | 4    | 335  | 1248 | 1195 | 2782      | 1361  |         |          |          |           |           | 12           |
| Murax_dffesr | 128  | 380  | 637  | 785  | 1930      | 233   | 841     | 86       | 7        | 174       | 20        | 12           |

| Type            | Descriptions                                 |
|-----------------|----------------------------------------------|
| LUTFF           | DFF with no enable and no set/reset          |
| LUTFF_E         | synchronous enable                           |
| LUTFF_SR        | synchronous reset to 0                       |
| LUTFF_SS        | synchronous set to 1                         |
| LUTFF_ESR       | synchronous enable, synchronous reset to 0   |
| LUTFF_ESS       | synchronous enable, synchronous set to 1     |
