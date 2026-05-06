# LUT Layering

LUT layering is the next step after fractional LUT packing. The LUT
combinator maps the first user design into fractional LUT cells and may leave
some internal LUT capacity unused. Layering uses that free capacity to inject a
second user design into the already packed base design.

The important idea is that the base design is not repacked from scratch. We use
the existing `MappingResult` from the LUT combinator as an inventory of reusable
leftover LUT space, synthesize the second design separately, and then place the
second design's `$lut` cells into those leftovers.

## 1. Problem

A fractional LUT cell contains two internal LUT halves. For a single mapped
base LUT, one half is used and the other half may still be available:

```text
before layering:

  base logic
      |
      v
  +-------------------+
  | FRAC_LUT          |
  |   L0 = base LUT   | --> O0 --> base output/net
  |   L1 = unused     | --> O1 unused
  +-------------------+
```

Layering turns the unused half into useful logic for a second design:

```text
after layering:

  base logic                 overlay logic
      |                          |
      v                          v
  +-------------------+      downstream overlay cells
  | FRAC_LUT          |          ^
  |   L0 = base LUT   | --> O0 --+--> base output/net
  |   L1 = overlay LUT| --> O1 ----> overlay net
  +-------------------+
```

Only the overlay LUT itself is absorbed into the fractional LUT. Any overlay
logic after that LUT, for example flip-flops, muxes, or other non-LUT cells, is
kept as normal Yosys cells and appended to the base design with renamed ports
and nets.

## 2. Flow

The layering pass runs after the LUT combinator:

```text
design 0 -> LUT mapper -> LUT combinator -> FRAC_LUT netlist
                                                  |
design 1 -> separate PyosysBridge -> LUT mapping -+
                                                  |
                                                  v
                                      layered FRAC_LUT netlist
```

The implementation does the following:

1. The base design must already have been processed by the LUT combinator.
2. The synthesizer keeps the latest `MappingResult` and `FracLutArchitecture`.
3. The overlay design is read into a fresh `PyosysBridge`.
4. The overlay design is normalized with Yosys and mapped to `$lut` cells.
5. The layerer extracts all overlay `$lut` cells.
6. Overlay names are prefixed, for example with `design1_`.
7. Overlay integer JSON bit IDs are remapped to avoid collisions with the base
   design.
8. Each overlay LUT is placed into one compatible leftover slot.
9. The affected base `FRAC_LUT` cells are rebuilt with the normal architecture
   binder, so INIT remapping and pin assignment are handled consistently.
10. The overlay non-LUT cells, ports, and netnames are merged into the base top
    module.

If any overlay LUT cannot fit, layering raises an error and the base design is
not modified. Partial injection is intentionally not supported, because a
half-injected user design would not be functionally complete.

## 3. Effective Leftover Space

For a fractional LUT architecture with internal LUT size $K$ and nominal shared
input count $N$, the LUT combinator reports a leftover width for each mapped
cell. For layering, only single non-full FRAC cells are used as hosts.

Let a single host cell have nominal leftover width:

$L_{nominal}$

If select-as-data pair mode is disabled, the reusable layering capacity is:

$L_{effective} = L_{nominal}$

If select-as-data pair mode is enabled, the otherwise fixed `S` input can act as
one additional data input for the second internal LUT, so:

$L_{effective} = L_{nominal} + 1$

Example for a `K=4`, `N=3` architecture:

```text
single LUT4 in one FRAC_LUT:

  L0 uses a LUT4
  L1 is unused
  select-as-data enabled

  effective leftover = LUT2
```

That means a second design LUT2 can be inserted into this cell even though the
normal leftover accounting would only show one unused private input.

## 4. Placement Rule

The overlay LUTs are sorted largest first. Each overlay LUT is placed into the
smallest legal remaining leftover slot.

For one host LUT $H$ and one overlay LUT $U$, layering asks the architecture:

$bind(H, U)$

If the architecture returns a valid pair binding, the host cell is rebuilt:

```text
old:
  FRAC(H, unused)

new:
  FRAC(H, U)
```

The legality check includes:

- LUT width limits
- shared/private input assignment
- select-as-data mode when needed
- duplicate private-net policy
- output pin assignment

The INIT values are not recalculated by layering itself. Instead, layering calls
the existing `FracLutArchitecture.build_mapped_cell(...)` path:

```python
binding = architecture.try_bind_pair(host_lut, overlay_lut)
rebuilt = architecture.build_mapped_cell(host_cell.packed_id, binding)
```

This reuses the same INIT remapping used by normal pair packing. Therefore the
overlay LUT truth table is remapped to the internal FRAC pin order exactly like a
normal dual-LUT packed cell.

## 5. Port and Name Renaming

The overlay design is merged into the base design, so name conflicts must be
avoided. The layerer prefixes overlay objects:

```text
overlay input  e  -> design1_e
overlay output z  -> design1_z
overlay cell lut0 -> design1_lut0
```

The base design can also be prefixed, for example:

```text
base input a -> design0_a
base output y -> design0_y
```

This is controlled by the `base_prefix` option. Passing `None` keeps the base
names unchanged.

Yosys JSON also uses integer bit IDs for wires. Prefixing names is not enough,
because two different designs may both contain bit ID `42`. The layerer remaps
all overlay integer bit IDs to a fresh range before merging.

## 6. What Happens to Non-LUT Overlay Cells?

Only overlay `$lut` cells are absorbed into FRAC leftovers. All other overlay
cells are copied into the base design as normal cells.

Example overlay:

```verilog
wire n;
assign n = a & b;
always @(posedge clk)
    q <= n;
```

After overlay synthesis this may become:

```text
$lut -> $dff -> output
```

After layering:

```text
FRAC_LUT.O1 -> $dff -> design1_output
```

The `$dff` remains explicit. This is deliberate: Yosys can produce many
different FF and sequential-cell variants. Absorbing FFs into architecture
flip-flops should be a later physical packing pass, after all layering is done.

## 7. Example

Base design after LUT combinator:

```text
FRAC_0: L0 = LUT4(base_y), L1 = unused, effective leftover LUT2
FRAC_1: L0 = LUT4(base_z), L1 = unused, effective leftover LUT2
```

Overlay design:

```text
overlay_u0 = LUT2(e, f) -> overlay_n0
overlay_u1 = LUT2(g, h) -> overlay_n1
```

Layering can create:

```text
FRAC_0: L0 = LUT4(base_y), L1 = LUT2(overlay_u0)
FRAC_1: L0 = LUT4(base_z), L1 = LUT2(overlay_u1)
```

with outputs:

```text
FRAC_0.O0 -> base_y
FRAC_0.O1 -> design1_overlay_n0
FRAC_1.O0 -> base_z
FRAC_1.O1 -> design1_overlay_n1
```

So the second design gets implemented without adding new FRAC cells, as long as
the full overlay LUT set fits into the leftover inventory.

## 8. Inventory Math

Let the base mapping provide leftover slots:

$S = \{s_0, s_1, ..., s_{m-1}\}$

Each slot has effective capacity:

$c(s_i)$

The overlay mapper produces LUTs:

$U = \{u_0, u_1, ..., u_{n-1}\}$

Each overlay LUT has width:

$w(u_j)$

Layering needs an injective assignment:

$f : U \rightarrow S$

such that every overlay LUT fits:

$w(u_j) \le c(f(u_j))$

and the architecture binding is legal:

$bind(H_{f(u_j)}, u_j) \ne \emptyset$

where $H_{f(u_j)}$ is the base host LUT already placed in that slot.

The current implementation uses a deterministic greedy assignment:

1. Sort overlay LUTs by decreasing width.
2. For each LUT, try remaining slots from least waste to most waste.
3. Accept the first legal architecture binding.

The waste for a candidate placement is:

$waste = c(s_i) - w(u_j)$

This keeps large overlay LUTs from being blocked by earlier small placements and
tries to preserve larger remaining slots where possible.

## 9. Limitations and Next Steps

The first implementation maps the overlay design with one maximum LUT size,
derived from the largest available leftover slot unless explicitly configured.
For example, if the inventory contains one `LUT4` slot and one hundred `LUT2`
slots, the current default overlay mapping allows `LUT4`.

That is simple and works, but it is not yet histogram-aware. A later
improvement should derive an ABC/ABC9 cost vector from the leftover inventory,
so overlay synthesis is biased toward the LUT widths that are actually abundant.

Other future steps:

- absorb supported overlay FF cells into physical FRAC output FFs
- support repeated layers with updated inventory reports
- add timing-aware overlay placement
- expose a histogram-aware overlay LUT mapper backend
