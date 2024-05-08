import math
import re
from typing import Literal

from FABulous.fabric_generator.code_generator import codeGenerator
from FABulous.fabric_definition.Fabric import IO, Bel, ConfigBitMode, Tile


class VerilogWriter(codeGenerator):
    """
    The writer class for generating Verilog code.
    """

    def addComment(self, comment, onNewLine=False, end="", indentLevel=0) -> None:
        if onNewLine:
            self._add("")
        if self._content:
            self._content[-1] += f"{' ':<{indentLevel*4}}" + f"//{comment}" f"{end}"
        else:
            self._add(f"{' ':<{indentLevel*4}}" + f"// {comment}" f"{end}")

    def addHeader(self, name, package="", indentLevel=0):
        self._add(f"module {name}", indentLevel)

    def addHeaderEnd(self, name, indentLevel=0):
        pass

    def addParameterStart(self, indentLevel=0):
        self._add(f"#(", indentLevel)

    def addParameterEnd(self, indentLevel=0):
        temp = self._content.pop()
        if "//" in temp:
            temp2 = self._content.pop()[:-1]
            self._add(temp2)
            self._add(temp)
        else:
            self._add(temp[:-1])
        self._add(")", indentLevel)

    def addParameter(self, name, type, value, indentLevel=0):
        if type.startswith("["):
            self._add(f"parameter {type} {name}={value},", indentLevel)
        else:
            self._add(f"parameter {name}={value},", indentLevel)

    def addPortStart(self, indentLevel=0):
        self._add(f"(", indentLevel)

    def addPortEnd(self, indentLevel=0):
        def deComma(x):
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

    def addPortScalar(self, name, io: IO, indentLevel=0):
        ioString = io.value.lower()
        self._add(f"{ioString} {name},", indentLevel)

    def addPortVector(self, name, io: IO, msbIndex, indentLevel=0):
        ioString = io.value.lower()
        self._add(f"{ioString} [{msbIndex}:0] {name},", indentLevel)

    def addDesignDescriptionStart(self, name, indentLevel=0):
        pass

    def addDesignDescriptionEnd(self, indentLevel=0):
        self._add("endmodule", indentLevel)

    def addConstant(self, name, value, indentLevel=0):
        self._add(f"parameter {name} = {value};", indentLevel)

    def addConnectionScalar(self, name, indentLevel=0):
        self._add(f"wire {name};", indentLevel)

    def addConnectionVector(self, name, startIndex, endIndex=0, indentLevel=0):
        self._add(f"wire[{startIndex}:{endIndex}] {name};", indentLevel)

    def addLogicStart(self, indentLevel=0):
        pass

    def addLogicEnd(self, indentLevel=0):
        pass

    def addInstantiation(
        self,
        compName,
        compInsName,
        portsPairs,
        paramPairs=[],
        emulateParamPairs=[],
        indentLevel=0,
    ):
        if paramPairs:
            port = [f".{i[0]}({i[1]})" for i in paramPairs]
            self._add(f"{compName}", indentLevel=indentLevel)
            self._add("#(", indentLevel=indentLevel + 1)
            self._add(
                (",\n" f"{' ':<{4*(indentLevel + 1)}}").join(port),
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
                (",\n" f"{' ':<{4*(indentLevel + 1)}}").join(port),
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
            if "(" in i[1]:
                tmp = i[1].replace("(", "[").replace(")", "]")
            else:
                tmp = i[1]
            connectPair.append(f".{i[0]}({tmp})")

        self._add(
            (",\n" f"{' ':<{4*(indentLevel + 1)}}").join(connectPair),
            indentLevel=indentLevel + 1,
        )
        self._add(");", indentLevel=indentLevel)
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

        return configPortUsed

    def addShiftRegister(self, configBits, indentLevel=0):
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

    def addFlipFlopChain(self, configBits, indentLevel=0):
        cfgBit = int(math.ceil(configBits / 2.0)) * 2
        template = f"""
    genvar k;
    assign ConfigBitsInput = {{ConfigBits[{cfgBit}-1-1:0], CONFin;}}
    // for k in 0 to Conf/2 generate
    for (k=0; k < {cfgBit-1}; k = k + 1) begin: L
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

    def addAssignScalar(self, left, right, delay=0, indentLevel=0):
        if type(right) == list:
            self._add(f"assign {left} = {{{','.join(right)}}};", indentLevel)
        else:
            self._add(f"assign {left} = {right};")

    def addAssignVector(self, left, right, widthL, widthR, indentLevel=0):
        self._add(f"assign {left} = {right}[{widthL}:{widthR}];", indentLevel)

    def addPreprocIfDef(self, macro, indentLevel=0):
        self._add(f"`ifdef {macro}", indentLevel)

    def addPreprocIfNotDef(self, macro, indentLevel=0):
        self._add(f"`ifndef {macro}", indentLevel)

    def addPreprocElse(self, indentLevel=0):
        self._add("`else", indentLevel)

    def addPreprocEndif(self, indentLevel=0):
        self._add("`endif", indentLevel)
