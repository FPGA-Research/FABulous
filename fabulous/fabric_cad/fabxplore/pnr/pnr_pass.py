"""Base interface for fabxplore placement/routing passes.

This module defines the abstract pass contract for work that happens after
pyosys synthesis and packing. Unlike ``SynthPass``, a PnR pass receives the
loaded ``PnRBridge`` so it can access the packed design, FABulous project API,
and editable routing graph through one object.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class PnRPass(ABC):
    """Abstract base class for placement/routing passes in fabxplore.

    PnR passes run after synthesis/packing and operate on the bridge that owns the
    packed design, loaded FABulous API, and routing graph.
    """

    @abstractmethod
    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run the PnR pass on the given FPGA model.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and editable routing
            graph model.
        """

    @property
    @abstractmethod
    def report_summary(self) -> str:
        """Return a summary report of the PnR pass results."""

    @property
    @abstractmethod
    def result_data(self) -> object | None:
        """Return any relevant data from the PnR pass results.

        Returns
        -------
        object | None
            Data relevant to the PnR pass results, or None if not available.
        """
