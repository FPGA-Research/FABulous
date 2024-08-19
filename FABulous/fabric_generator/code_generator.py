import abc
from loguru import logger
from typing import List, Tuple

from FABulous.fabric_definition.Fabric import IO, Bel, ConfigBitMode


class codeGenerator(abc.ABC):
    """
    The base class for all code generators.
    """

    @property
    def outFileName(self):
        return self._outFileName

    @property
    def content(self):
        return self._content

    def __init__(self):
        self._content = []

    def writeToFile(self):
        if self._outFileName == "":
            logger.critical("OutFileName is not set")
            exit(-1)
        with open(self._outFileName, "w") as f:
            self._content = [i for i in self._content if i is not None]
            f.write("\n".join(self._content))
        self._content = []

    @outFileName.setter
    def outFileName(self, outFileName):
        self._outFileName = outFileName

    def _add(self, line, indentLevel=0) -> None:
        if indentLevel == 0:
            self._content.append(line)
        else:
            self._content.append(f"{' ':<{4*indentLevel}}" + line)

    def popLastLine(self) -> str:
        return self._content.pop()

    def addNewLine(self):
        self._add("")

    @abc.abstractmethod
    def addComment(self, comment: str, onNewLine=False, end="", indentLevel=0) -> None:
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
        pass

    @abc.abstractmethod
    def addHeader(self, name: str, package="", indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addHeaderEnd(self, name: str, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addParameterStart(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addParameterEnd(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addParameter(self, name: str, type, value, indentLevel=0):
        """Add a parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        type : str
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
        pass

    @abc.abstractmethod
    def addPortStart(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addPortEnd(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addPortScalar(self, name: str, io: IO, indentLevel=0):
        """Add a scalar port.

        Parameters
        ----------
        name : str
            Name of the port.
        io : IO
            Direction of the port (input, output, inout).
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            **io** **name**

        VHDL
            **name** : **io** STD_LOGIC;
        """
        pass

    @abc.abstractmethod
    def addPortVector(self, name: str, io: IO, msbIndex, indentLevel=0):
        """Add a vector port.

        Parameters
        ----------
        name : str
            Name of the port.
        io : IO
            Direction of the port (input, output, inout).
        msbIndex : int or str
            Index of the MSB of the vector. Can be a string.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.

        Examples
        --------
        Verilog
            **io** [**msbIndex**:0] **name**

        VHDL
            **name** : **io** STD_LOGIC_VECTOR(**msbIndex** downto 0);
        """
        pass

    @abc.abstractmethod
    def addDesignDescriptionStart(self, name: str, indentLevel=0):
        """
        Add start of design description. Only useful with VHDL.

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
        pass

    @abc.abstractmethod
    def addDesignDescriptionEnd(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addConstant(self, name: str, value, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addConnectionScalar(self, name: str, indentLevel=0):
        """Add a scalar connection.

        Parameters
        ----------
        name : str
            Name of the connection
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            wire **name**;
        VHDL:
            signal **name** : STD_LOGIC;
        """
        pass

    @abc.abstractmethod
    def addConnectionVector(self, name: str, startIndex, endIndex=0, indentLevel=0):
        """Add a vector connection.

        Parameters
        ----------
        name : str
            Name of the connection
        startIndex : str
            Start index of the vector. Can be a string.
        endIndex : int, optional
            End index of the vector. Can be a string. Defaults to 0.
        indentLevel : int, optional
            The indentation Level. Defaults to 0.

        Examples
        --------
        Verilog:
            wire [**startIndex**:**end**] **name**;
        VHDL:
            signal **name** : STD_LOGIC_VECTOR( **startIndex** downto **endIndex** );
        """
        pass

    @abc.abstractmethod
    def addLogicStart(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addLogicEnd(self, indentLevel=0):
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
        pass

    @abc.abstractmethod
    def addInstantiation(
        self,
        compName: str,
        compInsName: str,
        portsPairs: List[Tuple[str, str]],
        paramPairs: List[Tuple[str, str]] = [],
        emulateParamPairs: List[Tuple[str, str]] = [],
        indentLevel=0,
    ):
        """Add an instantiation. This will line up the ports and signals.
        So ports[0] will have signals[0] and so on. This is also the same case for paramPorts and paramSignals.

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
        pass

    @abc.abstractmethod
    def addComponentDeclarationForFile(self, fileName: str):
        """Add a component declaration for a file.

        Only usefull for VHDL. It copies the entity declaration
        from the specified VHDL file and replaces the entity with the component to
        ensure compatibility in VHDL code.

        Parameters
        ----------
        fileName : str
            Name of the VHDL file.
        """
        pass

    @abc.abstractmethod
    def addShiftRegister(self, configBits: int, indentLevel=0):
        """Add a shift register.

        Parameters
        ----------
        configBits : int
            The number of configuration bits.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addFlipFlopChain(self, configBits: int, indentLevel=0):
        """Add a flip flop chain.

        Parameters
        ----------
        configBits : int
            The number of configuration bits.
        indentLevel : int, optional
            The level of indentation. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addAssignScalar(self, left, right, delay=0, indentLevel=0):
        """Add a scalar assign statement.

        Delay is provided but currently not used by any of the code generators.
        If **right** is a list, it will be concatenated.
        Verilog will concatenate with comma ','.
        VHDL will concatenate with ampersand '&' instead.

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

        Examples
        --------
        Verilog
        -------
        assign **left** = **right**;

        VHDL
        ----
        **left** <= **right** after **delay** ps;
        """
        pass

    @abc.abstractmethod
    def addAssignVector(self, left, right, widthL, widthR, indentLevel=0):
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

        Examples
        --------
        Verilog
        -------
        assign **left** = **right** [**widthL**:**widthR**];

        VHDL
        ----
        **left** <= **right** ( **widthL** downto *widthR* );
        """
        pass

    @abc.abstractmethod
    def addPreprocIfDef(self, macro, indentLevel=0):
        """Add a preprocessor "ifdef".

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
        pass

    @abc.abstractmethod
    def addPreprocIfNotDef(self, macro, indentLevel=0):
        """Add a preprocessor "ifndef".

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
        pass

    @abc.abstractmethod
    def addPreprocElse(self, indentLevel=0):
        """Add a preprocessor "else".

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
        pass

    @abc.abstractmethod
    def addPreprocEndif(self, indentLevel=0):
        """
        Add a preprocessor "endif".

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
        pass
