"""Utilities for parsing STA reports and extracting timing slack values.

This module provides functions to parse static timing analysis (STA) reports and extract
the worst hold and setup slack values. The parser looks for paths marked as "Path Type:
min" for hold slack and "Path Type: max" for setup slack, and extracts the numeric slack
values from the report text. The extracted slack values can be used for timing
verification and optimization in the gate-level mapping flow.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StaSlacks:
    """STA setup and hold slack values.

    Atributes
    ----------
    hold : float | None
        Worst hold slack from ``Path Type: min`` paths.
    setup : float | None
        Worst setup slack from ``Path Type: max`` paths.
    """

    hold: float | None
    setup: float | None


def extract_sta_slacks(report_text: str) -> StaSlacks:
    """Extract worst hold and setup slack from an STA report.

    Parses an STA timing report and extracts slack values from paths marked as
    ``Path Type: min`` and ``Path Type: max``. Negative slack values are
    supported. The parser does not depend on ``(MET)`` or ``(VIOLATED)`` text;
    it only extracts the numeric value before the word ``slack``.

    Parameters
    ----------
    report_text : str
        Full STA report text.

    Returns
    -------
    StaSlacks
        Dataclass containing the worst hold and setup slack values.

    Examples
    --------
    >>> result = extract_sta_slacks(report_text)
    >>> result.hold
    -0.05
    >>> result.setup
    9.56
    """
    pattern: re.Pattern[str] = re.compile(
        r"Path Type:\s*(min|max).*?"
        r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+slack\b",
        flags=re.DOTALL | re.MULTILINE,
    )

    hold_slacks: list[float] = []
    setup_slacks: list[float] = []

    for path_type, slack_text in pattern.findall(report_text):
        slack: float = float(slack_text)

        if path_type == "min":
            hold_slacks.append(slack)
        elif path_type == "max":
            setup_slacks.append(slack)

    return StaSlacks(
        hold=min(hold_slacks) if hold_slacks else None,
        setup=min(setup_slacks) if setup_slacks else None,
    )
