# Fabric Router

The fabric router pass runs a synthesized fabxplore design through the FABulous
nextpnr backend. It is intended as the first whole-fabric check after tile-level
generation and routing-demand evaluation: the pass exports the active pyosys
design to Yosys JSON, builds or uses a concrete PCF, invokes `nextpnr-generic`
with `--uarch fabulous`, and reports the nextpnr JSON metrics plus captured
terminal output.

## Pass Interface

Use the architecture synthesizer helper:

```python
router_pass = self.pnr_fabric_router_pass(
    top_name=None,
    out_dir=None,
    nextpnr_exec=None,
    json_path=None,
    json_output_path=None,
    pcf_path=None,
    fasm_path=None,
    report_path=None,
    project_dir=None,
    extra_args=None,
    write_json=True,
    check=True,
    live_output=False,
    report_output=True,
    report_output_max_lines=200,
    log_report=True,
)
```

The helper creates a `FabricRouterPass`, runs it on the active `PyosysBridge`
design, and stores the pass result in the architecture pass history. The
structured result is available as `router_pass.result_data`; the Markdown report
is available as `router_pass.report_summary`.

Options:

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `top_name` | `None` | Top module to route. Required when `json_path` is provided. Otherwise `None` uses the active pyosys design top. |
| `out_dir` | `None` | Output directory for generated route artifacts. If `None`, uses `<project>/user_design/fabxplore`. |
| `nextpnr_exec` | `None` | nextpnr executable. If `None`, uses the FABulous project setting. |
| `json_path` | `None` | Input Yosys JSON netlist path. If provided, this JSON is the design source of truth and has priority over the active pyosys bridge. |
| `json_output_path` | `None` | Persisted JSON output path used when `write_json=True`. If omitted, uses `<out_dir>/<top>.json`. |
| `pcf_path` | `None` | Concrete PCF path. If `None`, auto-generates `<out_dir>/<top>.pcf`. |
| `fasm_path` | `None` | FASM output path. If `None`, writes `<out_dir>/<top>.fasm`. |
| `report_path` | `None` | nextpnr JSON report path. If `None`, writes `<out_dir>/<top>_nextpnr_report.json`. |
| `project_dir` | `None` | FABulous project root used as `FAB_ROOT`. If `None`, uses the active project context. |
| `extra_args` | `None` | Extra arguments appended to the nextpnr command. |
| `write_json` | `True` | Persist the selected design JSON. With `json_path`, copies the input JSON. Without `json_path`, writes the active pyosys design. If `False` and no `json_path` is provided, a temporary bridge JSON is used only for the nextpnr invocation. |
| `check` | `True` | Raise `RuntimeError` when nextpnr returns a non-zero exit code. |
| `live_output` | `False` | Mirror nextpnr stdout/stderr live while still capturing both streams. |
| `report_output` | `True` | Append captured nextpnr stdout/stderr to the Markdown report. |
| `report_output_max_lines` | `200` | Maximum trailing stdout/stderr lines included in the report. Use `None` for full output. |
| `log_report` | `True` | Log the Markdown report after the pass runs. |

The default file layout is:

```text
<project>/
  .FABulous/
    bel.v2.txt
    pips.txt
    template.pcf
    bitStreamSpec.bin
    bitStreamSpec.csv
  user_design/
    fabxplore/
      <top>.json
      <top>.pcf
      <top>.fasm
      <top>_nextpnr_report.json
```

The router does not copy `.FABulous` into `out_dir`. nextpnr reads routing
metadata from `FAB_ROOT/.FABulous`, so the pass validates that at least
`bel.v2.txt` and `pips.txt` exist before invoking nextpnr.

## What The Pass Does

The pass performs these steps:

1. Resolve the route design source: explicit `json_path` first, otherwise the
   active pyosys bridge design.
2. Resolve the top name and output paths.
3. Validate FABulous routing metadata in `<project>/.FABulous`.
4. Stage or temporarily write the selected JSON netlist for nextpnr.
5. Generate a PCF from the selected design ports and the in-memory FABulous
   routing model, unless `pcf_path`
   is provided.
6. Run:

```text
nextpnr-generic --uarch fabulous \
  --json <top>.json \
  -o pcf=<top>.pcf \
  -o fasm=<top>.fasm \
  --report <top>_nextpnr_report.json
```

7. Parse the nextpnr JSON report.
8. Render a Markdown report with summary, utilization, timing, and captured
   nextpnr output.

## Config Bits As BEL Parameters

FABulous BEL RTL may expose configuration through one or more ports marked with
`(* FABulous, GLOBAL *)`. For nextpnr, those config values should become BEL
parameters instead of routeable ports. fabxplore handles this with the
`conf2bel` conversion used by the morph tile, LUT decomposer, and FF
materializer passes before the fabric router runs.

The principle is generic: a custom BEL can have any config carrier port name and
any parameter names, as long as:

- the config carrier port is marked `(* FABulous, GLOBAL *)`;
- the BelMap attributes map config bits with contiguous indices `0..N-1`;
- the synthesized netlist connects those config bits as constants.

Example BEL RTL before conversion:

```verilog
(* FABulous, BelMap,
   INIT0_0=0,
   INIT0_1=1,
   INIT0_2=2,
   INIT0_3=3,
   MODE=4
*)
module MY_BEL (
    input A,
    input B,
    output Y,
    (* FABulous, GLOBAL *) input [4:0] CfgB
);
    // implementation
endmodule
```

After deriving the BEL model, the config carrier is removed from the blackbox
and the mapped features become parameters:

```verilog
module MY_BEL #(
    parameter [3:0] INIT0 = 4'b0000,
    parameter MODE = 1'b0
) (
    input A,
    input B,
    output Y
);
endmodule
```

A netlist instance before conversion:

```verilog
MY_BEL u0 (
    .A(a),
    .B(b),
    .Y(y),
    .CfgB(5'b10110)
);
```

The corresponding netlist cell after conversion:

```verilog
MY_BEL #(
    .INIT0(4'b0110),
    .MODE(1'b1)
) u0 (
    .A(a),
    .B(b),
    .Y(y)
);
```

This keeps nextpnr placement/routing focused on real BEL ports, while the FASM
and bitstream flow still sees the configuration intent through BEL parameters.

## Automatic PCF Generation

When `pcf_path=None`, the router asks the attached FABulous API for the current
in-memory routing model:

```python
pips, bel, bel_v2, template_pcf = fab.genRoutingModel()
```

The pass uses `template_pcf` for candidate IO locations and filters those
candidates against `bel_v2`. This matters because FABulous template PCFs can
contain entries that look like assignable pins but are not real top-level IO
BELs, for example pass-through mux BELs.

By default the auto PCF only chooses BELs whose type is:

```text
IO_1_bidirectional_frame_config_pass
```

Those are treated as legal user IO sites. Entries for routing helper BELs such
as `InPass4_frame_config_mux` or `OutPass4_frame_config_mux` are skipped, even
if they appear in the template PCF. This avoids constraints like `X9Y1/A` being
emitted for a site that nextpnr cannot use as a user IO BEL.

The design ports are flattened in declaration order and assigned to the legal IO
sites in template order. For example:

```verilog
module top(input [2:0] a, output y);
endmodule
```

with four legal template sites becomes:

```text
set_io a[0] X0Y1/A
set_io a[1] X0Y1/B
set_io a[2] X0Y2/A
set_io y X0Y2/B
```

If the design has more top-level ports than legal IO sites, the pass raises a
`ValueError` before nextpnr is started.
