"""Run fabxplore architecture flow scripts.

This module loads a user-provided Python architecture file inside the active
FABulous process. It finds the architecture class, attaches the already-loaded
FABulous API object, and calls the architecture's ``run_flow`` method.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    from fabulous.fabulous_api import FABulous_API


def run_fabxplore_architecture(
    architecture_file: Path,
    fabulous_api: FABulous_API,
    debug: bool = False,
) -> ArchitectureSynthesizer:
    """Load an architecture script and run its ``run_flow`` method.

    Parameters
    ----------
    architecture_file : Path
        Python file defining exactly one ``ArchitectureSynthesizer`` subclass.
    fabulous_api : FABulous_API
        Loaded FABulous API instance to attach to the architecture object.
    debug : bool
        Enable debug mode on the architecture flow before running it.

    Returns
    -------
    ArchitectureSynthesizer
        Instantiated and executed architecture flow object.
    """
    architecture = load_fabxplore_architecture(architecture_file)
    architecture.debug = debug
    architecture.design.debug = debug
    architecture.attach_fabulous_api(fabulous_api)
    logger.info(f"Running fabxplore flow from {architecture_file}")
    architecture.run_flow()
    return architecture


def load_fabxplore_architecture(architecture_file: Path) -> ArchitectureSynthesizer:
    """Load and instantiate an architecture flow from a Python file.

    Parameters
    ----------
    architecture_file : Path
        Python file defining exactly one ``ArchitectureSynthesizer`` subclass.

    Returns
    -------
    ArchitectureSynthesizer
        Instantiated architecture object.

    Raises
    ------
    TypeError
        If the architecture class cannot be instantiated without arguments.
    """
    module = _load_python_module(architecture_file)
    architecture_class = _find_architecture_class(module, architecture_file)
    try:
        architecture = architecture_class()
    except TypeError as exc:
        raise TypeError(
            f"{architecture_file} architecture class "
            f"{architecture_class.__name__} must be instantiable without arguments."
        ) from exc
    return architecture


def _load_python_module(path: Path) -> ModuleType:
    """Load a Python file as a module.

    Parameters
    ----------
    path : Path
        Path to the Python file to load.

    Returns
    -------
    ModuleType
        Loaded Python module.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    ImportError
        If the file cannot be loaded as a Python module.
    """
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Architecture file not found: {path}")

    module_name = f"_fabxplore_arch_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load architecture file: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_architecture_class(
    module: ModuleType,
    architecture_file: Path,
) -> type[ArchitectureSynthesizer]:
    """Find exactly one architecture class defined in a module.

    Parameters
    ----------
    module : ModuleType
        Python module to search for architecture classes.
    architecture_file : Path
        Path to the architecture file (used for error messages).

    Returns
    -------
    type[ArchitectureSynthesizer]
        The architecture class defined in the module.

    Raises
    ------
    RuntimeError
        If the module does not define exactly one
        subclass of ``ArchitectureSynthesizer``.
    """
    candidates: list[type[ArchitectureSynthesizer]] = []
    for value in vars(module).values():
        if not isinstance(value, type):
            continue
        if value is ArchitectureSynthesizer:
            continue
        if value.__module__ != module.__name__:
            continue
        if issubclass(value, ArchitectureSynthesizer):
            candidates.append(value)

    if len(candidates) != 1:
        names = ", ".join(candidate.__name__ for candidate in candidates) or "none"
        raise RuntimeError(
            f"{architecture_file} must define exactly one "
            f"ArchitectureSynthesizer subclass; found {names}."
        )
    return candidates[0]
