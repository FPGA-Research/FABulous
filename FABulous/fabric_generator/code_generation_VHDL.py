from typing import Literal, Tuple
import os
import math
import re

from fabric_generator.fabric import Fabric, Tile, Port, Bel, IO
from fabric_generator.code_generator import codeGenerator
from fabric_generator.fabric import ConfigBitMode


class VHDLWriter(codeGenerator):
    """
    The VHDL writer class. This is the template for generating VHDL code.

    """

    def addComment(self, comment, onNewLine=False, end="", indentLevel=0) -> None:
        if onNewLine:
            self._add("")
        if self._content:
            self._content[-1] += f"{' ':<{indentLevel*4}}" + f"-- {comment}" f"{end}"
        else:
            self._add(f"{' ':<{indentLevel*4}}" + f"-- {comment}" f"{end}")

    def addHeader(self, name, package="", indentLevel=0):
        #   library template
        self._add("library IEEE;", indentLevel)
        self._add("use IEEE.STD_LOGIC_1164.ALL;", indentLevel)
        self._add("use IEEE.NUMERIC_STD.ALL;", indentLevel)
        self._add("use work.my_package.all;", indentLevel)
        if package != "":
            self._add(package, indentLevel)
        self._add(f"entity {name} is", indentLevel)

    def addHeaderEnd(self, name, indentLevel=0):
        self._add(f"end entity {name}; ", indentLevel)

    def addParameterStart(self, indentLevel=0):
        self._add("Generic(", indentLevel)

    def addParameterEnd(self, indentLevel=0):
        temp = self._content.pop()
        if "--" in temp:
            temp2 = self._content.pop()[:-1]
            self._add(temp2)
            self._add(temp)
        else:
            self._add(temp[:-1])
        self._add(");", indentLevel)

    def addParameter(self, name, type, value, indentLevel=0):
        self._add(f"{name} : {type} := {value};", indentLevel)

    def addPortStart(self, indentLevel=0):
        self._add("Port (", indentLevel)

    def addPortEnd(self, indentLevel=0):
        def deSemiColon(x):
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

    def addPortScalar(self, name, io: IO, end=False, indentLevel=0):
        ioVHDL = ""
        if io.value.lower() == "input":
            ioVHDL = "in"
        elif io.value.lower() == "output":
            ioVHDL = "out"
        self._add(f"{name:<10} : {ioVHDL} STD_LOGIC;", indentLevel=indentLevel)

    def addPortVector(self, name, io: IO, msbIndex, indentLevel=0):
        ioVHDL = ""
        if io.value.lower() == "input":
            ioVHDL = "in"
        elif io.value.lower() == "output":
            ioVHDL = "out"
        self._add(
            f"{name:<10} : {ioVHDL} STD_LOGIC_VECTOR( {msbIndex} downto 0 );",
            indentLevel=indentLevel,
        )

    def addDesignDescriptionStart(self, name, indentLevel=0):
        self._add(f"architecture Behavioral of {name} is", indentLevel)

    def addDesignDescriptionEnd(self, indentLevel=0):
        self._add(f"end architecture Behavioral;", indentLevel)

    def addConstant(self, name, value, indentLevel=0):
        self._add(f"constant {name} : STD_LOGIC := '{value}';", indentLevel)

    def addConnectionScalar(self, name, indentLevel=0):
        self._add(f"signal {name} : STD_LOGIC;", indentLevel)

    def addConnectionVector(self, name, startIndex, endIndex=0, indentLevel=0):
        self._add(
            f"signal {name} : STD_LOGIC_VECTOR( { startIndex } downto {endIndex} );",
            indentLevel,
        )

    def addLogicStart(self, indentLevel=0):
        self._add("\n" f"begin" "\n", indentLevel)

    def addLogicEnd(self, indentLevel=0):
        self._add("\n" f"end" "\n", indentLevel)

    def addAssignScalar(self, left, right, delay=0, indentLevel=0):
        if type(right) == list:
            self._add(f"{left} <= {' & '.join(right)} after {delay} ps;", indentLevel)
        else:
            left = (
                str(left).replace(":", " downto ").replace("[", "(").replace("]", ")")
            )
            right = (
                str(right).replace(":", " downto ").replace("[", "(").replace("]", ")")
            )
            self._add(f"{left} <= {right} after {delay} ps;", indentLevel)

    def addAssignVector(self, left, right, widthL, widthR, indentLevel=0):
        self._add(f"{left} <= {right}( {widthL} downto {widthR} );", indentLevel)

    def addInstantiation(
        self,
        compName,
        compInsName,
        portsPairs,
        paramPairs=[],
        emulateParamPairs=[],
        indentLevel=0,
    ):
        self._add(f"{compInsName} : {compName}", indentLevel=indentLevel)
        if paramPairs:
            connectPair = []
            self._add(f"generic map (", indentLevel=indentLevel + 1)
            for i in paramPairs:
                connectPair.append(f"{i[0]} => {i[1]}")
            self._add(
                (",\n" f"{' ':<{4*(indentLevel + 2)}}").join(connectPair),
                indentLevel=indentLevel + 2,
            )
            self._add(f")", indentLevel=indentLevel + 1)

        self._add(f"Port map(", indentLevel=indentLevel + 1)
        connectPair = []
        for i in portsPairs:
            if "[" in i[0]:
                port = i[0].replace("[", "(").replace("]", ")").replace(":", " downto ")
            else:
                port = i[0]
            if "[" in i[1]:
                signal = (
                    i[1].replace("[", "(").replace("]", ")").replace(":", " downto ")
                )
            else:
                signal = i[1]
            connectPair.append(f"{port} => {signal}")

        self._add(
            (",\n" f"{' ':<{4*(indentLevel + 2)}}").join(connectPair),
            indentLevel=indentLevel + 2,
        )
        self._add(");", indentLevel=indentLevel + 1)
        self.addNewLine()

    def addComponentDeclarationForFile(self, fileName):
        configPortUsed = 0  # 1 means is used
        with open(fileName, "r") as f:
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

        self._add(result)
        self.addNewLine()
        return configPortUsed

    def addFlipFlopChain(self, configBitCounter):
        template = f"""
ConfigBitsInput <= ConfigBits(ConfigBitsInput'high-1 downto 0) & CONFin;
-- for k in 0 to Conf/2 generate
L: for k in 0 to {int(math.ceil(configBitCounter/2.0))-1} generate
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

    def addShiftRegister(self, indentLevel=0):
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

    def addPreprocIfDef(self, macro, indentLevel=0):
        assert False, "preprocessor not supported in VHDL"

    def addPreprocIfNotDef(self, macro, indentLevel=0):
        assert False, "preprocessor not supported in VHDL"

    def addPreprocElse(self, indentLevel=0):
        assert False, "preprocessor not supported in VHDL"

    def addPreprocEndif(self, indentLevel=0):
        assert False, "preprocessor not supported in VHDL"
