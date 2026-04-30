# Chain Mapper

The chain mapper is a techmap-based pass that lowers selected Yosys word-level
or reduction cells into a generic target-independent primitive called
`__chain`. It is meant to describe structures that are naturally implemented as
local logic plus a one-bit state transition, such as carry chains and
wide-reduction chains.

The pass does not directly know the final FPGA primitive. Instead, it emits
`__chain` cells with enough mode and INIT metadata that a later architecture
techmap can replace them with the real FABulous primitive, for example a
LUT-plus-carry block.

## Supported Cells

The mapper currently supports:

```text
$alu
$reduce_and
$reduce_or
$reduce_xor
$reduce_bool
```

The selected cells are controlled by `ChainOp` values in the `ops` tuple. If an
operation is not listed, its Yosys cell is left untouched and can be handled by
normal mapping later.

## Flow

The high-level flow is:

```text
RTL / Yosys netlist
        |
        | optional extract_reduce
        | optional alumacc + opt_clean
        v
Yosys cells: $reduce_*, $alu
        |
        | generated techmap files
        v
generic __chain instances
        |
        | later architecture techmap
        v
real FPGA chain primitive
```

`extract_reduce` is useful because it recognizes gate-level AND/OR/XOR trees and
turns them into `$reduce_and`, `$reduce_or`, and `$reduce_xor` cells.

`alumacc` is useful because it normalizes arithmetic such as add/sub into Yosys
`$alu` style cells.

The mapper renders one techmap file per selected cell type. For example, if
`ops=(ChainOp.REDUCE_XOR, ChainOp.ALU)`, it emits two map files and applies them
with one Yosys command:

```text
techmap -autoproc -map reduce_xor_map.v -map alu_map.v
```

Internally, each source cell has a dedicated renderer class:

```text
ReduceAndTechmap
ReduceBoolTechmap
ReduceOrTechmap
ReduceXorTechmap
AluTechmap
```

Each class owns the context and template rendering for exactly one Yosys cell.
The top-level `ChainMapper` only handles normalization, temporary files,
pyosys commands, statistics, and reporting.

## Generic Primitive

The generated primitive interface is:

```verilog
module __chain #(
    parameter MODE = "REDUCE_OR",
    parameter [31:0] N = 32'd1,
    parameter INIT = 0,
    parameter [N-1:0] INV_IN = {N{1'b0}},
    parameter INV_OUT = 1'b0,
    parameter ALU_INIT_MODE = "xor"
) (
    input  [N-1:0] I,
    input  [N-1:0] A,
    input  [N-1:0] B,
    input          CI,
    output         Y,
    output         CO
);
endmodule
```

The intended meaning is:

```text
I    = local LUT/INIT inputs
A,B  = optional ALU operand inputs
CI   = incoming chain state
Y    = local result output, used by ALU as the sum bit
CO   = outgoing chain state
```

For reductions, `CO` is the meaningful accumulated result. `Y` is connected to
an unused local wire because the primitive has a common interface for all modes.

For ALU mapping, both outputs matter:

```text
Y  = sum bit
CO = carry out
```

## Reduction Mapping

For reductions, one `__chain` primitive consumes `chunk_size` input bits. The
primitive width is always fixed:

```text
N = chunk_size
```

In math notation, for a configured chunk size $K_c$:

$$
N = K_c
$$

If the final chunk has fewer real input bits, it is padded with the neutral
value for the physical operation:

```text
OR  padding = 0
XOR padding = 0
AND padding = 1
```

For a reduction input vector `x` with width `W`, the number of emitted chain
primitives is:

```text
P = ceil(W / chunk_size)
```

Equivalently:

$$
P = \left\lceil \frac{W}{K_c} \right\rceil
$$

For chunk $i$, the real bit range is:

$$
o_i = iK_c
$$

$$
b_i = \min(K_c, W - o_i)
$$

where $o_i$ is the chunk offset and $b_i$ is the number of real input bits in
that chunk. The physical input vector still has $K_c$ bits. For bit position
$j$ inside the physical chunk:

$$
I_{i,j} =
\begin{cases}
x_{o_i+j}, & j < b_i \\
e,         & j \ge b_i
\end{cases}
$$

where the neutral padding value $e$ is:

$$
e =
\begin{cases}
0, & \text{OR or XOR} \\
1, & \text{AND}
\end{cases}
$$

The mapper emits a simple linear chain:

```text
seed -> chain_0 -> chain_1 -> ... -> chain_P
```

There is no combiner tree and no recursive splitting. If `max_chain_prims` is
set and `P > max_chain_prims`, the cell is not mapped and remains as the
original Yosys cell.

## Reduction Equations

For each chunk, the mapper builds a local truth table in `INIT`.

Let:

```text
l_i = local reduction result of chunk i
c_i = incoming chain state
c_{i+1} = outgoing chain state
```

For a local chunk input vector $I_i = (I_{i,0}, ..., I_{i,K_c-1})$, the local
result is:

$$
l_i = f(I_i)
$$

where $f$ is one of $\lor$, $\land$, or $\oplus$ depending on the selected
chain mode.

For OR:

```text
l_i = OR(I_i)
c_0 = 0
c_{i+1} = c_i OR l_i
```

$$
l_i = \bigvee_{j=0}^{K_c-1} I_{i,j}
$$

$$
c_0 = 0,\qquad c_{i+1} = c_i \lor l_i
$$

Equivalent transition:

```text
CO = local ? 1 : CI
```

$$
CO =
\begin{cases}
1,  & l_i = 1 \\
CI, & l_i = 0
\end{cases}
$$

For AND:

```text
l_i = AND(I_i)
c_0 = 1
c_{i+1} = c_i AND l_i
```

$$
l_i = \bigwedge_{j=0}^{K_c-1} I_{i,j}
$$

$$
c_0 = 1,\qquad c_{i+1} = c_i \land l_i
$$

Equivalent transition:

```text
CO = local ? CI : 0
```

$$
CO =
\begin{cases}
CI, & l_i = 1 \\
0,  & l_i = 0
\end{cases}
$$

For XOR:

```text
l_i = XOR(I_i)
c_0 = 0
c_{i+1} = c_i XOR l_i
```

$$
l_i = \bigoplus_{j=0}^{K_c-1} I_{i,j}
$$

$$
c_0 = 0,\qquad c_{i+1} = c_i \oplus l_i
$$

Equivalent transition:

```text
CO = CI ^ local
```

$$
CO = CI \oplus l_i
$$

For `$reduce_bool`, the default behavior is OR-like:

```text
result = OR(all input bits)
```

## INIT Tables

The local INIT truth table is generated for the fixed `chunk_size`, not for the
number of leftover real bits in a tail chunk.

Let an INIT address $a$ encode the local input vector bits. The bit at address
$a$ is:

$$
INIT[a] = f(a_0, a_1, ..., a_{K_c-1})
$$

where:

$$
a_j = \left\lfloor \frac{a}{2^j} \right\rfloor \bmod 2
$$

The implementation loops over every address:

$$
0 \le a < 2^{K_c}
$$

and writes the local reduction result into the corresponding INIT bit. This is
why a 4-input XOR chunk has the full 4-input XOR table even when it is the tail
chunk with only one or two real input bits.

For `chunk_size = 4`:

```text
REDUCE_OR  INIT = 16'hfffe
REDUCE_AND INIT = 16'h8000
REDUCE_XOR INIT = 16'h6996
```

Examples:

```text
6-input OR, chunk_size=4

chunk 0: I = x[3:0]             INIT = 16'hfffe, N = 4
chunk 1: I = {2'b00, x[5:4]}    INIT = 16'hfffe, N = 4
```

```text
6-input AND, chunk_size=4

chunk 0: I = x[3:0]             INIT = 16'h8000, N = 4
chunk 1: I = {2'b11, x[5:4]}    INIT = 16'h8000, N = 4
```

```text
6-input XOR, chunk_size=4

chunk 0: I = x[3:0]             INIT = 16'h6996, N = 4
chunk 1: I = {2'b00, x[5:4]}    INIT = 16'h6996, N = 4
```

The padding preserves the mathematical result while keeping every physical
primitive the same width.

## De Morgan Modes

Some architectures may only have one physical reduction style available, or may
prefer one mode for routing reasons. The mapper can convert between AND and OR
chains with De Morgan identities.

For AND through OR:

```text
AND(x_0, ..., x_n) = NOT OR(NOT x_0, ..., NOT x_n)
```

$$
\bigwedge_{i=0}^{n} x_i =
\neg \left(\bigvee_{i=0}^{n} \neg x_i\right)
$$

The emitted context becomes:

```text
MODE      = "REDUCE_OR"
INV_IN    = all ones
INV_OUT   = 1
seed      = 0
padding   = 0
final     = ~chain[NUM_PRIMS]
```

For OR through AND:

```text
OR(x_0, ..., x_n) = NOT AND(NOT x_0, ..., NOT x_n)
```

$$
\bigvee_{i=0}^{n} x_i =
\neg \left(\bigwedge_{i=0}^{n} \neg x_i\right)
$$

The emitted context becomes:

```text
MODE      = "REDUCE_AND"
INV_IN    = all ones
INV_OUT   = 1
seed      = 1
padding   = 1
final     = ~chain[NUM_PRIMS]
```

The options are:

```text
and_to_or = True
or_to_and = True
```

## ALU Mapping

The `$alu` mapping emits one `__chain` primitive per output bit. It does not use
`chunk_size`; it follows carry-chain structure.

For an `M`-bit Yosys `$alu`, the number of emitted chain primitives is:

```text
P = M
```

$$
P = M
$$

If `max_chain_prims` is set and `M > max_chain_prims`, the `$alu` is left
untouched.

The template first normalizes operand widths with Yosys `$pos` cells:

```text
A_buf = sign/zero-extended A to Y_WIDTH
B_buf = sign/zero-extended B to Y_WIDTH
BB    = BI ? ~B_buf : B_buf
```

Then it emits a carry chain:

```text
carry[0] = CI

for each bit i:
    P_i        = A_i XOR B_i
    Y_i        = P_i XOR carry_i
    carry[i+1] = carry transition
```

For addition, using $p_i = A_i \oplus B_i$:

$$
Y_i = p_i \oplus c_i
$$

$$
c_{i+1} = (A_i \land B_i) \lor (p_i \land c_i)
$$

This is the usual full-adder carry relation, represented through the generic
chain primitive's local INIT and `CI`/`CO` path.

In the default `alu_init_mode = "xor"` mode:

```text
N    = 2
I    = {A_i, B_i}
INIT = 4'h6
```

`4'h6` is the two-input XOR truth table.

There is also `alu_init_mode = "full_adder"`:

```text
N    = 3
I    = {carry_i, A_i, B_i}
INIT = 8'h96
```

`8'h96` is the full-adder sum truth table.

## Chunk And Mapping Limits

Important options:

```text
chunk_size
min_chain_prims
max_chain_prims
leave_short
```

For reductions:

```text
P = ceil(input_width / chunk_size)
```

$$
P_{red} = \left\lceil \frac{W}{K_c} \right\rceil
$$

The cell maps only if:

```text
P >= min_chain_prims
```

$$
P_{red} \ge P_{min}
$$

unless `leave_short=False`, in which case the effective minimum becomes one.

If `max_chain_prims` is set, the cell also requires:

```text
P <= max_chain_prims
```

$$
P_{red} \le P_{max}
$$

For ALU:

```text
P = Y_WIDTH
```

$$
P_{alu} = Y_{width}
$$

and the same maximum rule applies:

```text
Y_WIDTH <= max_chain_prims
```

$$
P_{alu} \le P_{max}
$$

This makes `max_chain_prims` a hard per-cell physical limit. The mapper does
not split long reductions or ALUs into multiple independent physical chains.

## Example: Wide Reduction

Suppose:

```text
operation  = reduce_and
input bits = x[13:0]
chunk_size = 4
```

Then:

```text
P = ceil(14 / 4) = 4
```

The chain is:

```text
seed = 1

       x[3:0]          x[7:4]          x[11:8]         {2'b11,x[13:12]}
          |               |               |                    |
          v               v               v                    v
CI=1 -> __chain -----> __chain -----> __chain ------------> __chain -> result
        AND4            AND4            AND4                 AND4
```

The last chunk is padded with ones because AND's neutral element is one.

## Example: Adder Chain

For an 8-bit add:

```verilog
assign y = a + b;
```

Yosys can normalize this into `$alu`, and the chain mapper can emit:

```text
carry[0] -> bit0 -> bit1 -> bit2 -> ... -> bit7 -> carry[8]
```

Each bit becomes:

```text
__chain MODE="ADD"
    I  = {a_i, b_i}
    CI = carry_i
    Y  = sum_i
    CO = carry_{i+1}
```

ASCII sketch:

```text
        LUT/INIT       chain mux/state
       ---------       ---------------
a_i -->|       |--Y--> sum_i
b_i -->| XOR   |
       | INIT  |       CI -----> CO
       ---------          carry
```

The real target primitive can implement the local `INIT` function in a LUT and
route `CI/CO` through a dedicated fast carry path.

## Architecture Interpretation

A FABulous-style architecture can lower `__chain` into a primitive that looks
conceptually like this:

```text
               configuration bits
                     |
                     v
I[0..N-1] ---> +-------------+
               | LUT / INIT  | ----> Y
               +-------------+
                      |
                      v local

CI ----------> +-------------+ ----> CO
               | chain logic |
local -------> +-------------+
```

For reductions, the local LUT computes:

```text
local = f_INIT(I)
```

and the chain logic updates:

```text
CO = transition(MODE, CI, local)
```

For adders, the local LUT computes the sum bit and the chain logic computes the
carry transition.

This is the core reason the mapper is useful: many different Yosys structures
can be expressed as the same physical pattern:

```text
local truth table + one-bit chain state
```

That pattern can then be mapped to a real carry chain, reduction chain, or other
FABulous primitive in a later architecture-specific techmap.

## Why This Method Is Generic

The mapper is target-independent because it only emits `__chain`. The target
architecture can later choose how to implement each mode:

```text
MODE="REDUCE_OR"   -> OR-style reduction chain primitive
MODE="REDUCE_AND"  -> AND-style reduction chain primitive
MODE="REDUCE_XOR"  -> XOR-style reduction chain primitive
MODE="ADD"         -> carry-chain primitive
```

With the same flow, we can map several independent chain families:

```text
wide OR/AND/XOR reductions
boolean reductions
add/sub style ALU chains
future compare, popcount, prefix, or custom chains
```

Adding a new chain family should only require:

1. Add a `ChainOp`.
2. Add a standalone Verilog template.
3. Add a `ChainCellTechmap` subclass that renders that template.
4. Register that class in `ChainMapper._build_cell_mappers()`.
