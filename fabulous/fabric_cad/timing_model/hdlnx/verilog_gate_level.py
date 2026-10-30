"""Convert a Verilog gate-level netlist into a timing graph.

It uses the SDFTimingGraph class to parse the SDF file and generate a NetworkX directed
graph representing the timing relationships. It will call an external STA tool to
generate the SDF file from the Verilog netlist.
"""

import re
from functools import cached_property

import networkx as nx

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph import SDFTimingGraph
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
)
from fabulous.fabric_cad.timing_model.tools.specification import StaTool


def _net_bits(expression: str, ranges: dict[str, list[int]]) -> list[str]:
    """Expand a structural Verilog connection in most-significant-bit order.

    Parameters
    ----------
    expression : str
        Net, bit select, numeric part select, constant, or concatenation.
    ranges : dict[str, list[int]]
        Declared indices, in declaration order, for each vector.

    Returns
    -------
    list[str]
        Individual net bits with Verilog identifier escapes removed.

    Raises
    ------
    ValueError
        If the expression is not a structural net connection.
    """
    expression = expression.strip()
    if expression.startswith("{") and expression.endswith("}"):
        parts = []
        start = 1
        depth = 0
        escaped = False
        for index, character in enumerate(expression[1:-1], 1):
            if escaped:
                escaped = not character.isspace()
            elif character == "\\":
                escaped = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
            elif character == "," and depth == 0:
                parts.extend(_net_bits(expression[start:index], ranges))
                start = index + 1
        parts.extend(_net_bits(expression[start:-1], ranges))
        return parts

    constant = re.fullmatch(r"(\d+)'([bBoOdDhH])([0-9a-fA-FxXzZ_]+)", expression)
    if constant:
        width, base, digits = constant.groups()
        digits = digits.replace("_", "").lower()
        if "x" in digits or "z" in digits:
            if base.lower() == "d":
                if len(set(digits)) != 1:
                    raise ValueError(f"Invalid decimal constant: {expression!r}")
                return [f"1'b{digits[0]}"] * int(width)
            digit_width = {"b": 1, "o": 3, "h": 4}[base.lower()]
            base_value = {"b": 2, "o": 8, "h": 16}[base.lower()]
            bit_groups = []
            for digit in digits:
                if digit in "xz":
                    bit_groups.append(digit * digit_width)
                else:
                    bit_groups.append(f"{int(digit, base_value):0{digit_width}b}")
            bits = "".join(bit_groups)
            padding = bits[0] if bits[0] in "xz" else "0"
            return [
                f"1'b{bit}" for bit in bits.rjust(int(width), padding)[-int(width) :]
            ]
        value = int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[base.lower()])
        return [f"1'b{bit}" for bit in f"{value:0{width}b}"[-int(width) :]]

    net = re.fullmatch(
        r"(\\\S+|[A-Za-z_$][\w$]*)(?:\s*\[\s*(-?\d+)\s*(?::\s*(-?\d+)\s*)?\])?",
        expression,
    )
    if net is None:
        raise ValueError(f"Unsupported structural Verilog connection: {expression!r}")
    name, first, last = net.groups()
    name = name.removeprefix("\\")
    if first is not None:
        if last is None:
            return [f"{name}[{first}]"]
        start, end = int(first), int(last)
        step = 1 if end >= start else -1
        return [f"{name}[{index}]" for index in range(start, end + step, step)]
    if name in ranges:
        return [f"{name}[{index}]" for index in ranges[name]]
    return [name]


class VerilogGateLevelTimingGraph(SDFTimingGraph):
    """Class to represent a timing graph from a Verilog gate-level netlist.

    Initializes the VerilogGateLevelTimingGraph by generating an SDF
    file from the provided Verilog netlist using the specified STA tool,
    and then initializing the parent SDFTimingGraph with the generated
    SDF file.

    It extends SDFTimingGraph to include functionality for generating
    the SDF file using an external static timing analysis (STA) tool.

    Parameters
    ----------
    top_name : str
        Name of the top-level module in the Verilog netlist.
    sta_tool : StaTool
        Instance of the STA tool used for timing analysis.
    delay_type_str : DelayType, optional
        Type of delay to consider (e.g., DelayType.MAX_ALL).
        Default is DelayType.MAX_ALL.
    debug : bool, optional
        Flag to enable debug mode. Default is False.
    """

    def __init__(
        self,
        top_name: str,
        sta_tool: StaTool,
        delay_type_str: DelayType = DelayType.MAX_ALL,
        debug: bool = False,
    ) -> None:
        self.top_name: str = top_name
        self.delay_type_str: DelayType = delay_type_str
        self.debug: bool = debug
        self.sta_tool: StaTool = sta_tool

        self.sta_tool.sta_analyze()
        super().__init__(self.sta_tool.sta_sdf_file, self.delay_type_str)
        self.sta_tool.sta_clean_up()

    ### Public methods ###

    @staticmethod
    def verilog_identifier_to_sdf(identifier: str) -> str:
        r"""Convert a Verilog instance identifier to its SDF representation.

        Yosys uses escaped Verilog identifiers for generated instances, for example
        `\Q$_DFF_P_`. OpenSTA removes the leading Verilog escape and escapes the
        special characters in the corresponding SDF hierarchy, producing
        `Q\$_DFF_P_`. Indexed names such as `\Q[0]$_DFF_P_` become
        `Q\[0\]\$_DFF_P_`.

        Parameters
        ----------
        identifier : str
            Instance identifier as written in the structural Verilog netlist.

        Returns
        -------
        str
            Identifier spelling used by the SDF timing graph.
        """
        if not identifier.startswith("\\"):
            return identifier

        sdf_identifier: str = identifier.removeprefix("\\")
        for special_character in ("$", "[", "]", "."):
            sdf_identifier = sdf_identifier.replace(
                special_character, f"\\{special_character}"
            )
        return sdf_identifier

    def get_raw_verilog_netlist_data(self) -> str:
        """Return the raw Verilog netlist content as a string.

        Returns
        -------
        str
            The content of the Verilog netlist file.
        """
        return self.verilog_netlist_content

    @cached_property
    def _pin_modules(self) -> dict[str, dict]:
        """Index structural connections, including vector ports and net aliases.

        Returns
        -------
        dict[str, dict]
            Parsed module declarations, instances, ranges, and alias equivalences.

        Raises
        ------
        ValueError
            If an assignment connects different numbers of bits.
        """
        source = re.sub(
            r"/\*.*?\*/|//[^\n]*", "", self.verilog_netlist_content, flags=re.DOTALL
        )
        identifier = r"(?:\\[^\s]+|[A-Za-z_$][\w$]*)"
        module_pattern = rf"\bmodule\s+({identifier})\s*(.*?)\bendmodule\b"
        instance_pattern = rf"({identifier})\s+({identifier})\s*\((.*?)\)\s*;"
        connection_pattern = rf"\.\s*({identifier})\s*\(([^()]*)\)"
        declaration_pattern = (
            r"\b(?:input|output|inout|wire|reg)\s+(?:(?:wire|reg|signed)\s+)*"
            rf"(?:\[\s*(-?\d+)\s*:\s*(-?\d+)\s*\]\s*)?({identifier})"
        )
        modules = {}
        for name, body in re.findall(module_pattern, source, flags=re.DOTALL):
            ranges = {}
            for first, last, net in re.findall(declaration_pattern, body):
                net = net.removeprefix("\\")
                if first:
                    start, end = int(first), int(last)
                    step = 1 if end >= start else -1
                    ranges[net] = list(range(start, end + step, step))
            instances = []
            for cell_type, instance, connections in re.findall(
                instance_pattern, body, flags=re.DOTALL
            ):
                if cell_type in {
                    "module",
                    "input",
                    "output",
                    "inout",
                    "wire",
                    "reg",
                    "assign",
                }:
                    continue
                instances.append(
                    {
                        "type": cell_type.removeprefix("\\"),
                        "name": instance,
                        "conns": {
                            pin.removeprefix("\\"): expression.strip()
                            for pin, expression in re.findall(
                                connection_pattern, connections
                            )
                        },
                    }
                )
            aliases = nx.utils.UnionFind()
            for left, right in re.findall(
                r"\bassign\s+(.+?)\s*=\s*(.+?);", body, flags=re.DOTALL
            ):
                left_bits = _net_bits(left, ranges)
                right_bits = _net_bits(right, ranges)
                if len(left_bits) != len(right_bits):
                    raise ValueError(
                        f"Mismatched assignment widths in module {name!r}: "
                        f"{left} = {right}"
                    )
                for left_bit, right_bit in zip(left_bits, right_bits, strict=True):
                    aliases.union(left_bit, right_bit)
            modules[name.removeprefix("\\")] = {
                "ranges": ranges,
                "instances": instances,
                "aliases": aliases,
            }
        return modules

    def resolve_hier_pin(self, hier_pin_path: str) -> list[str]:
        """Resolve a module port to its connected leaf standard-cell pins.

        Follow bit selects, slices, concatenations, and continuous net aliases.

        Parameters
        ----------
        hier_pin_path : str
            Instance hierarchy followed by a scalar or indexed module port.

        Returns
        -------
        list[str]
            Connected leaf pins in SDF spelling, without duplicates.

        Raises
        ------
        ValueError
            If the path or a structural connection is invalid.
        KeyError
            If the top module, instance, or requested port is absent.
        """
        parts = hier_pin_path.split(self.hier_sep)
        if len(parts) < 2:
            raise ValueError(
                f"Hierarchical pin path must be 'inst/pin', got: {hier_pin_path!r}"
            )
        modules = self._pin_modules
        if self.top_name not in modules:
            raise KeyError(f"Top module {self.top_name!r} not found in netlist")
        module_name = self.top_name
        prefix = []
        target_pin = parts[-1]
        for depth, name in enumerate(parts[:-1]):
            instance = next(
                (
                    item
                    for item in modules[module_name]["instances"]
                    if item["name"].removeprefix("\\") == name.removeprefix("\\")
                ),
                None,
            )
            if instance is None:
                raise KeyError(f"Instance {name!r} not found in module {module_name!r}")
            pin_base = target_pin.split("[", 1)[0]
            if depth == len(parts) - 2 and pin_base not in instance["conns"]:
                raise KeyError(f"Pin {target_pin!r} not found on instance {name!r}")
            prefix.append(self.verilog_identifier_to_sdf(instance["name"]))
            module_name = instance["type"]
            if module_name not in modules:
                if depth != len(parts) - 2:
                    raise KeyError(
                        f"Instance {parts[depth + 1]!r} not found in leaf "
                        f"module {module_name!r}"
                    )
                return [self.hier_sep.join([*prefix, target_pin])]

        visited = set()

        def traverse(module: str, net: str, path: tuple[str, ...]) -> list[str]:
            """Follow one bit through aliases and submodule port connections."""
            data = modules[module]
            root = data["aliases"][net]
            key = (module, root, path)
            if key in visited:
                return []
            visited.add(key)
            result = []
            for instance in data["instances"]:
                child = instance["type"]
                child_path = (*path, self.verilog_identifier_to_sdf(instance["name"]))
                for pin, expression in instance["conns"].items():
                    bits = _net_bits(expression, data["ranges"])
                    if child in modules:
                        pin_bits = _net_bits(pin, modules[child]["ranges"])
                        if len(bits) != len(pin_bits):
                            raise ValueError(
                                f"Port width mismatch at {'/'.join(child_path)}/{pin}: "
                                f"{len(bits)} connected bits, "
                                f"{len(pin_bits)} declared bits"
                            )
                    else:
                        pin_bits = (
                            [pin]
                            if len(bits) == 1
                            else [
                                f"{pin}[{index}]"
                                for index in reversed(range(len(bits)))
                            ]
                        )
                    for bit, pin_bit in zip(bits, pin_bits, strict=True):
                        if data["aliases"][bit] != root:
                            continue
                        if child in modules:
                            result.extend(traverse(child, pin_bit, child_path))
                        else:
                            result.append(self.hier_sep.join([*child_path, pin_bit]))
            return result

        result = []
        for bit in _net_bits(target_pin, modules[module_name]["ranges"]):
            result.extend(traverse(module_name, bit, tuple(prefix)))
        return list(dict.fromkeys(result))

    def find_verilog_modules_regex(self, name_pattern: str) -> list[str]:
        """Find Verilog module names matching a regex pattern.

        Parse a Verilog netlist and return all module names that match the given
        regex pattern.

        Parameters
        ----------
        name_pattern : str
            Regular expression pattern to match module names.

        Returns
        -------
        list[str]
            List of module names matching the regex pattern.
        """
        verilog_src: str = self.verilog_netlist_content

        # Strip block and line comments
        src = re.sub(r"/\*.*?\*/", "", verilog_src, flags=re.DOTALL)  # /* ... */
        src = re.sub(r"//.*?$", "", src, flags=re.MULTILINE)  # // ...

        #    Regex for module declaration:
        #    module <name> [#(...)] (
        module_decl_re = re.compile(
            r"^\s*module\s+([A-Za-z_]\w*)\s*"  # module name (group 1)
            r"(?:#\s*\([^()]*\))?"  # optional parameter list #(...)
            r"\s*\(",  # opening parenthesis of port list
            flags=re.MULTILINE,
        )

        name_re = re.compile(name_pattern)
        found: list[str] = []
        for m in module_decl_re.finditer(src):
            name = m.group(1)
            if name_re.search(name):
                found.append(name)
        return found

    def find_instance_paths_by_regex(
        self, inst_regex: str, filter_regex: str | None = None
    ) -> list[str]:
        """Find hierarchical instance paths matching a regex.

        Parse a structural Verilog netlist, walk the hierarchy from `top_module`, and
        return all hierarchical instance paths (without the top module name) whose path
        matches `inst_regex`.

        Parameters
        ----------
        inst_regex : str
            Regular expression to match hierarchical instance paths.
        filter_regex : str | None
            Optional regular expression to filter the matched instance paths.

        Returns
        -------
        list[str]
            List of hierarchical instance paths matching the regex.

        Raises
        ------
        KeyError
            If the top module specified by `top_name` is not found in the netlist.
        """
        top_module = self.top_name
        sep = self.hier_sep
        modules = self._pin_modules

        # -------------------------------------------------------------
        # Check that top_module exists
        # -------------------------------------------------------------
        if top_module not in modules:
            raise KeyError(f"Top module {top_module!r} not found in netlist")

        # -------------------------------------------------------------
        # DFS from top_module, build hierarchical instance paths
        # (without including the top module name itself)
        # -------------------------------------------------------------
        pattern = re.compile(inst_regex)
        results = []

        def dfs(mod_name: str, path_parts: list[str]) -> None:
            """Depth-first search to build hierarchical instance paths.

            mod_name: current module type.
            path_parts: list of instance names from *below* top, e.g.
            ["inst_sw_matrix", "inst_cus_mux81_buf_NN4BEG0"]
            """
            inst_list = modules.get(mod_name, {}).get("instances", [])
            for inst in inst_list:
                inst_name = inst["name"]
                new_parts = path_parts + [inst_name]
                hier_path = sep.join(new_parts)  # WITHOUT the top module name

                # Regex is matched on this hierarchical path
                if pattern.search(hier_path):
                    results.append(hier_path)

                # If this instance's type is another module, recurse into it
                inst_type = inst["type"]
                if inst_type in modules:
                    dfs(inst_type, new_parts)

        dfs(top_module, [])

        if filter_regex is not None:
            filter_pattern = re.compile(filter_regex)
            results = [p for p in results if filter_pattern.search(p)]

        return results

    def find_instances_with_all_nets(
        self, module_name: str, nets: list[str]
    ) -> list[str]:
        """All nets must be on the instance.

        Scan a Verilog netlist and return instance names inside `module_name` that
        have *all* nets in `nets` connected to any of their pins.

        - Only looks at direct instances inside the given module (no hierarchy).
        - Assumes gate-level style instantiations like

            cell_type inst_name (
                .A0(net1),
                .A1(net2),
                ...
            );

        Parameters
        ----------
        module_name : str
            Name of the module to search in.
        nets : list[str]
            List of net names that must all appear on the instance.

        Returns
        -------
        list[str]
            List of instance names (strings).

        Raises
        ------
        ValueError
            If the specified module is not found in the netlist.
        """
        text = self.verilog_netlist_content

        # Extract the reference module body: module <name> ... endmodule
        mod_pattern = re.compile(
            rf"module\s+{re.escape(module_name)}\b(.*?endmodule)", re.DOTALL
        )
        m = mod_pattern.search(text)
        if not m:
            raise ValueError(f"Module {module_name!r} not found in netlist content")

        module_body = m.group(1)

        # Remove simple // comments to avoid bogus matches
        module_body = re.sub(r"//.*?$", "", module_body, flags=re.MULTILINE)

        # Find instantiations:  cell_type inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)        # cell type
            \s+
            (?P<inst>\w+)        # instance name
            \s*
            \(
                (?P<pins>[^;]*?) # pin connections until the semicolon
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pin connection pattern: .PIN_NAME(NET_NAME)
        pin_conn_pattern = re.compile(r"\.\s*\w+\s*\(\s*([^\s\)]+)\s*\)")

        target_nets = set(nets)
        matching_instances: list[str] = []

        for im in inst_pattern.finditer(module_body):
            inst_name = im.group("inst")
            pins_block = im.group("pins")

            # Collect all nets connected on this instance
            nets_on_inst = set(pin_conn_pattern.findall(pins_block))

            if target_nets.issubset(nets_on_inst):
                matching_instances.append(inst_name)

        return matching_instances

    def find_instances_paths_with_all_nets(
        self, module_name: str, nets: list[str], filter_regex: str | None = None
    ) -> list[str]:
        """Find hierarchical instance paths with all nets.

        Combines `find_instances_with_all_nets` and `find_instance_paths_by_regex` to
        return hierarchical instance paths (without top module name) for instances
        inside `module_name` that have *all* nets in `nets` connected to any of their
        pins.

        Parameters
        ----------
        module_name : str
            Name of the module to search in.
        nets : list[str]
            List of net names that must all appear on the instance.
        filter_regex : str | None
            Optional regular expression to filter the matched instance paths.

        Returns
        -------
        list[str]
            List of hierarchical instance paths (strings).
        """
        inst_hier_paths = []
        insts = self.find_instances_with_all_nets(module_name, nets)
        for inst in insts:
            paths = self.find_instance_paths_by_regex(
                rf"{re.escape(inst)}$", filter_regex=filter_regex
            )
            inst_hier_paths.extend(paths)
        return inst_hier_paths

    def net_to_pin_paths_for_instance(self, hier_inst_path: str) -> dict[str, str]:
        """Paths from nets to hierarchical pins for an instance.

        Given a hierarchical instance path like:
            "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3"

        and a gate-level Verilog netlist, return a mapping:
            net_name -> "hier_inst_path/pin_name"

        Only the leaf instance is resolved (no further hierarchy).

        Example output:
            {
            "N1END2": "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3/A0",
            "N2END4": "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3/A1",
            ...
            }

        Parameters
        ----------
        hier_inst_path : str
            Hierarchical instance path.

        Returns
        -------
        dict[str, str]
            Mapping from net names to pins keep hierarchy (no further hierarchy).

        Raises
        ------
        ValueError
            If the top module or instance is not found in the netlist.
        RuntimeError
            If an unexpected error occurs during hierarchy resolution.
        """
        text = self.verilog_netlist_content
        top_module = self.top_name
        sep = self.hier_sep

        # Collect all modules: name -> body text
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        modules = {}
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            modules[name] = body

        if top_module not in modules:
            raise ValueError(f"Top module {top_module!r} not found in netlist")

        # Pattern for instances inside a module
        # Handles: cell_type [#(...)] inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections until ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pattern for pin connections: .PIN(NET)
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        # Walk the hierarchy down to the leaf instance
        segments = hier_inst_path.split(sep)
        current_module = top_module

        for depth, inst_name in enumerate(segments):
            body = modules.get(current_module)
            if body is None:
                raise ValueError(
                    f"Module {current_module!r} not found while "
                    f"resolving {hier_inst_path!r}"
                )

            found = False
            cell_type = None
            pins_block = None

            for m in inst_pattern.finditer(body):
                if m.group("inst") == inst_name:
                    cell_type = m.group("cell")
                    pins_block = m.group("pins")
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Instance {inst_name!r} not found inside module {current_module!r}"
                )

            # If not yet at the leaf, descend into the instance's module type
            if depth < len(segments) - 1:
                current_module = cell_type
            else:
                # Leaf instance: parse its pin connections
                net_to_path: dict[str, str] = {}
                for pm in pin_conn_pattern.finditer(pins_block):
                    pin = pm.group("pin")
                    net = pm.group("net")
                    # Note: if the same net appears on multiple pins, last one wins
                    net_to_path[net] = f"{hier_inst_path}{sep}{pin}"
                return net_to_path

        raise RuntimeError("Unexpected end of hierarchy resolution")

    def net_to_pin_paths_for_instance_resolved(
        self, hier_inst_path: str
    ) -> dict[str, list[str]]:
        """Resolve hierarchical instance pin paths to leaf pins.

        Given a hierarchical instance path like:
        "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3"
        and a gate-level Verilog netlist, return a mapping:
        net_name -> [ "full_hier_pin_path1", "full_hier_pin_path2", ... ]
        where each full hierarchical pin path is resolved down to leaf std-cell pins.

        Parameters
        ----------
        hier_inst_path : str
            Hierarchical instance path.

        Returns
        -------
        dict[str, list[str]]
            Mapping from net names to lists of resolved leaf pin paths.
        """
        resolved_paths: dict[str, list[str]] = {}
        net_to_pin = self.net_to_pin_paths_for_instance(hier_inst_path)
        for net, pin_path in net_to_pin.items():
            leaf_pins = self.resolve_hier_pin(pin_path)
            resolved_paths[net] = leaf_pins
        return resolved_paths

    def nearest_port_from_pin(
        self, hier_pin_path: str, reverse: bool = False, num_ports: int = 1
    ) -> list[str]:
        """Nearest port from pin.

        Given a hierarchical pin path like "inst1/inst2/A0", find the nearest top-
        level port connected to the same net as that pin. Depending on `reverse`, the
        search is done towards input ports (reverse=True) or output ports
        (reverse=False).

        Parameters
        ----------
        hier_pin_path : str
            Hierarchical pin path.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return. if less ports are found,
            return all found, which can be less than `num_ports`.

        Returns
        -------
        list[str]
            Hierarchical paths of the nearest top-level ports.

        Raises
        ------
        ValueError
            If num_ports is less than 1.
        """
        # Use NetworkX shortest path to find nearest port
        # Depending on `reverse`, search towards inputs or outputs
        # If reverse=True, search towards inputs (for setup analysis)
        # If reverse=False, search towards outputs (for hold analysis)

        if num_ports < 1:
            raise ValueError("num_ports must be at least 1")
        if num_ports == 1:
            path_without_sentinel, closest_target = (
                self.path_to_nearest_target_sentinel(
                    hier_pin_path,
                    self.input_ports if reverse else self.output_ports,
                    reverse=reverse,
                )
            )
            return [closest_target] if closest_target is not None else []
        if reverse:
            dist = nx.single_source_shortest_path_length(
                self.reverse_graph, hier_pin_path
            )
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.input_ports]
        else:
            dist = nx.single_source_shortest_path_length(self.graph, hier_pin_path)
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.output_ports]

        if len(leaf_dists) == 0:
            return []

        # already sorted by distance from NetworkX
        return [leaf_dists[i][0] for i in range(min(num_ports, len(leaf_dists)))]

    def nearest_ports_from_instance_pin_nets(
        self, inst_path: str, reverse: bool = False, num_ports: int = 1
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Nearest ports from instance pin nets.

        Given a hierarchical instance path like "inst1/inst2", find the nearest top-
        level ports connected to the same nets as the instance's pins. Depending on
        `reverse`, the search is done towards input ports (reverse=True) or output ports
        (reverse=False).

        Parameters
        ----------
        inst_path : str
            Hierarchical instance path.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return per pin. if less ports are found,
            return all found, which can be less than `num_ports`.

        Returns
        -------
        tuple[dict[str, list[str]], list[str]]
            Mapping from instance net names to lists of
            nearest top-level port paths. The list is sorted
            starting from the nearest ports.
        """
        net_to_pin: dict[str, list[str]] = self.net_to_pin_paths_for_instance_resolved(
            inst_path
        )
        pin_to_nearest_ports: dict[str, list[str]] = {}
        pin_to_nearest_ports_list: list[str] = []
        for net, pin_paths in net_to_pin.items():
            if pin_paths is None or len(pin_paths) == 0:
                continue
            # Maybe not only use the first pin path for nearest port search
            nearest_ports = self.nearest_port_from_pin(
                pin_paths[0], reverse=reverse, num_ports=num_ports
            )
            pin_to_nearest_ports_list.extend(nearest_ports)
            pin_to_nearest_ports[net] = nearest_ports

        # Remove duplicates while preserving order
        return pin_to_nearest_ports, list(dict.fromkeys(pin_to_nearest_ports_list))

    def get_instance_pins(self, hier_inst_path: str) -> list[str]:
        """Pin names connected to an instance.

        Given a hierarchical instance path like:
        "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3"
        and a gate-level Verilog netlist, return a list of pin names
        connected to that instance, in the order they appear in the instantiation.

        Parameters
        ----------
        hier_inst_path : str
            Hierarchical instance path.

        Returns
        -------
        list[str]
            List of pin names connected to the instance.

        Raises
        ------
        ValueError
            If the top module or instance is not found in the netlist.
        RuntimeError
            If an unexpected error occurs during hierarchy resolution.
        """
        verilog_src: str = self.verilog_netlist_content
        top_module: str = self.top_name
        sep: str = self.hier_sep

        # Strip comments to avoid bogus matches ---
        # Remove block comments /* ... */
        text = re.sub(r"/\*.*?\*/", "", verilog_src, flags=re.DOTALL)
        # Remove line comments // ...
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)

        # --- 1) Collect all modules: name -> body text ---
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        modules = {}
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            modules[name] = body

        if top_module not in modules:
            raise ValueError(f"Top module {top_module!r} not found")

        # Pattern for instances inside a module ---
        # Handles: cell_type [#(...)] inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections until ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pattern for pin connections: .PIN(NET) ---
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        # Walk the hierarchy down to the leaf instance ---
        segments = hier_inst_path.split(sep)
        current_module = top_module

        for depth, inst_name in enumerate(segments):
            body = modules.get(current_module)
            if body is None:
                raise ValueError(
                    f"Module {current_module!r} not found while "
                    f"resolving {hier_inst_path!r}"
                )

            found = False
            cell_type = None
            pins_block = None

            # find the instance in the current module
            for m in inst_pattern.finditer(body):
                if m.group("inst") == inst_name:
                    cell_type = m.group("cell")
                    pins_block = m.group("pins")
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Instance {inst_name!r} not found inside module {current_module!r}"
                )

            # If not yet at the leaf, descend into the instance's module type
            if depth < len(segments) - 1:
                current_module = cell_type
            else:
                # Leaf instance: parse its pin connections
                pins_in_order: list[str] = []
                for pm in pin_conn_pattern.finditer(pins_block):
                    pin_name = pm.group("pin")
                    pins_in_order.append(pin_name)
                return pins_in_order

        # Should never get here
        raise RuntimeError("Hierarchy resolution fell through unexpectedly")

    def get_module_instance_nets(self, module_name: str) -> dict[str, list[str]]:
        """Extract, for a module, all inst names and nets connected to each instance.

        Parameters
        ----------
        module_name : str
            Name of the module to inspect.

        Returns
        -------
        dict[str, list[str]]
            Mapping:
            instance_name -> [net1, net2, net3, ...]
            where each list contains all nets connected to that instance,
            order is the order of the pin connections in the instantiation.

        Raises
        ------
        ValueError
            If the specified module is not found in the Verilog source.
        """
        verilog_src: str = self.verilog_netlist_content

        # Strip comments so patterns don't get confused ---
        # Remove block comments /* ... */
        text = re.sub(r"/\*.*?\*/", "", verilog_src, flags=re.DOTALL)
        # Remove line comments // ...
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)

        # Extract the body of the target module: module <name> ... endmodule
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        target_body = None
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            if name == module_name:
                target_body = body
                break

        if target_body is None:
            raise ValueError(
                f"Module {module_name!r} not found in provided Verilog source"
            )

        # Instance pattern inside a module
        # Matches:
        #   cell_type inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections up to ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pin connection pattern: .PIN(NET)
        # NET can be e.g. N1END3, JE2BEG0, ConfigBits[328], etc.
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        instance_to_nets: dict[str, list[str]] = {}

        # Find all instantiations and their nets
        for m in inst_pattern.finditer(target_body):
            inst_name = m.group("inst")
            pins_block = m.group("pins")

            nets: list[str] = []
            for pm in pin_conn_pattern.finditer(pins_block):
                net = pm.group("net")
                nets.append(net)

            instance_to_nets[inst_name] = nets

        return instance_to_nets
