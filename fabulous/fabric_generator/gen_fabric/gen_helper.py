"""Helper functions for FPGA fabric generation.

Currently only a CSV → ``.list`` switch-matrix converter. The switch matrix is
otherwise read once into its canonical form by
:class:`fabulous.fabric_definition.switch_matrix.SwitchMatrix`.
"""

from pathlib import Path


def CSV2list(InFileName: str, OutFileName: str) -> None:
    """Export a CSV switch matrix description into its equivalent list representation.

    Parameters
    ----------
    InFileName : str
        The input file name of the CSV file
    OutFileName : str
        The directory of the list file to be written
    """
    with Path(InFileName).open() as f:
        inFile = f.readlines()
    InFile = [i.strip("\n").split(",") for i in inFile]
    with Path(OutFileName).open("w") as f:
        # get the number of tiles in horizontal direction
        cols = len(InFile[0])
        # top-left should be the name
        _ = f.write(f"# {InFile[0][0]}\n")
        # switch matrix inputs
        inputs = []
        for item in InFile[0][1:]:
            inputs.append(item)
        # beginning from the second line, write out the list
        for line in InFile[1:]:
            for i in range(1, cols):
                if line[i] != "0":
                    # it is [i-1] because the beginning of the line is the
                    # destination port
                    _ = f.write(f"{line[0]},{inputs[i - 1]}")
