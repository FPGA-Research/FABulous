#!/usr/bin/env python3
"""Extract PDK placement site dimensions using ODB.

This script runs within the OpenROAD Python interpreter to extract standard cell
placement site dimensions from the loaded technology LEF. The dimensions are written as
metrics for use by the flow.
"""

from typing import Any

from librelane.logging.logger import info


def main(reader: Any, **_: dict) -> None:  # noqa: ANN401
    """Extract placement site dimensions and write to metrics.

    Parameters
    ----------
    reader : Any
        Reader object provided by OdbpyStep with loaded database
    **_ : dict
        Additional unused keyword arguments

    Raises
    ------
    RuntimeError
        If no database is available or no libraries/sites are found
        or if no CORE placement site is found.
    """
    db = reader.block.getDb()

    if not db:
        raise RuntimeError("No database available")

    # Get all libraries (tech LEF + cell LEFs)
    libs = db.getLibs()

    if not libs:
        raise RuntimeError("No libraries found in database")

    # Search for the first CORE placement site
    site_width_dbu = None
    site_height_dbu = None
    site_name = None

    for lib in libs:
        sites = lib.getSites()
        for site in sites:
            # Look for CORE class sites (standard cell placement)
            if str(site.getClass()) == "CORE":
                site_width_dbu = site.getWidth()
                site_height_dbu = site.getHeight()
                site_name = site.getName()
                break
        if site_width_dbu is not None:
            break

    if site_width_dbu is None or site_height_dbu is None:
        raise RuntimeError(
            "Could not find CORE placement site in technology LEF. "
            "Ensure tech LEF is loaded correctly."
        )

    # Write metrics for use by the flow
    print(f"%OL_METRIC pdk__site_width {site_width_dbu}")  # noqa: T201
    print(f"%OL_METRIC pdk__site_height {site_height_dbu}")  # noqa: T201

    # Also print for debugging
    info(
        f"Found placement site '{site_name}': {site_width_dbu} x {site_height_dbu} DBU"
    )


if __name__ == "__main__":
    main()
