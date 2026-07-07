(emulation-on-fpga)=
# Emulating a fabric on a commercial FPGA

This guide describes how to run a FABulous-generated fabric on a commercial FPGA
board and reconfigure it with user designs at runtime, over UART. The
[FABulous_fabric_demo](https://github.com/EverythingElseWasAlreadyTaken/FABulous_fabric_demo)
repository is used as the worked example. It targets a
[Digilent Nexys Video](https://digilent.com/reference/programmable-logic/nexys-video/start)
board, but the same approach applies to any FPGA large enough to hold the fabric.
Note that the FPGA needs to support latch cells, since the configuration bitstream is stored in latches.

## Two kinds of emulation

FABulous supports two different ways of testing a fabric in real hardware. They
are easy to confuse, so it is worth being explicit about which one this page
covers.

- **Hardwired-bitstream emulation.** The user-design bitstream is baked into the
  fabric RTL at synthesis time and the configuration port is removed. Swapping
  the mapped design means re-synthesizing the whole fabric. This is the mode
  described in [Emulation setup](#emulation-setup).
- **Runtime-reconfigurable emulation (this page).** The fabric is synthesized
  onto the host FPGA _once_, with its configuration loader left intact. Different
  user-design bitstreams are then streamed into the fabric over UART at runtime,
  exactly as they would be on a taped-out chip. No re-synthesis is needed to
  change the mapped design.

The second mode is the closer analogue to real silicon: the host FPGA plays the
role the ASIC would, and you exercise the same configuration path
(`config_UART` -> `ConfigFSM` -> frame registers) that a hardened fabric uses.
The first mode results in a lower resource utilization, since the bitstream does not have to be stored and
all the switch matrices collapse into simple, hardwired connections.

## How it works

There are two nested layers of FPGA in this setup.

1. The **host FPGA** (the Nexys Video) treats the FABulous fabric RTL as an
   ordinary synthesizable design. Vivado synthesizes, places, and routes the
   fabric onto the host device just like any other design.
2. The **FABulous fabric** sits inside that design as a soft, reconfigurable
   core. Its own `config_UART` loader receives FABulous bitstreams and programs
   the fabric's configuration frames.

```text
host bitstream (Vivado)          user-design bitstream (FABulous)
  loaded once, over JTAG           streamed at runtime, over UART
         │                                   │
         ▼                                   ▼
  ┌──────────────────────── Nexys Video (host FPGA) ──────────────────────┐
  │   top.v  (clock wizard, reset, UART Rx, switch/LED wiring)            │
  │     └── eFPGA_top  (the FABulous fabric)                              │
  │           ├── eFPGA_Config  (config_UART -> ConfigFSM -> frames)      │
  │           └── tile array     (LUT4AB, RegFile, BRAM, IO, ...)         │
  └───────────────────────────────────────────────────────────────────────┘
```

Because the fabric keeps its configuration port, you build the host bitstream
once and then iterate on user designs purely by uploading new FABulous
bitstreams over the serial link.

## Prerequisites

- A working FABulous installation and CAD tools (see the
  [Quick start](#quick-start)).
- [AMD/Xilinx Vivado](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado.html)
  for the host FPGA. The demo targets the Nexys Video (`xc7a200tsbg484-1`);
  install board support via
  [Digilent's board files tutorial](https://digilent.com/reference/programmable-logic/guides/installing-vivado-and-sdk).
- A host FPGA board with a UART bridge to the host PC. The Nexys Video exposes an
  FTDI-based USB-UART (default VID `0403`, PID `6014`).
- Python 3 on the host PC for the `board.py` upload script.

## Step 1: Generate the fabric and a user-design bitstream

Generate the fabric RTL and at least one user-design bitstream with the normal
FABulous flow. Using the default demo project:

```bash
FABulous create-project demo
FABulous -p demo run "run_fab; compile_design user_design/sequential_16bit_en.v"
```

This produces:

- the fabric RTL under `demo/Fabric/` and `demo/Tile/` (this is what Vivado will
  synthesize onto the host FPGA), and
- the user-design bitstream at
  `demo/user_design/sequential_16bit_en.bin` (this is what you will stream over
  UART).

See [FASM to Bitstream](#bitstream-generation) for how `compile_design` produces
the `.bin`, and for generating further bitstreams from other user designs. Every
user design you want to try on the board just needs its own `.bin` from
`compile_design` — the fabric RTL does not change.

## Step 2: The top-level wrapper

The host design needs a thin top-level module that instantiates the fabric and
connects it to the board's physical resources. The demo's `top.v` does four
things.

**Clocking:** A Vivado clocking wizard (`clk_wiz_0`) derives the fabric clock
from the board's oscillator. The demo runs the fabric at 10 MHz.

**Reset:** `resetn` is asserted only when the external reset is released _and_
the clocking wizard reports `locked`, so the fabric is not clocked before its
PLL is stable.

**Configuration link:** The board's UART receive line drives the fabric's `Rx`
port through `eFPGA_Config`, and the fabric's `ReceiveLED` is brought out to a board LED.
If it will be solid on during the bitstream transmission and blink when there is no transmission,
so you can see if the config logic receives a bitstream. This is useful for debugging something
like a baud rate mismatch.

The relevant configuration ports exposed by `eFPGA_Config` are:

| Port             | Direction | Role                                                               |
|------------------|-----------|--------------------------------------------------------------------|
| `Rx`             | in        | UART serial input — this is what `board.py` drives                 |
| `s_clk`/`s_data` | in        | Bit-bang serial config (unused in the UART flow)                   |
| `ReceiveLED`     | out       | On while configuration data is being received, blinking otherwise  |
| `ComActive`      | out       | High while a configuration transfer is in progress                 |

The fabric prioritizes configuration sources as **UART > bit-bang > parallel**,
so wiring only `Rx` is sufficient for this flow.

**User I/O:** The fabric's user I/O buses (`I_top` / `O_top` in the demo, sized
by `NUM_USED_IOS`) are mapped to board switches and LEDs so you can drive inputs
and observe outputs. In the demo, dip switches feed fabric inputs and a slice of
the fabric outputs drive `led[7:2]`, with `led[0]` used as a free-running
heartbeat and `led[1]` as the configuration-receive indicator.

:::{tip}
Match the wrapper's user-I/O mapping to the top-level ports of the user design
you compiled in Step 1. The mapped design's inputs and outputs appear on the
fabric I/O in the order defined by the fabric's I/O tiles, so keep the wrapper
and the user design consistent.
:::

## Step 3: Build the host bitstream in Vivado

1. **Create a project** targeting the Nexys Video board.
2. **Add design sources.** Add the generated fabric directory and make sure
   _Add sources from subdirectories_ is checked so all tile RTL is picked up.
   Add `top.v` and the constraint (`.xdc`) files.
3. **Set the top module** to `top`.
4. **Scope implementation-only constraints.** Any constraint file that only
   applies during implementation (for example an `efpga_loops.xdc` that
   constrains generated nets) should have its _used in_ property set to
   implementation only, so it does not interfere with synthesis.
5. **Enable out-of-context (OOC) synthesis** on the tile instances and the block
   RAM. Select them in the _Sources_ panel, right-click, and set them out of
   context. The fabric is highly repetitive, so OOC synthesis of the tiles
   drastically reduces synthesis time and RAM usage.
6. **Configure the clocking wizard** (`clk_wiz_0`): input `clk_in`, output `clk_out1` at 10 MHz.
7. **Generate the bitstream** from the Flow Navigator, then program the board
   through the Hardware Manager.

A correctly programmed board shows the heartbeat LED blinking. At this point the
host FPGA is running the fabric but the fabric is still unconfigured.

## Step 4: Upload a user design over UART

With the board programmed, stream a FABulous bitstream into the fabric using the
`board.py` helper from the demo's `upload_bitstream/` directory:

```bash
pip install -r requirements.txt
./board.py upload path/to/sequential_16bit_en.bin
```

Useful options:

| Flag              | Default                   | Meaning                                        |
|-------------------|---------------------------|------------------------------------------------|
| `-i DEVICE_ID`    | —                         | Select a specific board by serial/device id    |
| `-v`              | off                       | Verbose progress output                        |
| (VID/PID/baud)    | `0403` / `6014` / `57600` | FTDI USB-UART identity and baud rate           |

The configuration-receive LED (`led[1]` in the demo) is solid while the bitstream
is being received. When the upload finishes, the fabric holds the mapped design.

To try a different design, compile it to a `.bin` with `compile_design`
(Step 1) and run `board.py upload` again — no Vivado re-run is required.

## Step 5: Exercise the mapped design

Once configured, the fabric behaves like the hardware it emulates. Drive the
board switches wired to the fabric inputs and observe the LEDs wired to the
fabric outputs. For the `sequential_16bit_en` demo, the switches enable and
reset the counter and the LEDs show its running output.

## Troubleshooting

- **No heartbeat after programming.** The host bitstream is not running — check
  the Vivado programming step and the board's mode/power jumpers.
- **Heartbeat but no reaction to uploads.** Confirm the UART device (VID/PID),
  baud rate, and that `board.py` is talking to the right port. The
  configuration-receive LED should be solid on during a valid transfer.
- **Upload completes but outputs look wrong.** Re-check that the wrapper's
  switch/LED mapping lines up with the user design's top-level ports, and that
  the `.bin` was built against the _same_ fabric RTL that was synthesized onto
  the board.
- **Synthesis is very slow.** Make sure OOC synthesis is enabled on the tiles
  and BRAM.

## See also

- [Emulation setup](#emulation-setup) — the hardwired-bitstream alternative.
- [Simulation](#simulation-setup) — verifying the fabric in RTL before taking it
  to a board.
- [FASM to Bitstream](#bitstream-generation) — producing the `.bin` files you
  upload.
