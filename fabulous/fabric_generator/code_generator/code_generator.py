"""The base class for all code generators."""

import abc
from pathlib import Path

from loguru import logger

from fabulous.fabric_definition.define import IO


class CodeGenerator(abc.ABC):
    """The base class for all code generators."""

    @property
    def outFileName(self) -> Path:
        """Get the output file path.

        Returns
        -------
        Path
            The output file path.
        """
        return self._outFileName

    @property
    def content(self) -> list[str]:
        """Get the content list.

        Returns
        -------
        list[str]
            List of content strings.
        """
        return self._content

    def __init__(self) -> None:
        self._content = []
        self._outFileName = Path()

    def writeToFile(self) -> None:
        """Write the content to the output file.

        Writes all content strings to the specified output file,
        filtering out `None` values. Clears content after writing.
        """
        if self._outFileName == Path():
            logger.critical("OutFileName is not set")
            exit(-1)
        with Path(self._outFileName).open("w") as f:
            self._content = [i for i in self._content if i is not None]
            f.write("\n".join(self._content))
        self._content = []

    @outFileName.setter
    def outFileName(self, outFileName: Path) -> None:
        """Set the output file path.

        Parameters
        ----------
        outFileName : Path
            The output file path to set.
        """
        self._outFileName = outFileName

    def _add(self, line: str, indentLevel: int = 0) -> None:
        """Add a line to the content with optional indentation.

        Parameters
        ----------
        line : str
            The line of code to add.
        indentLevel : int, optional
            The indentation level (each level = 4 spaces). Defaults to 0.
        """
        if indentLevel == 0:
            self._content.append(line)
        else:
            self._content.append(f"{' ':<{4 * indentLevel}}" + line)

    def popLastLine(self) -> str:
        """Remove and return the last line from content.

        Returns
        -------
        str
            The last line that was removed.
        """
        return self._content.pop()

    def addNewLine(self) -> None:
        """Add an empty line to the content."""
        self._add("")

    @abc.abstractmethod
    def addComment(
        self, comment: str, onNewLine: bool = False, end: str = "", indentLevel: int = 0
    ) -> None:
        """Add a comment to the code.

        Parameters
        ----------
        comment : str
            The comment text to add.
        onNewLine : bool, optional
            If True, put the comment on a new line. Defaults to False.
        end : str, optional
            The end token of the comment. Defaults to an empty string "".
        indentLevel : int, optional
            The level of indentation for the comment. Defaults to 0.

        Examples
        --------
        Verilog
            // **comment**

        VHDL
            -- **comment**
        """

    @abc.abstractmethod
    def addHeader(self, name: str, package: str = "", indentLevel: int = 0) -> None:
        """Add a header to the code.

        Parameters
        ----------
        name : str
            Name of the module.
        package : str, optional
            The package used by VHDL. Only useful with VHDL.
            Defaults to an empty string ''.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        ::

            Verilog
                module **name**
            VHDL
                library IEEE;
                use IEEE.std_logic_1164.all;
                use IEEE.NUMERIC_STD.ALL
                **package**
                entity **name** is
        """

    @abc.abstractmethod
    def addHeaderEnd(self, name: str, indentLevel: int = 0) -> None:
        """Add end to header. Only useful with VHDL.

        Parameters
        ----------
        name : str
            Name of the module.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        VHDL
            end entity **name**;
        """

    @abc.abstractmethod
    def addParameterStart(self, indentLevel: int = 0) -> None:
        """Add start of parameters.

        Parameters
        ----------
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            #(

        VHDL
            Generic(
        """

    @abc.abstractmethod
    def addParameterEnd(self, indentLevel: int = 0) -> None:
        """Add end of parameters.

        Parameters
        ----------
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            )

        VHDL
            );
        """

    @abc.abstractmethod
    def addParameter(
        self, name: str, storageType: str, value: str, indentLevel: int = 0
    ) -> None:
        """Add a parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        storageType : str
            Type of the parameter. Only useful with VHDL.
        value : str
            Value of the parameter.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            parameter **name** = **value**

        VHDL
            **name** : **type** := **value**;
        """

    @abc.abstractmethod
    def addPortStart(self, indentLevel: int = 0) -> None:
        """Add start of ports.

        Parameters
        ----------
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            (

        VHDL
            port (
        """

    @abc.abstractmethod
    def addPortEnd(self, indentLevel: int = 0) -> None:
        """Add end of ports.

        Parameters
        ----------
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            );

        VHDL
            );
        """

    @abc.abstractmethod
    def addPort(
        self,
        name: str,
        io: IO,
        *,
        width: int | str = 1,
        reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a port carrying `width` wires.

        An integer width of 1 declares a scalar, so references to it must use the
        bare name. An expression width always declares a vector.

        Parameters
        ----------
        name : str
            Name of the port.
        io : IO
            Direction of the port (input, output, inout).
        width : int | str
            Number of wires, or an HDL expression such as `NoConfigBits`.
            Defaults to 1.
        reg : bool
            Port is a register. Only useful with Verilog. Defaults to False.
        attribute : str
            Add a FABulous ATTRIBUTE to the port. Defaults to no attribute.
        indentLevel : int
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            **(* FABulous, ATTRIBUTE *)** **io** **reg** [**width**-1:0] **name**

        VHDL
            **name** : **io** STD_LOGIC_VECTOR(**width**-1 downto 0); **-- ATTRIBUTE**
        """

    @abc.abstractmethod
    def addDesignDescriptionStart(self, name: str, indentLevel: int = 0) -> None:
        """Add start of design description. Only useful with VHDL.

        Parameters
        ----------
        name : str
            Name of the module.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        VHDL
            architecture Behavioral of **name** is
        """

    @abc.abstractmethod
    def addDesignDescriptionEnd(self, indentLevel: int = 0) -> None:
        """Add end of design description.

        Parameters
        ----------
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            endmodule

        VHDL
            end architecture Behavioral
        """

    @abc.abstractmethod
    def addConstant(self, name: str, value: str, indentLevel: int = 0) -> None:
        """Add a constant.

        Parameters
        ----------
        name : str
            Name of the constant.
        value : str
            The value of the constant.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
            Verilog
                parameter **name** = **value**;

            VHDL
                constant **name** : STD_LOGIC := **value**;
        """

    @abc.abstractmethod
    def addConnection(
        self,
        name: str,
        *,
        width: int | str = 1,
        reg: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add a connection carrying `width` wires.

        An integer width of 1 declares a scalar, so references to it must use the
        bare name. An expression width always declares a vector.

        Parameters
        ----------
        name : str
            Name of the connection.
        width : int | str
            Number of wires, or an HDL expression such as `NoConfigBits`.
            Defaults to 1.
        reg : bool
            Connection is a register. Only useful with Verilog. Defaults to False.
        indentLevel : int
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            wire/reg [**width**-1:0] **name**;
        VHDL:
            signal **name** : STD_LOGIC_VECTOR( **width**-1 downto 0 );
        """

    @staticmethod
    def _msbIndex(width: int | str) -> int | str | None:
        """Return the MSB index of a declaration carrying `width` wires.

        Parameters
        ----------
        width : int | str
            Number of wires, or an HDL expression.

        Returns
        -------
        int | str | None
            `None` for an integer width of 1, which is declared as a scalar. An
            expression width always gives an index, because its value is only known
            at elaboration.

        Raises
        ------
        ValueError
            If `width` is an integer below 1.
        """
        if isinstance(width, str):
            return f"{width}-1"
        if width < 1:
            raise ValueError(f"A declaration needs at least one wire, got {width}.")
        if width == 1:
            return None
        return width - 1

    @staticmethod
    def _rangeSelect(
        high: int | str | None, low: int | str | None
    ) -> tuple[int | str, int | str] | int | str | None:
        """Classify the `right[high:low]` selection of `addAssign`.

        Parameters
        ----------
        high : int | str | None
            MSB of the selection.
        low : int | str | None
            LSB of the selection.

        Returns
        -------
        tuple[int | str, int | str] | int | str | None
            `None` for no selection, the index for a bit-select when the bounds are
            equal, otherwise `(high, low)`.

        Raises
        ------
        ValueError
            If only one of `high` and `low` is given.
        """
        if high is None and low is None:
            return None
        if high is None or low is None:
            raise ValueError(
                f"A range select needs both bounds, got high={high} and low={low}."
            )
        if high == low:
            return high
        return (high, low)

    @abc.abstractmethod
    def addLogicStart(self, indentLevel: int = 0) -> None:
        """Add start of logic. Only useful with VHDL.

        Parameters
        ----------
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            No equivalent construct.
        VHDL:
            begin
        """

    @abc.abstractmethod
    def addLogicEnd(self, indentLevel: int = 0) -> None:
        """Add end of logic. Only useful with VHDL.

        Examples
        --------
        VHDL:
            end

        Parameters
        ----------
        indentLevel : int, optional
            The indentation Level. Defaults to 0.
        """

    @abc.abstractmethod
    def addInstantiation(
        self,
        compName: str,
        compInsName: str,
        portsPairs: list[tuple[str, str]],
        paramPairs: list[tuple[str, str]] | None = None,
        emulateParamPairs: list[tuple[str, str]] | None = None,
        add_keep: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add an instantiation.

        Align ports and signals such that `ports[i]` corresponds to `signals[i]`
        for all indices i.

        This is also the same case for `paramPorts` and `paramSignals`.

        Parameters
        ----------
        compName : str
            Name of the component.
        compInsName : str
            Name of the component instance.
        portsPairs : list[tuple[str, str]]
            List of tuples pairing component ports with signals.
        paramPairs : list[tuple[str, str]] | None, optional
            List of tuples pairing parameter ports with parameter signals.
            Defaults to None.
        emulateParamPairs : list[tuple[str, str]] | None, optional
            List of parameter signals of the component in emulation mode only.
            Defaults to None.
        add_keep : bool, optional
            Whether to add a FABulous "keep" attribute to the instance.
            Defaults to False.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog:
            **compName** **compInsName** # (
                . **paramPairs[0]** (**paramSignals[0]**),
                . **paramPairs[1]** (**paramSignals[1]**),
                ...
                . **paramPairs[n]** (**paramSignals[n]**)
                ) (
                . **compPorts[0]** (**signals[0]**),
                . **compPorts[1]** (**signals[1]**),
                ...
                . **compPorts[n]** (**signals[n]**)
            );

        VHDL:
            **compInsName** : **compName**
                generic map (
                    **paramPairs[0]** => **paramSignals[0]**,
                    **paramPairs[1]** => **paramSignals[1]**,
                    ...
                    **paramPairs[i]** => **paramSignals[i]**
                )
                port map (
                    **compPorts[i]** => **signals[i]**,
                    **compPorts[i]** => **signals[i]**,
                    **compPorts[i]** => **signals[i]**
                );
        """

    @abc.abstractmethod
    def addComponentDeclarationForFile(self, fileName: str) -> int:
        """Add a component declaration for a file.

        Only usefull for VHDL. It copies the entity declaration
        from the specified VHDL file and replaces the entity with the component to
        ensure compatibility in VHDL code.

        Parameters
        ----------
        fileName : str
            Name of the VHDL file.

        Returns
        -------
        int
            1 if the component/file uses configuration bits, 0 otherwise.
        """

    @abc.abstractmethod
    def addShiftRegister(self, configBits: int, indentLevel: int = 0) -> None:
        """Add a shift register.

        Parameters
        ----------
        configBits : int
            The number of configuration bits.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.
        """

    @abc.abstractmethod
    def addFlipFlopChain(self, configBits: int, indentLevel: int = 0) -> None:
        """Add a flip flop chain.

        Parameters
        ----------
        configBits : int
            The number of configuration bits.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.
        """

    @abc.abstractmethod
    def addRegister(
        self,
        reg: str,
        regIn: str,
        clk: str = "CLK",
        inverted: bool = False,
        indentLevel: int = 0,
    ) -> None:
        r"""Add a register.

        Parameters
        ----------
        reg : str
            The name of the register.
        regIn : str
            The input signal of the register.
        clk : str, optional
            The clock signal of the register. Defaults to "UserCLK".
        inverted : bool, optional
            Invert the input signal. Defaults to False.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog:
        ::

            always @ (posedge **clk**)
            begin
                **reg** <= **inv** **regIn**;
            end

        VHDL:
        ::

            process(**clk**)
            begin
                if **clk**'event and **clk**='1' then
                        **reg** <= **inv** **regIn**;
                end if;
            end process;
        """

    @abc.abstractmethod
    def addAssign(
        self,
        left: str,
        right: str | list[str],
        *,
        high: int | str | None = None,
        low: int | str | None = None,
        delay: int = 0,
        inverted: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add an assign statement, optionally selecting `right[high:low]`.

        Equal bounds give a bit-select `right[high]`. The bounds are compared as
        Python values, so pass one bit as two equal values rather than two spellings
        of the same expression. Giving only one bound raises `ValueError`. Only VHDL
        emits `delay`.

        Parameters
        ----------
        left : str
            The left hand side of the assign statement.
        right : str | list[str]
            The right hand side of the assign statement. A list is concatenated.
        high : int | str | None
            MSB of the range selected from **right**. Defaults to no selection.
        low : int | str | None
            LSB of the range selected from **right**. Defaults to no selection.
        delay : int
            Delay in the assignment. Defaults to 0.
        inverted : bool
            Invert **right**. Defaults to False.
        indentLevel : int
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            assign **left** = **right**[**high**:**low**];

        VHDL:
            **left** <= **right**( **high** downto **low** ) after **delay** ps;
        """

    @abc.abstractmethod
    def addMuxAssign(
        self,
        output: str,
        inputVector: str,
        selectVector: str,
        selectLow: int,
        selectWidth: int,
        delay: int = 0,
        indentLevel: int = 0,
    ) -> None:
        """Assign a behavioral multiplexer output from a select slice.

        Drives **output** with the element of **inputVector** chosen by the
        ``selectWidth``-bit slice of **selectVector** starting at bit
        **selectLow**. Each backend emits the indexing in its own syntax: a
        Verilog vector index, a VHDL ``to_integer(unsigned(...))`` conversion.

        Parameters
        ----------
        output : str
            The signal driven with the selected input.
        inputVector : str
            The concatenated mux inputs being indexed.
        selectVector : str
            The vector holding the select bits (e.g. ``ConfigBits``).
        selectLow : int
            Index of the lowest select bit within **selectVector**.
        selectWidth : int
            Number of select bits.
        delay : int, optional
            Delay in the assignment. Defaults to 0.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            assign **output** = **inputVector**[**selectVector**[high:low]];

        VHDL:
            **output** <= **inputVector**(to_integer(unsigned(
            **selectVector**(high downto low)))) after **delay** ps;
        """

    @abc.abstractmethod
    def addPreprocIfDef(self, macro: str, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "ifdef".

        Parameters
        ----------
        macro : str
            The macro to check for.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            \`ifdef **macro**

        VHDL:
            unsupported
        """

    @abc.abstractmethod
    def addPreprocIfNotDef(self, macro: str, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "ifndef".

        Parameters
        ----------
        macro : str
            The macro to check for.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            \`ifndef **macro**

        VHDL:
            unsupported
        """

    @abc.abstractmethod
    def addPreprocElse(self, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "else".

        Parameters
        ----------
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            \`else

        VHDL:
            unsupported
        """

    @abc.abstractmethod
    def addPreprocEndif(self, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "endif".

        Parameters
        ----------
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            \`endif

        VHDL:
            unsupported
        """

    @abc.abstractmethod
    def addBelMapAttribute(
        self, configBitValues: list[tuple[str, int]], indentLevel: int = 0
    ) -> None:
        r"""Add a BelMap.

        Parameters
        ----------
        configBitValues : list[tuple[str, int]]
            The list of config bit value information.
            Each config bit should have a name and number of bits
            Should be sorted by number list is equal to NoConfigBits map.

        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
            input:
                list[("INIT", 3), ("FF", 1)]

            Verilog:
            ```
                (*FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2,FF=3 *)
            ```
            VHDL:
            ```
                -- (* FABulous, BelMap, INIT=0, INIT[1]=1, INIT[2]=2, FF=3 *)
            ```
        """
