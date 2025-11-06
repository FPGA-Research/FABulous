"""The Verilog code generator."""

import math
import re
from pathlib import Path

from FABulous.fabric_definition.define import IO
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator


class VerilogCodeGenerator(CodeGenerator):
    """The writer class for generating Verilog code."""

    def addComment(
        self, comment: str, onNewLine: bool = False, end: str = "", indentLevel: int = 0
    ) -> None:
        """Add a Verilog comment to the generated code.

        Args:
            comment: The comment text to add
            onNewLine: Whether to add the comment on a new line
            end: Additional text to append at the end
            indentLevel: The indentation level for the comment
        """
        if onNewLine:
            self._add("")
        if self._content:
            self._content[-1] += f"{' ':<{indentLevel * 4}}" + f"//{comment}{end}"
        else:
            self._add(f"{' ':<{indentLevel * 4}}" + f"// {comment}{end}")

    def addHeader(self, name: str, _package: str = "", indentLevel: int = 0) -> None:
        """Add the Verilog module header.

        Args:
            name: Module name
            _package: Package parameter (unused in Verilog)
            indentLevel: The indentation level
        """
        self._add(f"module {name}", indentLevel)

    def addHeaderEnd(self, name: str, indentLevel: int = 0) -> None:
        """Add the module end statement (no-op for Verilog).

        Args:
            name: Module name (unused)
            indentLevel: The indentation level (unused)
        """

    def addParameterStart(self, indentLevel: int = 0) -> None:
        """Start the parameter declaration section.

        Args:
            indentLevel: The indentation level
        """
        self._add("#(", indentLevel)

    def addParameterEnd(self, indentLevel: int = 0) -> None:
        """End the parameter declaration section.

        Args:
            indentLevel: The indentation level
        """
        temp = self._content.pop()
        if "//" in temp:
            temp2 = self._content.pop()[:-1]
            self._add(temp2)
            self._add(temp)
        else:
            self._add(temp[:-1])
        self._add(")", indentLevel)

    def addParameter(
        self, name: str, storageType: str, value: str, indentLevel: int = 0
    ) -> None:
        """Add a parameter declaration.

        Args:
            name: Parameter name
            storageType: Parameter type or width specification
            value: Default value
            indentLevel: The indentation level
        """
        if storageType.startswith("["):
            self._add(f"parameter {storageType} {name}={value},", indentLevel)
        else:
            self._add(f"parameter {name}={value},", indentLevel)

    def addPortStart(self, indentLevel: int = 0) -> None:
        """Start the port declaration section.

        Args:
            indentLevel: The indentation level
        """
        self._add("(", indentLevel)

    def addPortEnd(self, indentLevel: int = 0) -> None:
        """End the port declaration section.

        Args:
            indentLevel: The indentation level
        """

        def deComma(x: str) -> str:
            cpos = x.rfind(",")
            assert cpos != -1, x
            return x[:cpos] + x[cpos + 1 :]

        temp = self._content.pop()
        if "//" in temp and "," not in temp:
            temp2 = deComma(self._content.pop())
            self._add(temp2)
            self._add(temp)
        else:
            self._add(deComma(temp))
        self._add(");", indentLevel)

    def addPortScalar(
        self,
        name: str,
        io: IO,
        reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a scalar port declaration.

        Args:
            name: Port name
            io: Input/output direction
            reg: Whether the port should be declared as a `reg` type
            attribute: Additional attributes to add as Verilog attribute
            indentLevel: The indentation level
        """
        ioString = io.value.lower()
        if attribute:
            attribute = f"(* FABulous, {attribute} *) "
        regString = "reg" if reg else ""
        self._add(f"{attribute}{ioString} {regString} {name},", indentLevel)

    def addPortVector(
        self,
        name: str,
        io: IO,
        msbIndex: int | str,
        reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a vector port declaration.

        Args:
            name: Port name
            io: Input/output direction
            msbIndex: Most significant bit index
            reg: Whether port should be declared as `reg` type
            attribute: Additional attributes to add as Verilog attribute
            indentLevel: The indentation level
        """
        ioString = io.value.lower()
        regString = "reg" if reg else ""
        if attribute:
            attribute = f"(* FABulous, {attribute} *) "
        self._add(
            f"{attribute}{ioString} {regString} [{msbIndex}:0] {name},", indentLevel
        )

    def addDesignDescriptionStart(self, name: str, indentLevel: int = 0) -> None:
        """Start the design description (no-op for Verilog).

        Args:
            name: Module name (unused)
            indentLevel: The indentation level (unused)
        """

    def addDesignDescriptionEnd(self, indentLevel: int = 0) -> None:
        """End the design description with endmodule.

        Args:
            indentLevel: The indentation level
        """
        self._add("endmodule", indentLevel)

    def addConstant(self, name: str, value: str, indentLevel: int = 0) -> None:
        """Add a parameter/constant declaration.

        Args:
            name: Constant name
            value: Constant value
            indentLevel: The indentation level
        """
        self._add(f"parameter {name} = {value};", indentLevel)

    def addConnectionScalar(
        self, name: str, reg: bool = False, indentLevel: int = 0
    ) -> None:
        """Add a scalar `wire` or `reg` declaration.

        Args:
            name: Signal name
            reg: If True, the connection will be declared as a `reg` type.
                 If False, the connection will be declared as a `wire`.
                 Defaults to False.
            indentLevel: The indentation level
        """
        con_type = "reg" if reg else "wire"
        self._add(f"{con_type} {name};", indentLevel)

    def addConnectionVector(
        self,
        name: str,
        startIndex: int,
        endIndex: int = 0,
        reg: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add a vector wire or reg declaration.

        Args:
            name: Signal name
            startIndex: Start index (MSB)
            endIndex: End index (LSB)
            reg: Whether to declare as `reg` type
            indentLevel: The indentation level
        """
        con_type = "reg" if reg else "wire"
        self._add(f"{con_type}[{startIndex}:{endIndex}] {name};", indentLevel)

    def addLogicStart(self, indentLevel: int = 0) -> None:
        """Start the logic section (no-op for Verilog).

        Args:
            indentLevel: The indentation level (unused)
        """

    def addLogicEnd(self, indentLevel: int = 0) -> None:
        """End the logic section (no-op for Verilog).

        Args:
            indentLevel: The indentation level (unused)
        """

    def addInstantiation(
        self,
        compName: str,
        compInsName: str,
        portsPairs: list[tuple[str, str]],
        paramPairs: list[tuple[str, str]] | None = None,
        emulateParamPairs: list[tuple[str, str]] | None = None,
        indentLevel: int = 0,
    ) -> None:
        """Add a module instantiation.

        Args:
            compName: Module name
            compInsName: Instance name
            portsPairs: List of (port, signal) pairs for port mapping
            paramPairs: List of (parameter, value) pairs for parameter mapping
            emulateParamPairs: Parameters for emulation mode only
            indentLevel: The indentation level
        """
        if emulateParamPairs is None:
            emulateParamPairs = []
        if paramPairs is None:
            paramPairs = []
        if paramPairs:
            port = [f".{i[0]}({i[1]})" for i in paramPairs]
            self._add(f"{compName}", indentLevel=indentLevel)
            self._add("#(", indentLevel=indentLevel + 1)
            self._add(
                (f",\n{' ':<{4 * (indentLevel + 1)}}").join(port),
                indentLevel=indentLevel + 1,
            )
            self._add(")", indentLevel=indentLevel + 1)
            self._add(f"{compInsName}", indentLevel=indentLevel + 1)
            self._add("(", indentLevel=indentLevel + 1)
        elif emulateParamPairs:
            port = [f".{i[0]}({i[1]})" for i in emulateParamPairs]
            self._add(f"{compName}", indentLevel=indentLevel)
            self._add("`ifdef EMULATION", indentLevel=0)
            self._add("#(", indentLevel=indentLevel + 1)
            self._add(
                (f",\n{' ':<{4 * (indentLevel + 1)}}").join(port),
                indentLevel=indentLevel + 1,
            )
            self._add(")", indentLevel=indentLevel + 1)
            self._add("`endif", indentLevel=0)
            self._add(f"{compInsName}", indentLevel=indentLevel + 1)
            self._add("(", indentLevel=indentLevel + 1)
        else:
            self._add(f"{compName} {compInsName} (", indentLevel=indentLevel)

        connectPair = []
        for i in portsPairs:
            tmp = i[1].replace("(", "[").replace(")", "]")
            connectPair.append(f".{i[0]}({tmp})")

        self._add(
            (f",\n{' ':<{4 * (indentLevel + 1)}}").join(connectPair),
            indentLevel=indentLevel + 1,
        )
        self._add(");", indentLevel=indentLevel)
        self.addNewLine()

    def addComponentDeclarationForFile(self, fileName: Path | str) -> int:
        """Check if a Verilog file uses configuration bits.

        Parameters
        ----------
        fileName : Path | str
            Path to the Verilog file to analyze

        Returns
        -------
        int
            1 if file uses configuration bits, 0 otherwise
        """
        configPortUsed = 0  # 1 means is used
        with Path(fileName).open() as f:
            data = f.read()

        if result := re.search(
            r"NumberOfConfigBits.*?(\d+)", data, flags=re.IGNORECASE
        ):
            configPortUsed = 1
            if result.group(1) == "0":
                configPortUsed = 0

        return configPortUsed

    def addShiftRegister(self, configBits: int, indentLevel: int = 0) -> None:
        """Add a shift register for configuration bits.

        Args:
            configBits: Number of configuration bits
            indentLevel: The indentation level
        """
        template = f"""
// the configuration bits shift register
    always @ (posedge CLK)
        begin
            if (MODE=1b'1) begin    //configuration mode
                ConfigBits <= {{CONFin,ConfigBits[{configBits}-1:1]}};
            end
        end
    assign CONFout = ConfigBits[{configBits}-1];

        """
        self._add(template, indentLevel)

    def addFlipFlopChain(self, configBits: int, indentLevel: int = 0) -> None:
        """Add a flip-flop chain for configuration bits.

        Args:
            configBits: Number of configuration bits
            indentLevel: The indentation level
        """
        cfgBit = int(math.ceil(configBits / 2.0)) * 2
        template = f"""
    genvar k;
    assign ConfigBitsInput = {{ConfigBits[{cfgBit}-1-1:0], CONFin;}}
    // for k in 0 to Conf/2 generate
    for (k=0; k < {cfgBit - 1}; k = k + 1) begin: L
        LHQD1 inst_LHQD1a(
            .D(ConfigBitsInput[k*2]),
            .E(CLK),
            .Q(ConfigBits[k*2])
        );
        LHQD1 inst_LHQD1b(
            .D(ConfigBitsInput[(k*2)+1]),
            .E(MODE),
            .Q(ConfigBits[(k*2)+1])
        );
    end
    assign CONFout = ConfigBits[{cfgBit}-1];
"""
        self._add(template, indentLevel)

    def addRegister(
        self,
        reg: str,
        regIn: str,
        clk: str = "UserCLK",
        inverted: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add a clocked register always block.

        Args:
            reg: Register output signal name
            regIn: Register input signal name
            clk: Clock signal name
            inverted: Whether to invert the input
            indentLevel: The indentation level
        """
        inv = "~" if inverted else ""
        template = f"""
always @ (posedge {clk})
begin
    {reg} <= {inv}{regIn};
end
"""
        self._add(template, indentLevel)

    def addAssignScalar(
        self,
        left: str,
        right: str,
        delay: int = 0,  # noqa: ARG002
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a continuous assignment statement.

        Args:
            left: Left-hand side signal
            right: Right-hand side signal or expression
            delay: Delay (unused in Verilog implementation)
            inverted: Whether to invert the right-hand side of the expression
            inverted: Whether to invert the right-hand side
        """
        inv = "~" if inverted else ""
        if isinstance(right, list):
            self._add(f"assign {left} = {inv}{{{','.join(right)}}};", indentLevel)
        else:
            self._add(f"assign {left} = {inv}{right};")

    def addAssignVector(
        self,
        left: str,
        right: str,
        widthL: int | str,
        widthR: int | str,
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a vector slice assignment.

        Args:
            left: Left-hand side signal
            right: Right-hand side signal
            widthL: Upper bound of slice
            widthR: Lower bound of slice
            inverted: Whether to invert the right-hand side of the expression
            inverted: Whether to invert the right-hand side
        """
        inv = "~" if inverted else ""
        self._add(f"assign {left} = {inv}{right}[{widthL}:{widthR}];", indentLevel)

    def addPreprocIfDef(self, macro: str, indentLevel: int = 0) -> None:
        """Add an `ifdef` preprocessor directive.

        Args:
            macro: Macro name to check
            indentLevel: The indentation level
        """
        self._add(f"`ifdef {macro}", indentLevel)

    def addPreprocIfNotDef(self, macro: str, indentLevel: int = 0) -> None:
        """Add an `ifndef` preprocessor directive.

        Args:
            macro: Macro name to check
            indentLevel: The indentation level
        """
        self._add(f"`ifndef {macro}", indentLevel)

    def addPreprocElse(self, indentLevel: int = 0) -> None:
        """Add an `else` preprocessor directive.

        Args:
            indentLevel: The indentation level
        """
        self._add("`else", indentLevel)

    def addPreprocEndif(self, indentLevel: int = 0) -> None:
        """Add an `endif` preprocessor directive.

        Args:
            indentLevel: The indentation level
        """
        self._add("`endif", indentLevel)

    def addBelMapAttribute(
        self, configBitValues: list[tuple[str, int]], indentLevel: int = 0
    ) -> None:
        """Add the BEL mapping attribute as a Verilog attribute.

        Args:
            configBitValues: List of (name, count) pairs for configuration bits
            indentLevel: The indentation level
        """
        template = "(* FABulous, BelMap"
        bit_count = 0
        for value, count in configBitValues:
            for i in range(count):
                if i == 0:
                    template += f", {value}={bit_count}"
                else:
                    template += f", {value}_{i}={bit_count}"
                bit_count = bit_count + 1

        template += " *)\n"

        self._add(template, indentLevel)
