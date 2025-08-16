"""The VHDL code generator."""

import math
import re
from pathlib import Path
from typing import Never

from FABulous.fabric_definition.define import IO
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator


class VHDLCodeGenerator(CodeGenerator):
    """The VHDL writer class.

    This is the template for generating VHDL code.
    """

    def addComment(
        self, comment: str, onNewLine: bool = False, end: str = "", indentLevel: int = 0
    ) -> None:
        """Add a VHDL comment to the generated code.

        Args:
            comment: The comment text to add
            onNewLine: Whether to add the comment on a new line
            end: Additional text to append at the end
            indentLevel: The indentation level for the comment
        """
        if onNewLine:
            self._add("")
        if self._content:
            self._content[-1] += f"{' ':<{indentLevel * 4}}" + f"-- {comment}{end}"
        else:
            self._add(f"{' ':<{indentLevel * 4}}" + f"-- {comment}{end}")

    def addHeader(self, name: str, package: str = "", indentLevel: int = 0) -> None:
        """Add VHDL entity header with standard libraries.

        Args:
            name: Entity name
            package: Additional package to include
            indentLevel: The indentation level
        """
        #   library template
        self._add("library IEEE;", indentLevel)
        self._add("use IEEE.STD_LOGIC_1164.ALL;", indentLevel)
        self._add("use IEEE.NUMERIC_STD.ALL;", indentLevel)
        self._add("use work.my_package.all;", indentLevel)
        if package != "":
            self._add(package, indentLevel)
        self._add(f"entity {name} is", indentLevel)

    def addHeaderEnd(self, name: str, indentLevel: int = 0) -> None:
        """Add the entity end statement.

        Args:
            name: Entity name
            indentLevel: The indentation level
        """
        self._add(f"end entity {name};", indentLevel)

    def addParameterStart(self, indentLevel: int = 0) -> None:
        """Start the generic parameter declaration section.

        Args:
            indentLevel: The indentation level
        """
        self._add("Generic(", indentLevel)

    def addParameterEnd(self, indentLevel: int = 0) -> None:
        """End the generic parameter declaration section.

        Args:
            indentLevel: The indentation level
        """
        temp = self._content.pop()
        if "--" in temp:
            temp2 = self._content.pop()[:-1]
            self._add(temp2)
            self._add(temp)
        else:
            self._add(temp[:-1])
        self._add(");", indentLevel)

    def addParameter(
        self, name: str, storageType: str, value: str, indentLevel: int = 0
    ) -> None:
        """Add a generic parameter declaration.

        Args:
            name: Parameter name
            storageType: Parameter type
            value: Default value
            indentLevel: The indentation level
        """
        self._add(f"{name} : {storageType} := {value};", indentLevel)

    def addPortStart(self, indentLevel: int = 0) -> None:
        """Start the port declaration section.

        Args:
            indentLevel: The indentation level
        """
        self._add("Port (", indentLevel)

    def addPortEnd(self, indentLevel: int = 0) -> None:
        """End the port declaration section.

        Args:
            indentLevel: The indentation level
        """

        def deSemiColon(x: str) -> str:
            cpos = x.rfind(";")
            assert cpos != -1, x
            return x[:cpos] + x[cpos + 1 :]

        temp = self._content.pop()
        if "--" in temp and ";" not in temp:
            temp2 = deSemiColon(self._content.pop())
            self._add(temp2)
            self._add(temp)
        else:
            self._add(deSemiColon(temp))
        self._add(");", indentLevel)

    def addPortScalar(
        self,
        name: str,
        io: IO,
        _reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a scalar port declaration.

        Args:
            name: Port name
            io: Input/output direction
            _reg: Register flag (unused in VHDL)
            attribute: Additional attributes to add as comment
            indentLevel: The indentation level
        """
        ioVHDL = ""
        if io.value.lower() == "input":
            ioVHDL = "in"
        elif io.value.lower() == "output":
            ioVHDL = "out"
        if attribute:
            attribute = f" -- {attribute}"
        self._add(
            f"{name:<10} : {ioVHDL} STD_LOGIC;{attribute}", indentLevel=indentLevel
        )

    def addPortVector(
        self,
        name: str,
        io: IO,
        msbIndex: int,
        _reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a vector port declaration.

        Args:
            name: Port name
            io: Input/output direction
            msbIndex: Most significant bit index
            _reg: Register flag (unused in VHDL)
            attribute: Additional attributes to add as comment
            indentLevel: The indentation level
        """
        ioVHDL = ""
        if io.value.lower() == "input":
            ioVHDL = "in"
        elif io.value.lower() == "output":
            ioVHDL = "out"
        if attribute:
            attribute = f" -- {attribute}"
        self._add(
            f"{name:<10} : {ioVHDL} STD_LOGIC_VECTOR( {msbIndex} downto 0 );"
            f"{attribute}",
            indentLevel=indentLevel,
        )

    def addDesignDescriptionStart(self, name: str, indentLevel: int = 0) -> None:
        """Start the architecture declaration.

        Args:
            name: Entity name
            indentLevel: The indentation level
        """
        self._add(f"architecture Behavioral of {name} is", indentLevel)

    def addDesignDescriptionEnd(self, indentLevel: int = 0) -> None:
        """End the architecture declaration.

        Args:
            indentLevel: The indentation level
        """
        self._add("end architecture Behavioral;", indentLevel)

    def addConstant(self, name: str, value: str, indentLevel: int = 0) -> None:
        """Add a constant declaration.

        Args:
            name: Constant name
            value: Constant value
            indentLevel: The indentation level
        """
        self._add(f"constant {name} : STD_LOGIC := '{value}';", indentLevel)

    def addConnectionScalar(
        self, name: str, _reg: bool = False, indentLevel: int = 0
    ) -> None:
        """Add a scalar signal declaration.

        Args:
            name: Signal name
            _reg: Register flag (unused in VHDL)
            indentLevel: The indentation level
        """
        self._add(f"signal {name} : STD_LOGIC;", indentLevel)

    def addConnectionVector(
        self,
        name: str,
        startIndex: int,
        _reg: bool = False,
        endIndex: int = 0,
        indentLevel: int = 0,
    ) -> None:
        """Add a vector signal declaration.

        Args:
            name: Signal name
            startIndex: Start index (MSB)
            _reg: Register flag (unused in VHDL)
            endIndex: End index (LSB)
            indentLevel: The indentation level
        """
        self._add(
            f"signal {name} : STD_LOGIC_VECTOR( {startIndex} downto {endIndex} );",
            indentLevel,
        )

    def addLogicStart(self, indentLevel: int = 0) -> None:
        """Start the logic section (begin statement).

        Args:
            indentLevel: The indentation level
        """
        self._add("\nbegin\n", indentLevel)

    def addLogicEnd(self, indentLevel: int = 0) -> None:
        """End the logic section (end statement).

        Args:
            indentLevel: The indentation level
        """
        self._add("\nend\n", indentLevel)

    def addRegister(
        self,
        reg: str,
        regIn: str,
        clk: str = "UserCLK",
        inverted: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add a clocked register process.

        Args:
            reg: Register output signal name
            regIn: Register input signal name
            clk: Clock signal name
            inverted: Whether to invert the input
            indentLevel: The indentation level
        """
        inv = "not " if inverted else ""
        template = f"""
process({clk})
begin
    if {clk}'event and {clk}='1' then
        {reg} <= {inv}{regIn};
    end if;
end process;
"""
        self._add(template, indentLevel)

    def addAssignScalar(
        self,
        left: str,
        right: str,
        delay: int = 0,
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a signal assignment statement.

        Args:
            left: Left-hand side signal
            right: Right-hand side signal or expression
            delay: Delay in picoseconds
            indentLevel: The indentation level
            inverted: Whether to invert the right-hand side
        """
        inv = "not " if inverted else ""
        if isinstance(right, list):
            self._add(
                f"{left} <= {inv}{' & '.join(right)} after {delay} ps;", indentLevel
            )
        else:
            left = (
                str(left).replace(":", " downto ").replace("[", "(").replace("]", ")")
            )
            right = (
                str(right).replace(":", " downto ").replace("[", "(").replace("]", ")")
            )
            self._add(f"{left} <= {inv}{right} after {delay} ps;", indentLevel)

    def addAssignVector(
        self,
        left: str,
        right: str,
        widthL: str | int,
        widthR: str | int,
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a vector slice assignment.

        Args:
            left: Left-hand side signal
            right: Right-hand side signal
            widthL: Upper bound of slice
            widthR: Lower bound of slice
            indentLevel: The indentation level
            inverted: Whether to invert the right-hand side
        """
        inv = "not " if inverted else ""
        self._add(f"{left} <= {inv}{right}( {widthL} downto {widthR} );", indentLevel)

    def addInstantiation(
        self,
        compName: str,
        compInsName: str,
        portsPairs: list[tuple[str, str]],
        paramPairs: list[tuple[str, str]] | None = None,
        emulateParamPairs: list[tuple[str, str]] | None = None,
        indentLevel: int = 0,
    ) -> None:
        """Add a component instantiation.

        Args:
            compName: Component name
            compInsName: Instance name
            portsPairs: List of (port, signal) pairs for port mapping
            paramPairs: List of (parameter, value) pairs for generic mapping
            emulateParamPairs: Additional parameters (unused)
            indentLevel: The indentation level
        """
        if emulateParamPairs is None:
            emulateParamPairs = []
        if paramPairs is None:
            paramPairs = []
        self._add(f"{compInsName} : {compName}", indentLevel=indentLevel)
        if paramPairs:
            connectPair = []
            self._add("generic map (", indentLevel=indentLevel + 1)
            for i in paramPairs:
                connectPair.append(f"{i[0]} => {i[1]}")
            self._add(
                (f",\n{' ':<{4 * (indentLevel + 2)}}").join(connectPair),
                indentLevel=indentLevel + 2,
            )
            self._add(")", indentLevel=indentLevel + 1)

        self._add("Port map(", indentLevel=indentLevel + 1)
        connectPair = []
        for p, s in portsPairs:
            # NOTE: This is a temporary fix for the issue of curly braces in the port
            # names and needs to be fixed properly a later refactoring of the code
            # generation
            port = p.replace("{", "(").replace("}", ")")
            signal = s.replace("{", "(").replace("}", ")")
            if "[" in port:
                port = port.replace("[", "(").replace("]", ")").replace(":", " downto ")
            if "[" in signal:
                signal = (
                    signal.replace("[", "(").replace("]", ")").replace(":", " downto ")
                )
            split = signal.split(",")
            if len(split) == 1:
                connectPair.append(f"{port} => {signal}")
            else:
                for idx, sn in zip(reversed(range(len(split))), split, strict=False):
                    connectPair.append(
                        f"{port}({idx}) => {sn.replace('(', '').replace(')', '')}"
                    )

        self._add(
            (f",\n{' ':<{4 * (indentLevel + 2)}}").join(connectPair),
            indentLevel=indentLevel + 2,
        )
        self._add(");", indentLevel=indentLevel + 1)
        self.addNewLine()

    def addComponentDeclarationForFile(self, fileName: str | Path) -> int:
        """Add component declaration extracted from VHDL file.

        Args:
            fileName: Path to the VHDL file to extract component from

        Returns
        -------
            1 if component uses configuration bits, 0 otherwise
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

        if result := re.search(
            r"^entity.*?end entity.*?;", data, flags=re.MULTILINE | re.DOTALL
        ):
            result = result.group(0)
            result = result.replace("entity", "component")
        resultList = []
        for i in result.splitlines():
            if "attribute" not in i:
                resultList.append(i)

        self._add("\n".join(resultList))
        self.addNewLine()
        return configPortUsed

    def addFlipFlopChain(self, configBitCounter: int) -> None:
        """Add a flip-flop chain for configuration bits.

        Args:
            configBitCounter: Total number of configuration bits
        """
        template = f"""
ConfigBitsInput <= ConfigBits(ConfigBitsInput'high-1 downto 0) & CONFin;
-- for k in 0 to Conf/2 generate
L: for k in 0 to {int(math.ceil(configBitCounter / 2.0)) - 1} generate
        inst_LHQD1a : LHQD1
        Port Map(
            D    => ConfigBitsInput(k*2),
            E    => CLK,
            Q    => ConfigBits(k*2) );
        inst_LHQD1b : LHQD1
        Port Map(
            D    => ConfigBitsInput((k*2)+1),
            E    => MODE,
            Q    => ConfigBits((k*2)+1) );
end generate;
CONFout <= ConfigBits(ConfigBits'high);
    """
        self._add(template)

    def addShiftRegister(self, indentLevel: int = 0) -> None:
        """Add a shift register for configuration bits.

        Args:
            indentLevel: The indentation level
        """
        template = """
-- the configuration bits shift register
process(CLK)
begin
    if CLK'event and CLK='1' then
        if mode='1' then    --configuration mode
            ConfigBits <= CONFin & ConfigBits(ConfigBits'high downto 1);
        end if;
    end if;
end process;
CONFout <= ConfigBits(ConfigBits'high);

    """
        self._add(template, indentLevel)

    def addPreprocIfDef(self, _macro: str, _indentLevel: int = 0) -> Never:
        """VHDL does not support preprocessor directives.

        Args:
            _macro: Macro name (unused)
            _indentLevel: Indentation level (unused)

        Raises
        ------
            AssertionError: Always, as VHDL doesn't support preprocessing
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocIfNotDef(self, _macro: str, _indentLevel: int = 0) -> Never:
        """VHDL does not support preprocessor directives.

        Args:
            _macro: Macro name (unused)
            _indentLevel: Indentation level (unused)

        Raises
        ------
            AssertionError: Always, as VHDL doesn't support preprocessing
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocElse(self, _indentLevel: int = 0) -> Never:
        """VHDL does not support preprocessor directives.

        Args:
            _indentLevel: Indentation level (unused)

        Raises
        ------
            AssertionError: Always, as VHDL doesn't support preprocessing
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocEndif(self, _indentLevel: int = 0) -> Never:
        """VHDL does not support preprocessor directives.

        Args:
            _indentLevel: Indentation level (unused)

        Raises
        ------
            AssertionError: Always, as VHDL doesn't support preprocessing
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addBelMapAttribute(
        self, configBitValues: list[tuple[str, int]], indentLevel: int = 0
    ) -> None:
        """Add BEL mapping attribute as VHDL comment.

        Args:
            configBitValues: List of (name, count) pairs for configuration bits
            indentLevel: The indentation level
        """
        template = "-- (* FABulous, BelMap"
        bit_count = 0
        for key, count in configBitValues:
            for i in range(count):
                if i == 0:
                    template += f", {key}={bit_count}"
                else:
                    template += f", {key}[{i}]={bit_count}"
                bit_count = bit_count + 1

        template += " *)\n"

        self._add(template, indentLevel)
