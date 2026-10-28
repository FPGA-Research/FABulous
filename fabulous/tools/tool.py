"""Abstract base for external EDA tool wrappers.

`Tool` is the root of the tool catalogue. It is never instantiated: every tool is
used as a singleton through classmethods (e.g. `YosysTool.run(...)`). The base
owns the single subprocess entry point (`run`), so every concrete wrapper (Yosys,
OpenSTA, GHDL, and future tools such as nextpnr or OpenROAD) shares one place for
invocation and error handling, and no business-logic code calls `subprocess`
directly. Each subclass resolves its own executable from the FABulous context via
`executable`.
"""

import subprocess
from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path
from typing import NoReturn

from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger


@cache
def _template_env() -> Environment:
    """Return the shared Jinja environment for tool script templates.

    Templates live in the `fabulous/template` package directory.
    `StrictUndefined` makes a missing variable a render error rather than an
    empty string, so a malformed template surfaces immediately.

    Returns
    -------
    Environment
        The cached Jinja environment.
    """
    return Environment(
        loader=PackageLoader("fabulous", "template"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class Tool(ABC):
    """Abstract base for every external tool wrapper.

    Tools are stateless singletons used through classmethods only; neither `Tool`
    nor any subclass can be instantiated (see `__new__`). A subclass implements
    `executable` to resolve its command, then builds its argument list and stdin
    and calls `run`.
    """

    def __new__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        """Reject instantiation; tools are used only through their classmethods.

        Parameters
        ----------
        *_args : object
            Ignored positional arguments from the rejected constructor call.
        **_kwargs : object
            Ignored keyword arguments from the rejected constructor call.

        Raises
        ------
        TypeError
            Always, because tool wrappers are stateless singletons.
        """
        raise TypeError(
            f"{cls.__name__} is a stateless tool wrapper used through its "
            f"classmethods and cannot be instantiated."
        )

    @classmethod
    def render_template(cls, template_name: str, **context: object) -> str:
        """Render a tool script template into the command string to feed `run`.

        Parameters
        ----------
        template_name : str
            Template file name within the `fabulous/template` directory.
        **context : object
            Variables made available to the template.

        Returns
        -------
        str
            The rendered script.
        """
        return _template_env().get_template(template_name).render(**context)

    @classmethod
    @abstractmethod
    def executable(cls) -> Path | str:
        """Return the path to (or name of) this tool's executable.

        Returns
        -------
        Path | str
            The resolved executable, typically read from the FABulous context.
        """

    @classmethod
    def run(
        cls,
        args: list[str] | None = None,
        stdin_data: str = "",
    ) -> subprocess.CompletedProcess:
        """Run the tool executable, capturing output and raising on failure.

        Parameters
        ----------
        args : list[str] | None
            Arguments passed to the executable.
        stdin_data : str
            Data piped to the executable's stdin.

        Returns
        -------
        subprocess.CompletedProcess
            The completed subprocess result.

        Raises
        ------
        RuntimeError
            If the command exits with a non-zero return code.
        """
        if args is None:
            args = []

        command: list[str] = [str(cls.executable()), *args]

        logger.debug("Debug mode enabled for external command.")
        logger.debug(f"Calling external command: {' '.join(command)}")
        logger.debug(f"With stdin data:\n{stdin_data}")

        result = subprocess.run(
            command,
            input=stdin_data,
            text=True,
            capture_output=True,
            check=False,
        )

        logger.debug(f"Command stdout:\n{result.stdout}")
        logger.debug(f"Command stderr:\n{result.stderr}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Command {' '.join(command)!r} failed with error: {result.stderr}"
            )
        return result
