import abc
from pathlib import Path

from loguru import logger

from FABulous.fabric_definition.enum_and_type import IO


class CodeGenerator(abc.ABC):
    """The base class for all code generators."""

    @property
    def outFileName(self) -> Path:
        return self._outFileName

    @property
    def content(self) -> list[str]:
        return self._content

    def __init__(self) -> None:
        self._content = []
        self._outFileName = Path()

    def writeToFile(self) -> None:
        if self._outFileName == Path():
            logger.critical("OutFileName is not set")
            exit(-1)
        with Path(self._outFileName).open("w") as f:
            self._content = [i for i in self._content if i is not None]
            f.write("\n".join(self._content))
        self._content = []

    @outFileName.setter
    def outFileName(self, outFileName: Path) -> None:
        self._outFileName = outFileName

    def _add(self, line: str, indentLevel: int = 0) -> None:
        if indentLevel == 0:
            self._content.append(line)
        else:
            self._content.append(f"{' ':<{4 * indentLevel}}" + line)

    def popLastLine(self) -> str:
        return self._content.pop()

    def addNewLine(self) -> None:
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
            The package used by VHDL. Only useful with VHDL. Defaults to an empty string ''.
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
    def addPortScalar(
        self,
        name: str,
        io: IO,
        reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a scalar port.

        Parameters
        ----------
        name : str
            Name of the port.
        io : IO
            Direction of the port (input, output, inout).
        reg: bool, optional
            port is a register. Only useful with Verilog.
        attribute: str, optional
            Add a FABulous ATTRIBUTE to the port.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            **(* FABulous, ATTRIBUTE *)** **io** **reg** **name**

        VHDL
            **name** : **io** STD_LOGIC; **-- ATTRIBUTE**
        """

    @abc.abstractmethod
    def addPortVector(
        self,
        name: str,
        io: IO,
        msbIndex: str | int,
        reg: bool = False,
        attribute: str = "",
        indentLevel: int = 0,
    ) -> None:
        """Add a vector port.

        Parameters
        ----------
        name : str
            Name of the port.
        io : IO
            Direction of the port (input, output, inout).
        msbIndex : int or str
            Index of the MSB of the vector. Can be a string.
        reg: bool, optional
            port is a register. Only useful with Verilog.
        attribute: str, optional
            Add a FABulous ATTRIBUTE to the port.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            **(* FABulous, ATTRIBUTE *)** **io** **reg** [**msbIndex**:0] **name**

        VHDL
            **name** : **io** STD_LOGIC_VECTOR(**msbIndex** downto 0); **-- ATTRIBUTE**
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
        value :
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
    def addConnectionScalar(
        self, name: str, reg: bool = False, indentLevel: int = 0
    ) -> None:
        """Add a scalar connection.

        Parameters
        ----------
        name : str
            Name of the connection
        reg : bool, optional
            Connection is a register. Only useful with Verilog.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            wire/reg **name**;
        VHDL:
            signal **name** : STD_LOGIC;
        """

    @abc.abstractmethod
    def addConnectionVector(
        self,
        name: str,
        startIndex: str | int,
        endIndex: str | int = 0,
        reg: bool = False,
        indentLevel: int = 0,
    ) -> None:
        """Add a vector connection.

        Parameters
        ----------
        name : str
            Name of the connection
        startIndex : str
            Start index of the vector. Can be a string.
        endIndex : int, optional
            End index of the vector. Can be a string. Defaults to 0.
        reg : bool, optional
            Connection is a register. Only useful with Verilog.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            wire/reg [**startIndex**:**end**] **name**;
        VHDL:
            signal **name** : STD_LOGIC_VECTOR( **startIndex** downto **endIndex** );
        """

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
        indentLevel: int = 0,
    ) -> None:
        """Add an instantiation. This will line up the ports and signals. So ports[0]
        will have signals[0] and so on. This is also the same case for paramPorts and
        paramSignals.

        Parameters
        ----------
        compName : str
            Name of the component.
        compInsName : str
            Name of the component instance.
        portsPairs : List[Tuple[str, str]]
            List of tuples pairing component ports with signals.
        paramPairs : List[Tuple[str, str]], optional
            List of tuples pairing parameter ports with parameter signals. Defaults to [].
        emulateParamPairs : List[Tuple[str, str]], optional
            List of parameter signals of the component in emulation mode only. Defaults to [].
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
        -------
        ::

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

        VHDL
        ----
        ::

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
    def addAssignScalar(
        self,
        left: str,
        right: str,
        delay: int = 0,
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a scalar assign statement. Delay is provided by currently not being used
        by any of the code generator. If **right** is a list, it will be concatenated.
        Verilog will concatenate with comma ','. VHDL will concatenate with ampersand
        '&' instead.

        Parameters
        ----------
        left : object
            The left hand side of the assign statement.
        right : object
            The right hand side of the assign statement.
        delay : int, optional
            Delay in the assignment. Defaults to 0.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.
        inverted : bool, optional
            Invert **right**. Default False.

        Examples
        --------
        Verilog
        -------
        assign **left** = **right**;

        VHDL
        ----
        **left** <= **right** after **delay** ps;
        """

    @abc.abstractmethod
    def addAssignVector(
        self,
        left: str,
        right: str,
        widthL: str | int,
        widthR: str | int,
        indentLevel: int = 0,
        inverted: bool = False,
    ) -> None:
        """Add a vector assign statement.

        Parameters
        ----------
        left : object
            The left hand side of the assign statement.
        right : object
            The right hand side of the assign statement.
        widthL : object
            The start index of the vector. Can be a string.
        widthR : object
            The end index of the vector. Can be a string.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.
        inverted : bool, optional
            Invert **right**. Default False.

        Examples
        --------
        Verilog
        -------
        assign **left** = **right** [**widthL**:**widthR**];

        VHDL
        ----
        **left** <= **right** ( **widthL** downto *widthR* );
        """

    @abc.abstractmethod
    def addPreprocIfDef(self, macro: str, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "ifdef".

        Parameters
        ----------
        macro : object
            The macro to check for.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog
        -------
        \`ifdef **macro**

        VHDL
        ----
        unsupported
        """

    @abc.abstractmethod
    def addPreprocIfNotDef(self, macro: str, indentLevel: int = 0) -> None:
        r"""Add a preprocessor "ifndef".

        Parameters
        ----------
        macro : object
            The macro to check for.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog
        -------
        \`ifndef **macro**

        VHDL
        ----
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
        Verilog
        -------
        \`else

        VHDL
        ----
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
        Verilog
        -------
        \`endif

        VHDL
        ----
        unsupported
        """

    @abc.abstractmethod
    def addBelMapAttribute(
        self, configBitValues: list[tuple[str, int]], indentLevel: int = 0
    ) -> None:
        r"""Add a BelMap.

        Parameters
        ----------
        configBits: list[tuple[str,int]]
            The list of config bit value information.
            Each config bit should have a name and number of bits
            Should be sorted by number list is equal to NoConfigBits map.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        configBitValues input:
        ::

            List[("INIT",3),("FF",1)]

        Verilog:
        ::

            (*FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2,FF=3 *)

        VHDL:
        ::

            -- (* FABulous, BelMap, INIT=0, INIT[1]=1, INIT[2]=2, FF=3 *)
        """
