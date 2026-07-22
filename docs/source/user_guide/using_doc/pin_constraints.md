(pin-constraints)=

# Pin Constraints File (PCF)

A pin constraints file (`.pcf`) maps the top-level ports of your user design to
physical I/O BELs on the fabric, letting you pin an _ordinary_ design without
hand-instantiating any I/O BEL.

This is the recommended alternative to the manual
{ref}`absolute-placement approach <nextpnr-compilation>`, where every I/O is wired up
by instantiating the I/O BEL (e.g. `IO_1_bidirectional_frame_config_pass`)
inside a `top_wrapper` and constraining each one with a `(* BEL=... *)`
attribute. With a PCF you keep your design's port list clean and describe the
pin assignment separately.

## How it works

The PCF flow has two parts, one in synthesis and one in place-and-route:

1. **Synthesis (`-iopad`):** Passing `-iopad` to the `synth_fabulous` Yosys pass
   runs I/O pad mapping, which inserts an I/O buffer cell
   (`$nextpnr_ibuf` / `$nextpnr_obuf` / `$nextpnr_iobuf`) on every top-level
   port. Without this step there are no I/O cells for nextpnr to constrain, and
   the PCF has nothing to bind to.
2. **Place-and-route (`-o pcf=...`):** nextpnr reads the PCF, and for each
   `set_io` line it finds the I/O cell connected to the named port and locks it
   to the requested I/O BEL.

Because the port list stays intact, you set nextpnr's top module to your design
itself (via `-top`), not to a wrapper.

:::{note}
`-iopad` is the simplest way to get I/O cells and is what this flow uses. Some
tile libraries (for example the primitives in
[fabulous-tiles](https://github.com/FPGA-Research/fabulous-tiles)) instead
provide explicit `IBUF`/`OBUF`/`TBUF`/`IOBUF` primitives that you map in with
`-extra-plib` and `-extra-map`; the fabrics in
[fabulous-fabrics](https://github.com/FPGA-Research/fabulous-fabrics) drive their
designs this way. Either approach produces the PAD-connected I/O cells that the
same `set_io` PCF then constrains — the PCF syntax below is identical in both.
:::

## PCF syntax

Each non-blank, non-comment line is a single `set_io` constraint:

```text
set_io <port> X<col>Y<row>/<bel>
```

| Field           | Meaning                                                             |
| ----------------| ------------------------------------------------------------------- |
| `<port>`        | A top-level port of your design. Bus bits are indexed, e.g. `a[0]`. |
| `X<col>Y<row>`  | The tile coordinate of the target I/O BEL (column `X`, row `Y`).    |
| `<bel>`         | The BEL letter that selects one BEL within that tile — see below.   |

### What the BEL letter means

A tile usually holds more than one BEL — an I/O tile, for instance, exposes
several physical I/O. The letter picks _which_ one. BELs are lettered `A`, `B`,
`C`, ... in the order they are declared in the tile, so `A` is the first BEL in
the tile, `B` the second, and so on. This letter is the BEL's _Z position_ (its
slot index inside the tile); together with the tile's `X`/`Y` coordinate it
uniquely identifies one BEL on the whole fabric.

You never have to guess the letter — it is column 4 of each `bel.txt` row, or
the third field of each `BelBegin` line in `bel.v2.txt` (see
{ref}`below <finding-valid-io-locations>`). For example these two `bel.txt` rows

```text
X0Y1,X0,Y1,A,IO_1_bidirectional_frame_config_pass,A_I,A_T,A_O,A_Q
X0Y1,X0,Y1,B,IO_1_bidirectional_frame_config_pass,B_I,B_T,B_O,B_Q
```

describe two I/O BELs in tile `X0Y1`: the first at slot `A`, the second at slot
`B`. So `X0Y1/A` and `X0Y1/B` are the two locations you can pin a port to in that
tile, and the `A`/`B` in the examples on this page are simply "the first I/O in
the tile" and "the second I/O in the tile".

Lines beginning with `#` are comments and blank lines are ignored. Constrain one
port (or one bus bit) per line:

```text
# clock and control
set_io clk  X0Y1/A
set_io rst  X0Y1/B
set_io ena  X0Y2/A

# 4-bit input bus
set_io a[0] X0Y3/A
set_io a[1] X0Y3/B
set_io a[2] X0Y4/A
set_io a[3] X0Y4/B
```

:::{note}
The location uses a slash and a bare tile coordinate (`X0Y1/A`), matching the
BEL names nextpnr builds internally. This differs from the port names that
appear inside the fabric netlist (`Tile_X0Y1_A_...`); do not use the
`Tile_...`-prefixed form in a PCF.
:::

(finding-valid-io-locations)=

## Finding valid I/O locations

Only tiles that contain an I/O BEL can be targeted. After the fabric flow has
run, two files in `<project-dir>/.FABulous/` list them:

- `bel.txt` — every BEL in the fabric, one CSV row per BEL. I/O BELs are the ones
  whose primitive name is `IO_1_bidirectional_frame_config_pass`,
  `InPass4_frame_config`, `OutPass4_frame_config`, or their `_mux` variants. Each
  row gives the tile coordinate and BEL letter you need, for example:

  ```text
  X0Y1,X0,Y1,A,IO_1_bidirectional_frame_config_pass,A_I,A_T,A_O,A_Q
  X0Y1,X0,Y1,B,IO_1_bidirectional_frame_config_pass,B_I,B_T,B_O,B_Q
  ```

  gives you `X0Y1/A` and `X0Y1/B`.

  :::{note}
  The letter is the slot name only for `IO_1_bidirectional_frame_config_pass`
  BELs. `InPass4_frame_config` / `OutPass4_frame_config` BELs (the BRAM-adjacent
  data I/O) are addressed by their port prefix instead of the letter — a row
  such as `X9Y1,X9,Y1,A,InPass4_frame_config_mux,RAM2FAB_D0_O0,...` is the
  location `X9Y1/RAM2FAB_D0`, not `X9Y1/A`.
  :::

- `bel.v2.txt` — the same BELs in the newer structured format, one multi-line
  `BelBegin … BelEnd` block per BEL. The tile coordinate and BEL letter are the
  second and third fields of the `BelBegin` line, so the two BELs above appear
  as:

  ```text
  BelBegin,X0Y1,A,IO_1_bidirectional_frame_config_pass,A_
  BelBegin,X0Y1,B,IO_1_bidirectional_frame_config_pass,B_
  ```

  also giving `X0Y1/A` and `X0Y1/B`.

## Running the flow

Drive the full synthesis -> place-and-route -> bitstream flow with
`compile_design`, enabling `-iopad` in synthesis and pointing nextpnr at your
PCF. From the FABulous shell, with the fabric already loaded:

```console
FABulous> compile_design user_design/counter.v -top counter \
    --synth-extra-args=-iopad \
    --nextpnr-extra-args "-o pcf=user_design/counter.pcf"
```

| Argument                              | Purpose                                            |
| ------------------------------------- | -------------------------------------------------- |
| `user_design/counter.v`               | The design source(s) to compile.                   |
| `-top counter`                        | Use the design module as the top (no wrapper).     |
| `--synth-extra-args=-iopad`           | Insert I/O buffers so the PCF has cells to bind.   |
| `--nextpnr-extra-args "-o pcf=..."`   | Forward the PCF to nextpnr's `fabulous` uarch.     |

The result is the usual bitstream (`counter.bin`) next to the design, ready to
configure the fabric.

## Worked example

A small design with a clock, reset, enable, a 4-bit input `a`, and a 4-bit
output `b`. Note the clock is still instantiated as a blackbox — a PCF pins
regular I/O, not the dedicated clock network.

`user_design/counter.v`:

```verilog
module counter (input clk, input rst, input ena, input [3:0] a, output [3:0] b);
    wire clk_int;
    (* keep *) Global_Clock inst_clk (.CLK(clk_int));

    reg [3:0] b_r;
    always @(posedge clk_int)
        if (rst)      b_r <= 4'd0;
        else if (ena) b_r <= b_r + a;
    assign b = b_r;
endmodule
```

`user_design/counter.pcf`:

```text
set_io rst  X0Y1/A
set_io ena  X0Y1/B

set_io a[0] X0Y3/A
set_io a[1] X0Y3/B
set_io a[2] X0Y4/A
set_io a[3] X0Y4/B

set_io b[0] X0Y5/A
set_io b[1] X0Y5/B
set_io b[2] X0Y6/A
set_io b[3] X0Y6/B
```

Compile it:

```console
FABulous> compile_design user_design/counter.v -top counter \
    --synth-extra-args=-iopad \
    --nextpnr-extra-args "-o pcf=user_design/counter.pcf"
```

## Troubleshooting

`No IO cell found connected to '<port>' via PAD port ... Was iopadmap run in
Yosys?`
: nextpnr found the port but no I/O buffer to constrain. Add
  `--synth-extra-args=-iopad` so synthesis inserts the I/O pads.

`Can only constrain IO cells`
: The name on the left of `set_io` is a top-level port, but it is not an I/O
  buffer — check the port name and that `-iopad` ran.

`Cannot find a pin named '<location>'`
: The `X<col>Y<row>/<bel>` location does not exist or is not an I/O BEL. Confirm
  it against `bel.txt` / `bel.v2.txt`, and use the slash form `X0Y1/A` rather
  than `Tile_X0Y1.A`.
