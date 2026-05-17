"""Base interface for fabxplore placement/routing passes.

This module defines the abstract pass contract for work that happens after
pyosys synthesis and packing. Unlike ``SynthPass``, a PnR pass receives both the
packed ``PyosysBridge`` design and the loaded ``FABulous_API`` project object, so
it can generate tile resources, call FABulous fabric generators, or invoke
place-and-route tooling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabulous_api import FABulous_API


class PnRPass(ABC):
    """Abstract base class for placement/routing passes in fabxplore.

    PnR passes run after synthesis/packing and can use both the packed pyosys design and
    the loaded FABulous project API.
    """

    @abstractmethod
    def run_on(self, design: PyosysBridge, fab: FABulous_API) -> None:
        """Run the PnR pass on the given design.

        Parameters
        ----------
        design : PyosysBridge
            The design to be processed by the PnR pass.
        fab : FABulous_API
            Loaded FABulous API for project, tile, and fabric generation access.
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
