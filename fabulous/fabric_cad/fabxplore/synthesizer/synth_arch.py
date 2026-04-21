"""Defines the base class for architecture synthesizers.

This module defines the `ArchitectureSynthesizer` abstract base class, which
serves as a blueprint for synthesizers that generate FPGA architectures.
"""

from abc import ABC, abstractmethod


class ArchitectureSynthesizer(ABC):
    """Abstract interface for architecture-specific synthesis pipelines."""

    @abstractmethod
    def begin(self) -> None:
        """Prepare the design and initialize the synthesis flow."""

    @abstractmethod
    def flatten(self) -> None:
        """Flatten hierarchy to simplify downstream mapping passes."""

    @abstractmethod
    def coarse(self) -> None:
        """Run coarse-grain synthesis optimizations on the design."""

    @abstractmethod
    def map_ram(self) -> None:
        """Map inferred memory structures to RAM primitives."""

    @abstractmethod
    def map_ffram(self) -> None:
        """Map FF-based RAM structures when dedicated RAM is unavailable."""

    @abstractmethod
    def map_gates(self) -> None:
        """Map generic logic into technology-specific gate primitives."""

    @abstractmethod
    def map_iopad(self) -> None:
        """Map top-level IO signals to architecture IO pad primitives."""

    @abstractmethod
    def map_ffs(self) -> None:
        """Map sequential elements to architecture flip-flop primitives."""

    @abstractmethod
    def map_luts(self) -> None:
        """Map combinational logic into LUT resources."""

    @abstractmethod
    def map_cells(self) -> None:
        """Run final cell-level mapping and legalization passes."""

    @abstractmethod
    def check(self) -> None:
        """Validate the mapped design and report structural issues."""

    @abstractmethod
    def synthesize(self) -> None:
        """Run the full synthesis pipeline for a user design."""

    @abstractmethod
    def generate_primitives(self) -> None:
        """Generate primitive definitions required by this architecture."""

    @abstractmethod
    def generate_switch_matrix(self) -> None:
        """Generate switch-matrix resources for routing integration."""
