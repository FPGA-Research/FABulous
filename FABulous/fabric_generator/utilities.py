import re

from loguru import logger


def expandListPorts(port, PortList):
    """Expand the .list file entry into a list of tuples.

    Parameters
    ----------
    port : str
        The port entry to expand. If it contains "[", it's split
        into multiple entries based on "|".
    PortList : list
        The list where expanded port entries are appended.

    Raises
    ------
    ValueError
        If the port entry contains "[" or "{" without matching closing
        bracket "]"/"}".
    """
    if port.count("[") != port.count("]") and port.count("{") != port.count("}"):
        raise ValueError(f"Invalid port entry: {port}, mismatched brackets")

    # a leading '[' tells us that we have to expand the list
    if "[" in port:
        # port.find gives us the first occurrence index in a string
        left_index = port.find("[")
        right_index = port.find("]")
        before_left_index = port[0:left_index]
        # right_index is the position of the ']' so we need everything after that
        after_right_index = port[(right_index + 1) :]
        ExpandList = []
        ExpandList = re.split(r"\|", port[left_index + 1 : right_index])
        for entry in ExpandList:
            ExpandListItem = before_left_index + entry + after_right_index
            expandListPorts(ExpandListItem, PortList)

    else:
        # Multiply ports by the number of multipliers, given in the curly braces.
        # We let all curly braces in the port Expansion to be expanded and
        # calculate the total number of ports to be added afterward, based on the number of multipliers.
        # Also remove the multipliers from port name, before adding it to the list.
        port = port.replace(" ", "")  # remove spaces
        multipliers = re.findall(r"\{(\d+)\}", port)
        portMultiplier = sum([int(m) for m in multipliers])
        if portMultiplier != 0:
            port = re.sub(r"\{(\d+)\}", "", port)
            logger.debug(f"Port {port} has {portMultiplier} multipliers")
            for _i in range(portMultiplier):
                PortList.append(port)
        else:
            PortList.append(port)
