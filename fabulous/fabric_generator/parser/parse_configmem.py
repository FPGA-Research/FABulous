"""Configuration memory parser for FABulous FPGA tiles.

`ConfigMem.from_csv` reads the file and `ConfigMem.validate` checks it against
the fabric's frame parameters; this module keeps the one-call form the
generators and tests use, returning the frames that hold bits.
"""

from pathlib import Path

from fabulous.fabric_definition.configmem import ConfigMem, ConfigMemFrame


def parseConfigMem(
    fileName: Path,
    maxFramePerCol: int,
    frameBitPerRow: int,
    globalConfigBits: int,
) -> list[ConfigMemFrame]:
    """Parse the config memory CSV file into the frames that hold bits.

    `ConfigMem.from_csv` rejects a malformed file and `ConfigMem.validate` one
    that does not fit the frame parameters, both with a ValueError.

    Parameters
    ----------
    fileName : Path
        Directory of the config memory CSV file
    maxFramePerCol : int
        Maximum number of frames per column
    frameBitPerRow : int
        Number of bits per row
    globalConfigBits : int
        Number of configuration bits the config memory must cover

    Returns
    -------
    list[ConfigMemFrame]
        The frames of the config memory CSV file that hold at least one bit.
    """
    memory = ConfigMem.from_csv(fileName).validate(
        frame_bits_per_row=frameBitPerRow,
        max_frames_per_col=maxFramePerCol,
        config_bits=globalConfigBits,
    )
    return list(memory.used_frames)
