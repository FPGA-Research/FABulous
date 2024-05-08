from dataclasses import dataclass, field


@dataclass(frozen=True, eq=True)
class ConfigMem:
    """
    Data structure to store the information about a config memory. Each structure represent a row of entry in the config memory csv file.

    Attributes:
        frameName (str) : The name of the frame
        frameIndex (int) : The index of the frame
        bitUsedInFrame (int) : The number of bits used in the frame
        usedBitMask (int) : The bit mask of the bits used in the frame
        configBitRanges (List[int]) : A list of config bit mapping values
    """

    frameName: str
    frameIndex: int
    bitsUsedInFrame: int
    usedBitMask: str
    configBitRanges: list[int] = field(default_factory=list)
