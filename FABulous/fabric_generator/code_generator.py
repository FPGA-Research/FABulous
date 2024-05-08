import abc
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
            print("OutFileName is not set")
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
        """
        Add a comment to the code.

        Examples :
            | Verilog: // **comment**
            | VHDL : -- **comment**

        Args:
            comment (str): The comment
            onNewLine (bool, optional): If true put the comment on a new line. Defaults to False.
            end (str, optional): The end token of the comment. Defaults to "".
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addHeader(self, name: str, package="", indentLevel=0):
        """
        Add a header to the code.

        Examples :
            | Verilog: module **name**
            | VHDL: library IEEE;
            |       use IEEE.std_logic_1164.all;
            |       use IEEE.NUMERIC_STD.ALL
            |       **package**
            |       entity **name** is

        Args:
            name (str): name of the module
            package (str, optional): The package used by VHDL. Only useful with VHDL. Defaults to ''.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addHeaderEnd(self, name: str, indentLevel=0):
        """
        Add end to header. Only useful with VHDL.

        Examples :
            | Verilog:
            | VHDL: end entity **name**;

        Args:
            name (str): name of the module
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addParameterStart(self, indentLevel=0):
        """
        Add start of parameters.

        Examples :
            | Verilog: #(
            | VHDL: Generic(

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addParameterEnd(self, indentLevel=0):
        """
        Add end of parameters.

        Examples :
            | Verilog: )
            | VHDL: );

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addParameter(self, name: str, type, value, indentLevel=0):
        """
        Add a parameter.

        Examples :
            | Verilog: parameter **name** = **value**
            | VHDL: **name** : **type** := **value**;

        Args:
            name (str): name of the parameter
            type (_type_): type of the parameter. Only useful with VHDL.
            value (_type_): value of the parameter.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPortStart(self, indentLevel=0):
        """
        Add start of ports.

        Examples :
            | Verilog: (
            | VHDL: port (

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPortEnd(self, indentLevel=0):
        """
        Add end of ports.

        Examples :
            | Verilog: );
            | VHDL: );

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPortScalar(self, name: str, io: IO, indentLevel=0):
        """
        Add a scalar port.

        Examples :
            | Verilog: **io** **name**
            | VHDL: **name** : **io** STD_LOGIC;

        Args:
            name (str): name of the port
            io (IO): direction of the port (input, output, inout)
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPortVector(self, name: str, io: IO, msbIndex, indentLevel=0):
        """
        Add a vector port.

        Examples :
            | Verilog: **io** [**msbIndex**:0] **name**
            | VHDL: **name** : **io** STD_LOGIC_VECTOR( **msbIndex** downto 0 );

        Args:
            name (str): name of the port
            io (IO): direction of the port (input, output, inout)
            msbIndex (int): index of the MSB of the vector. Can be a string
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addDesignDescriptionStart(self, name: str, indentLevel=0):
        """
        Add start of design description. Only useful with VHDL.

        Examples :
            | Verilog:
            | VHDL: architecture Behavioral of **name** is


        Args:
            name (str): name of the module
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addDesignDescriptionEnd(self, indentLevel=0):
        """
        Add end of design description.

        Examples :
            | Verilog: endmodule
            | VHDL: end architecture Behavioral

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addConstant(self, name: str, value, indentLevel=0):
        """
        Add a constant.

        Examples :
            | Verilog: parameter **name** = **value**;
            | VHDL: constant **name** : STD_LOGIC := **value**;

        Args:
            name (str): name of the constant
            value : The value of the constant.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addConnectionScalar(self, name: str, indentLevel=0):
        """
        Add a scalar connection.

        Examples :
            | Verilog: wire **name**;
            | VHDL: signal **name** : STD_LOGIC;

        Args:
            name (str): name of the connection
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addConnectionVector(self, name: str, startIndex, endIndex=0, indentLevel=0):
        """
        Add a vector connection.

        Examples :
            | Verilog: wire [**startIndex**:**end**] **name**;
            | VHDL: signal **name** : STD_LOGIC_VECTOR( **startIndex** downto **endIndex** );

        Args:
            name (str): name of the connection
            startIndex : Start index of the vector. Can be a string.
            endIndex (int, optional): End index of the vector. Can be a string. Defaults to 0.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addLogicStart(self, indentLevel=0):
        """
        Add start of logic. Only useful with VHDL.

        Examples :
            | Verilog:
            | VHDL: begin

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addLogicEnd(self, indentLevel=0):
        """
        Add end of logic. Only useful with VHDL.

        Examples :
            | Verilog:
            | VHDL: end

        Args:
            indentLevel (int, optional): The indentation Level. Defaults to 0.
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
        """
        Add an instantiation. This will line up the ports and signals. So ports[0] will have signals[0] and so on. This is also the same case for paramPorts and paramSignals.

        Examples :
            | Verilog: **compName** **compInsName** # (
            |             . **paramPorts[0]** (**paramSignals[0]**),
            |             . **paramPorts[1]** (**paramSignals[1]**),
            |             ...
            |             . **paramPorts[n]** (**paramSignals[n]**)
            |             ) (
            |             . **compPorts[0]** (**signals[0]**),
            |             . **compPorts[1]** (**signals[1]**),
            |             ...
            |             . **compPorts[n]** (**signals[n]**)
            |         );
            | VHDL: compInsName : compName
            |         generic map (
            |             **paramPorts[0]** => **paramSignals[0]**,
            |             **paramPorts[1]** => **paramSignals[1]**,
            |             ...
            |             **paramPorts[i]** => **paramSignals[i]**
            |         );
            |         Port map (
            |             **compPorts[i]** => **signals[i]**,
            |             **compPorts[i]** => **signals[i]**,
            |             **compPorts[i]** => **signals[i]**
            |         );



        Args:
            compName (str): name of the component
            compInsName (str): name of the component instance
            compPorts (List[str]): list of ports of the component
            signals (List[str]): list of signals of the component
            paramPorts (List[str], optional): list of parameter ports of the component. Defaults to [].
            paramSignals (List[str], optional): list of parameter signals of the component. Defaults to [].
            emulateParamPairs (List[str], optional): list of parameter signals of the component in emulation mode only. Defaults to [].
            indentLevel (int, optional): The indentation Level. Defaults to 0.

        Raises:
            ValueError: If the number of compPorts and signals are not equal.
            ValueError: If the number of paramPorts and paramSignals are not equal.
        """
        pass

    @abc.abstractmethod
    def addComponentDeclarationForFile(self, fileName: str):
        """
        Add a component declaration for a file. Only useful with VHDL. Will copy the entity of the file, and replacing the entity with component for VHDL to work.

        Args:
            fileName (str): name of the VHDL file
        """
        pass

    @abc.abstractmethod
    def addShiftRegister(self, configBits: int, indentLevel=0):
        """
        Add a shift registers.

        Args:
            configBits (int): the number of config bits
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addFlipFlopChain(self, configBits: int, indentLevel=0):
        """
        Add a flip flop chain.

        Args:
            configBits (int): the number of config bits
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addAssignScalar(self, left, right, delay=0, indentLevel=0):
        """
        Add a scalar assign statement. Delay is provided by currently not being used by any of the code generator.
        If **right** is a list, it will be concatenated.
        Verilog will be concatenated with comma ','.
        VHDL will be concatenated with ampersand '&'.

        Examples :
            | Verilog: assign **left** = **right**;
            | VHDL: **left** <= **right** after **delay** ps;

        Args:
            left : The left hand side of the assign statement.
            right : The right hand side of the assign statement.
            delay (int, optional): delay in the assignment. Defaults to 0.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addAssignVector(self, left, right, widthL, widthR, indentLevel=0):
        """
        Add a vector assign statement.

        Examples :
            | Verilog: assign **left** = **right** [**widthL**:**widthR**];
            | VHDL: **left** <= **right** ( **widthL** downto *widthR* );

        Args:
            left : The left hand side of the assign statement.
            right : The right hand side of the assign statement.
            widthL : The start index of the vector. Can be a string.
            widthR : The end index of the vector. Can be a string.
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPreprocIfDef(self, macro, indentLevel=0):
        """
        Add a preprocessor "ifdef"

        Examples :
            | Verilog: \`ifdef **macro**
            | VHDL: unsupported

        Args:
            macro : The macro to check for
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPreprocIfNotDef(self, macro, indentLevel=0):
        """
        Add a preprocessor "ifndef"

        Examples :
            | Verilog: \`ifndef **macro**
            | VHDL: unsupported

        Args:
            macro : The macro to check for
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPreprocElse(self, indentLevel=0):
        """
        Add a preprocessor "else"

        Examples :
            | Verilog: \`else
            | VHDL: unsupported

        Args:
            macro : The macro to check for
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass

    @abc.abstractmethod
    def addPreprocEndif(self, indentLevel=0):
        """
        Add a preprocessor "endif"

        Examples :
            | Verilog: \`endif
            | VHDL: unsupported

        Args:
            macro : The macro to check for
            indentLevel (int, optional): The indentation Level. Defaults to 0.
        """
        pass
