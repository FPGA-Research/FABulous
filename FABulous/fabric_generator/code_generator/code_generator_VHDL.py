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

        Parameters
        ----------
        comment : str
            The comment text to add
        onNewLine : bool
            Whether to add the comment on a new line
        end : str
            Additional text to append at the end
        indentLevel : int
            The indentation level for the comment
        """
        if onNewLine:
            self._add("")
        if self._content:
            self._content[-1] += f"{' ':<{indentLevel * 4}}" + f"-- {comment}{end}"
        else:
            self._add(f"{' ':<{indentLevel * 4}}" + f"-- {comment}{end}")

    def addHeader(self, name: str, package: str = "", indentLevel: int = 0) -> None:
        """Add VHDL entity header with standard libraries.

        Parameters
        ----------
        name : str
            Entity name
        package : str
            Additional package to include
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Entity name
        indentLevel : int
            The indentation level
        """
        self._add(f"end entity {name};", indentLevel)

    def addParameterStart(self, indentLevel: int = 0) -> None:
        """Start the generic parameter declaration section.

        Parameters
        ----------
        indentLevel : int
            The indentation level
        """
        self._add("Generic(", indentLevel)

    def addParameterEnd(self, indentLevel: int = 0) -> None:
        """End the generic parameter declaration section.

        Parameters
        ----------
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Parameter name
        storageType : str
            Parameter type
        value : str
            Default value
        indentLevel : int
            The indentation level
        """
        self._add(f"{name} : {storageType} := {value};", indentLevel)

    def addPortStart(self, indentLevel: int = 0) -> None:
        """Start the port declaration section.

        Parameters
        ----------
        indentLevel : int
            The indentation level
        """
        self._add("Port (", indentLevel)

    def addPortEnd(self, indentLevel: int = 0) -> None:
        """End the port declaration section.

        Parameters
        ----------
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Port name
        io : IO
            Input/output direction
        _reg : bool
            Register flag (unused in VHDL)
        attribute : str
            Additional attributes to add as a comment
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Port name
        io : IO
            Input/output direction
        msbIndex : int
            Most significant bit index
        _reg : bool
            Register flag (unused in VHDL)
        attribute : str
            Additional attributes to add as a comment
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Entity name
        indentLevel : int
            The indentation level
        """
        self._add(f"architecture Behavioral of {name} is", indentLevel)

    def addDesignDescriptionEnd(self, indentLevel: int = 0) -> None:
        """End the architecture declaration.

        Parameters
        ----------
        indentLevel : int
            The indentation level
        """
        self._add("end architecture Behavioral;", indentLevel)

    def addConstant(self, name: str, value: str, indentLevel: int = 0) -> None:
        """Add a constant declaration.

        Parameters
        ----------
        name : str
            Constant name
        value : str
            Constant value
        indentLevel : int
            The indentation level
        """
        self._add(f"constant {name} : STD_LOGIC := '{value}';", indentLevel)

    def addConnectionScalar(
        self, name: str, _reg: bool = False, indentLevel: int = 0
    ) -> None:
        """Add a scalar signal declaration.

        Parameters
        ----------
        name : str
            Signal name
        _reg : bool
            Register flag (unused in VHDL)
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        name : str
            Signal name
        startIndex : int
            Start index (MSB)
        _reg : bool
            Register flag (unused in VHDL)
        endIndex : int
            End index (LSB)
        indentLevel : int
            The indentation level
        """
        self._add(
            f"signal {name} : STD_LOGIC_VECTOR( {startIndex} downto {endIndex} );",
            indentLevel,
        )

    def addLogicStart(self, indentLevel: int = 0) -> None:
        """Start the logic section (begin statement).

        Parameters
        ----------
        indentLevel : int
            The indentation level
        """
        self._add("\nbegin\n", indentLevel)

    def addLogicEnd(self, indentLevel: int = 0) -> None:
        """End the logic section (end statement).

        Parameters
        ----------
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        reg : str
            Register output signal name
        regIn : str
            Register input signal name
        clk : str
            Clock signal name
        inverted : bool
            Whether to invert the input
        indentLevel : int
            The indentation level
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

        Parameters
        ----------
        left : str
            Left-hand side signal
        right : str
            Right-hand side signal or expression
        delay : int
            Delay in picoseconds
        indentLevel : int
            The indentation level
        inverted : bool
            Whether to invert the right-hand side
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

        Parameters
        ----------
        left : str
            Left-hand side signal
        right : str
            Right-hand side signal
        widthL : str | int
            Upper bound of slice
        widthR : str | int
            Lower bound of slice
        indentLevel : int
            The indentation level
        inverted : bool
            Whether to invert the right-hand side
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

        Parameters
        ----------
        compName : str
            Component name
        compInsName : str
            Instance name
        portsPairs : list[tuple[str, str]]
            List of (port, signal) pairs for port mapping
        paramPairs : list[tuple[str, str]] | None
            List of (parameter, value) pairs for generic mapping
        emulateParamPairs : list[tuple[str, str]] | None
            Additional parameters (unused)
        indentLevel : int
            The indentation level
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
        """Add a component declaration extracted from a VHDL file.

        Parameters
        ----------
        fileName : str | Path
            Path to the VHDL file to extract the component from.

        Returns
        -------
        int
            1 if the component uses configuration bits; 0 otherwise.
        """
        configPortUsed = 0
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

        Parameters
        ----------
        configBitCounter : int
            Total number of configuration bits.
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

        Parameters
        ----------
        indentLevel : int, optional
            The indentation level. Defaults to 0.
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
        """Define to keep parity with Verilog.

        VHDL does not support preprocessor directives.

        Parameters
        ----------
        _macro : str
            Macro name (unused).
        _indentLevel : int
            Indentation level (unused).

        Returns
        -------
        Never
            This function always raises an exception.

        Raises
        ------
        AssertionError
            Always, as VHDL doesn't support preprocessing.
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocIfNotDef(self, _macro: str, _indentLevel: int = 0) -> Never:
        """Define to keep parity with Verilog.

        VHDL does not support preprocessor directives.

        Parameters
        ----------
        _macro : str
            Macro name (unused).
        _indentLevel : int
            Indentation level (unused).

        Returns
        -------
        Never
            This function always raises an exception.

        Raises
        ------
        AssertionError
            Always, as VHDL doesn't support preprocessing.
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocElse(self, _indentLevel: int = 0) -> Never:
        """Define to keep parity with Verilog.

        VHDL does not support preprocessor directives.

        Parameters
        ----------
        _indentLevel : int
            Indentation level (unused).

        Returns
        -------
        Never
            This function always raises an exception.

        Raises
        ------
        AssertionError
            Always, as VHDL doesn't support preprocessing.
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addPreprocEndif(self, _indentLevel: int = 0) -> Never:
        """Define to keep parity with Verilog.

        VHDL does not support preprocessor directives.

        Parameters
        ----------
        _indentLevel : int
            Indentation level (unused).

        Returns
        -------
        Never
            This function always raises an exception.

        Raises
        ------
        AssertionError
            Always, as VHDL doesn't support preprocessing.
        """
        raise AssertionError("preprocessor not supported in VHDL")

    def addBelMapAttribute(
        self, configBitValues: list[tuple[str, int]], indentLevel: int = 0
    ) -> None:
        """Add the BEL mapping attribute as a VHDL comment.

        Parameters
        ----------
        configBitValues : list[tuple[str, int]]
            List of (name, count) pairs for configuration bits
        indentLevel : int
            The indentation level
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
