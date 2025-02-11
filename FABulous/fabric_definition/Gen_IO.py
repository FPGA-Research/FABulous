from dataclasses import dataclass, field
from FABulous.fabric_definition.define import IO


@dataclass
class Gen_IO:
    """
    Contains all the information about a generated IO port (GEN_IO).
    The information is parsed from the GEN_IO in the CSV
    definition file. There are something to be noted.

    Attributes
    ----------
    prefix : str
        The prefix of the GEN_IO given in the CSV file.
    pins : int
        Number of IOs.
    IO : IO
        Direction of the IOs, either INPUT or OUTPUT, seen from the fabric side.
        This means a fabric INPUT is an OUTPUT globally and vice versa.
    configBit : int
        The number of accessible config bits for config access GEN_IO.
    configAccess : bool
        Whether the GEN_IO is config access.
        Routes access to config bits, directly to TOP.
        This GEN_IOs are not connected to the switchmatrix,
        Can only be used as an OUTPUT.
    inverted : bool
        GEN_IO will be inverted.
    clocked : bool
        Adds a register to GEN_IO.
    clockedComb: bool
        Creates two signals for every GEN_IO.
        <prefix><Number>_Q: The clocked signal.
        <prefix><Number>: The orignal cobinatorial signal.
        If the GEN_IO is an INPUT, then there will be created
        two signals to the top, <prefix><Number>_Q_top is the clocked input
        signal and <prefix><Number>_top is the combinatorial input signal.
        If the GEN_IO is an OUTPUT, then there will be two signals connected
        to the switch matrix, <prefix><Number>_Q is the clocked output signal
        and <prefix><Number> is the combinatorial output signal.
    """

    prefix: str
    pins: int
    IO: IO
    configBit: int = 0

    # Paramters for GEN_IO:
    configAccess: bool = False
    inverted: bool = False
    clocked: bool = False
    clockedComb: bool = False
