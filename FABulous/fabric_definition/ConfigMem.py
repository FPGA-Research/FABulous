"""Configuration memory definition module.

This module contains the ConfigMem class which represents configuration memory entries
for FPGA fabric tiles. Each entry maps configuration bits to frame locations for
bitstream generation.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, eq=True)
class ConfigMem:
    """Data structure to store the information about a config memory.

    Each structure represents a row of entries in the config memory CSV file.

    Attributes
    ----------
    frameName : str
        The name of the frame
    frameIndex : int
        The index of the frame
    bitsUsedInFrame : int
        The number of bits used in the frame
    usedBitMask : str
        The bit mask of the bits used in the frame
    configBitRanges : list[int]
        A list of config bit mapping values
    """

    frameName: str
    frameIndex: int
    bitsUsedInFrame: int
    usedBitMask: str
    configBitRanges: list[int] = field(default_factory=list)
