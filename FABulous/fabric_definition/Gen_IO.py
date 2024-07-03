from dataclasses import dataclass, field
from FABulous.fabric_definition.define import IO


@dataclass
class Gen_IO:
    """
    Contains all the information about a generated IO port (GEN_IO).
    The information is parsed from the GEN_IO in the CSV
    definition file. There are something to be noted.

    Attributes:
        prefix (str): The prefix of the GEN_IO given in the CSV file.
        pins (int): Number of IOs.
        IO (IO) : Direction of the IOs, either INPUT or OUTPUT.
        configBit (int) : The number of accessible config bits for config access GEN_IO.
        params : Additional parameters of GEN_IOs.
            - configAccess (bool) : Whether the GEN_IO is config access.
                                    Routes access to config bits, directly to TOP.
                                    This GEN_IOs are not connected to the switchmatrix,
                                    Can only be used as an OUTPUT.
            - inverted (bool) : GEN_IO will be inverted.
    """

    prefix: str
    pins: int
    IO: IO
    configBit: int = 0

    # Paramters for GEN_IO:
    configAccess: bool = False
    inverted: bool = False
