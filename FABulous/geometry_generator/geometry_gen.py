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
    """This class handles the generation of the geometry for a fabric

    Attributes
    ----------
    fabric : Fabric
        The fabric object passed from the CSV definition files
    fabricGeometry : FabricGeometry
        The generated geometry object
    """

    def __init__(self, fabric: Fabric):
        self.fabric = fabric
        self.fabricGeometry = None

    def generateGeometry(self, padding: int = 8) -> None:
        """Starts the geometry generation for the given fabric."""
        self.fabricGeometry = FabricGeometry(self.fabric, padding)

    def saveToCSV(self, fileName: str) -> None:
        """Saves the generated geometry into a file specified by the given file name.
        This file can then be imported into the FABulous Editor.
        """
        self.fabricGeometry.saveToCSV(fileName)
