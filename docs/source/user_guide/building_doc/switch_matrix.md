(switch-matrix)=

# Switch matrix

FABulous usually implements all routing in a central switch matrix.
The inputs to the switch matrix are the wire end ports of the local wires and JUMP wires and the outputs of the {ref}`primitives`.
Hierarchies in an FPGA architecture graph will usually be modelled through JUMP wires (as shown in the {ref}`tiles` figure).
However, while it is possible to have multiple switch matrices in a tile, this is not recommended.

Configurable connections are defined in either an adjacency list or an adjacency matrix.

**Adjacency list** files follow the naming convention `<tile_descriptor>_switch_matrix.list` (e.g., LUT4AB_switch_matrix.list).

A switch matrix entry is specified by a line `<output_port>,<input_port>`.
For convenience, it is possible to specify multiple ports though a list operator `[item1|item2|...]`.
There is also a multiplier `{N}`, where N is the number of times the port should be repeated.
So a `{4}N2BEG0` will be expanded to `[N2BEG0|N2BEG0|N2BEG0|N2BEG0]`

For instance, the following line in a list file

```python
[N|E|S|W]2BEG[0|1|2],[N|E|S|W]2END[0|1|2] # extend double wires in each direction
```

is equivalent to

```python
N2BEG0,N2END0 # extend double wires in each direction
E2BEG0,E2END0 # extend double wires in each direction
S2BEG0,S2END0 # extend double wires in each direction
W2BEG0,W2END0 # extend double wires in each direction
N2BEG1,N2END1 # extend double wires in each direction
E2BEG1,E2END1 # extend double wires in each direction
S2BEG1,S2END1 # extend double wires in each direction
W2BEG1,W2END1 # extend double wires in each direction
N2BEG2,N2END2 # extend double wires in each direction
E2BEG2,E2END2 # extend double wires in each direction
S2BEG2,S2END2 # extend double wires in each direction
W2BEG2,W2END2 # extend double wires in each direction
```

The example shows how port names can be composed of string segments that can alternatively be provided in list form. The lists will be recursively unwrapped, which allows it to use multiple list operators together.

An error message is generated if the number of composed port names differs for the number of input_ports and output_ports or if ports are not found.
A warning will be generated if FABulous tries to set a connection that has already been specified.

A switch matrix multiplexer is modelled by having multiple connections for the same \<output_port>. For example, a MUX4 can be modelled as:

```python
N2BEG0,N2END3 # cascade and twist wire index
N2BEG0,E2END2 # turn from east to north
N2BEG0,S2END1 # U-turn
N2BEG0,LB_O   # route LUT B output north

# the same in compact form:
N2BEG[0|0|0|0],[N2END3|E2END2|S2END1|LB_O]
# or even more compact:
{4}N2BEG0,[N2END3|E2END2|S2END1|LB_O]
```

For completion, the following expressions are all equivalent:

```python
N2BEG[0|0|0|0] <=> {4}N2BEG0 <=> N2BEG[{4}0] <=> {2}N2BEG[0|0] <=> {2}N2BEG[{2}0] <=> [N2BEG0|N2BEG0|N2BEG0|N2BEG0]
```

The `INCLUDE` keyword can also be used to include another list file in the current list file. For example:

```python
INCLUDE, ../include/Base.list

N2BEG0,N2END3 # cascade and twist wire index
N2BEG0,E2END2 # turn from east to north
N2BEG0,S2END1 # U-turn
N2BEG0,LB_O   # route LUT B output north
```

and the target file `../include/Base.list` contains the following:

```python
N1BEG0,N2END3
N1BEG0,E2END2
```

The base file is equivalent to:

```python
N1BEG0,N2END3
N1BEG0,E2END2
N2BEG0,N2END3 # cascade and twist wire index
N2BEG0,E2END2 # turn from east to north
N2BEG0,S2END1 # U-turn
N2BEG0,LB_O # route LUT B output north
```

The directory defined by the `INCLUDE` keyword is relative to where the list file is located. For example if the file is located
at `foo/bar/far.list` then the load directory will be pointing to `foo/bar/../include/Bar.list`.

Adjacency lists are better for specifying and maintaining the connections while an adjacency matrix is better for monitoring and debug.
FABulous works on adjacency matrices and the tool can translate arbitrarily between both.
**Adjacency matrix** files are csv files and follow the naming convention `<tile_descriptor>_switch_matrix.csv` (e.g., LUT4AB_switch_matrix.csv).
The following figure shows a list file and the corresponding adjacency matrix:

:::{figure} figs/adjacency.*
:align: center
:alt: An illustration of the mapping between a list file and the corresponding adjacency matrix.
:width: 90%
:::

The top left cell of the adjacency matrix is a label only (conventionally the tile identifier name); it is not validated when the matrix is read, so any placeholder works.
The columns denote the input ports to the switch matrix and the rows denote the output ports.
A non-zero entry in the matrix denotes a configurable connection, i.e. a multiplexer input connection. Each non-zero entry corresponds to one `<output_port>,<input_port>` tuple defined in the adjacency list.

When `PreserveListOrder` is `FALSE` (by default), all configurable connections are written as `1`. When `PreserveListOrder` is `TRUE`, each non-zero entry stores the position of that input in the corresponding `.list` entry, preserving the mux input order.

When generating the adjacency matrix, FABulous will annotate for each row and column the number of connections set.
For the rows, this denotes the size of the multiplexers (e.g., MUX4) and by checking the column summary, we can inspect how well the wire usage is balanced.

:::{note}
Note that we can define the port names `VCC` and `GND` in {ref}`wires <wires>`, which allows it to specify a configurable multiplexer setting to `1` or `0`. For instance, this is useful for BRAM pins where unused ports (e.g., some MSB address bits) have to be tied to `0` without the need of any further LUTs or routing.

```python
#direction  source_name  X-offset  Y-offset  destination_name  wires
JUMP,       NULL,        0,        0,        GND,              1
JUMP,       NULL,        0,        0,        VCC,              1
```

:::

:::{note}
The multiplexers in the switch matrices are controlled by configuration bits only.

The multiplexers in {ref}`primitives <primitives>` can either be controlled by configuration bits (e.g., to select if a LUT output is to be routed to a primitive output pin or through a flop) or by the user logic (e.g., to cascade adjacent LUTs for implementing larger LUTs, like the F7MUX and F8MUX multiplexers in Xilinx FPGAs with LUT6s).
:::

:::{note}
Defining the adjacency of a switch matrix (and the wires) is a difficult task. Too many connections and wires are expensive to implement and will result in poor density and potentially in poor performance. However, too few connections and wires may lead to an inability to implement the intended user circuits on the fabric in the first place. The latter issue is not easily solvable by leaving primitives unused because that requires, for example, the use of more CLBs. That, in turn, requires more wires between the tiles, and will therefore jeopardize the approach of underutilising the CLBs.

Another difficulty is setting good switch matrix connections. An architecture graph should have sufficient entropy because of the usual sparsity of the graph. For instance, if we have to route from a LUT to a specific DSP pin, and the first path is not hitting that pin, then using an alternative path should result in possible connections to a different subset of pins. This implies that the architecture graph should not state linear combinations in subgraphs. However, adjacent LUT inputs often share the same signal (e.g., when cascading two LUT6 to form one LUT7, the two LUT6s connect to the same 6 signals). This can be used to share some multiplexing in the switch matrices.

To simplify the definition of fabrics, the provided FABulous reference fabrics have been confirmed to implement non-trivial user circuits like different CPU cores.
The provided switch matrices can be easily reused in new custom tiles (it is standard to have mostly identical switch matrices throughout an FPGA fabric, even if resources (LUTs, BRAMs, DSPs) differ).
Moreover, downstripping the routing fabric is easily possible by removing wires and connections.
:::
