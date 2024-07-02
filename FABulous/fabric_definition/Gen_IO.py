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
        params (Dict[str, str]): Additional parameters for GEN_IO.
    """

    prefix: str
    pins: int
    IO: IO
