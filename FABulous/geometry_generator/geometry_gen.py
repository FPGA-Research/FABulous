"""Classes for geometry generation."""

# Copyright 2023 Heidelberg University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.geometry_generator.fabric_geometry import FabricGeometry


class GeometryGenerator:
    """Class to handle the generation of the geometry for a fabric.

    Attributes
    ----------
    fabric : Fabric
        The fabric object passed from the CSV definition files
    fabricGeometry : FabricGeometry
        The generated geometry object
    """

    def __init__(self, fabric: Fabric) -> None:
        """Initialize a `GeometryGenerator` instance.

        Parameters
        ----------
        fabric : Fabric
            The fabric object from CSV definition files
        """
        self.fabric = fabric
        self.fabricGeometry = None

    def generateGeometry(self, padding: int = 8) -> None:
        """Start the geometry generation for the given fabric.

        Creates a `FabricGeometry` object that contains the complete geometric
        layout of the fabric including all tiles, switch matrices, BELs,
        and interconnect wiring.

        Parameters
        ----------
        padding : int, optional
            Padding used throughout the geometry, by default 8
        """
        self.fabricGeometry = FabricGeometry(self.fabric, padding)

    def saveToCSV(self, fileName: str) -> None:
        """Save the generated geometry into a file specified by the given file name.

        Exports the complete fabric geometry data to a CSV file that can be
        imported into FABulator for visualization and analysis.

        Parameters
        ----------
        fileName : str
            The name of the CSV file to create

        Raises
        ------
        AttributeError
            If generateGeometry() has not been called yet
        """
        self.fabricGeometry.saveToCSV(fileName)
