"""Abstract base for external EDA tool wrappers.

`Tool` is the root of the tool catalogue. It is never instantiated: every tool is
used as a singleton through classmethods (e.g. `YosysTool.run(...)`). The base
owns the single subprocess entry point (`run`), so every concrete wrapper (Yosys,
OpenSTA, GHDL, and future tools such as nextpnr or OpenROAD) shares one place for
invocation and error handling, and no business-logic code calls `subprocess`
directly. Each subclass resolves its own executable from the FABulous context via
`executable`.

`run` is also where a tool's supported version range is enforced, so a wrapper
declares `MINIMUM_VERSION` or `MAXIMUM_VERSION` and no caller ever asks for the
check. The check runs once per tool and executable and is skipped for a wrapper
that declares neither bound.
"""

import re
import subprocess
from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path
from typing import ClassVar, NoReturn

from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger
from packaging.version import InvalidVersion, Version

from fabulous.custom_exception import UnsupportedToolVersion


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


@cache
def _check_version_once(tool: type["Tool"], _executable: str) -> None:
    """Run `tool`'s version check the first time an executable is used.

    Parameters
    ----------
    tool : type[Tool]
        The tool wrapper whose version range is enforced.
    _executable : str
        The resolved executable. Unused in the body; it is part of the cache
        key so that repointing a tool at another binary re-checks it.
    """
    tool.check_version()


class Tool(ABC):
    """Abstract base for every external tool wrapper.

    Tools are stateless singletons used through classmethods only; neither `Tool`
    nor any subclass can be instantiated (see `__new__`). A subclass implements
    `executable` to resolve its command, then builds its argument list and stdin
    and calls `run`.
    """

    MINIMUM_VERSION: ClassVar[Version | None] = None
    MAXIMUM_VERSION: ClassVar[Version | None] = None
    VERSION_ARGS: ClassVar[list[str]] = ["--version"]
    # Anchored to the first line: a version further down a banner is some other
    # tool's, such as the GNAT version GHDL prints on its second line.
    VERSION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\A[^\n]*?(\d+(?:\.\d+)+[\w.+-]*)"
    )
    VERSION_HINT: ClassVar[str] = ""

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
    def version(cls) -> Version | None:
        """Return the version the tool reports, or None if it reports none.

        A build made outside a release, such as one built straight from a
        working tree, can print a banner with no version in it. That is not an
        error: the caller is told nothing is known rather than being stopped.

        Returns
        -------
        Version | None
            The parsed version, or None if the banner carries no readable one.
        """
        banner = cls.run(cls.VERSION_ARGS, check_version=False).stdout
        if not (match := cls.VERSION_PATTERN.search(banner)):
            logger.warning(
                f"{cls.__name__} could not read a version from "
                f"{cls.executable()}, which reported {banner.strip()!r}. "
                f"Skipping the version check."
            )
            return None
        try:
            return Version(match.group(1))
        except InvalidVersion:
            logger.warning(
                f"{cls.__name__} read the unparseable version "
                f"{match.group(1)!r} from {cls.executable()}. Skipping the "
                f"version check."
            )
            return None

    @classmethod
    def check_version(cls) -> None:
        """Reject an executable outside this tool's supported version range.

        Raises
        ------
        UnsupportedToolVersion
            If the executable is older than `MINIMUM_VERSION` or newer than
            `MAXIMUM_VERSION`.
        """
        if cls.MINIMUM_VERSION is None and cls.MAXIMUM_VERSION is None:
            return
        found = cls.version()
        if found is None:
            return
        # A bound names a release, so the local segment a build carries past that
        # release is dropped before comparing: oss-cad-suite ships Yosys as
        # `0.66+NN`, which PEP 440 otherwise sorts above the 0.66 ceiling. A
        # pre-release keeps its ordering, since `6.0.0.dev0` really does come
        # before the 6.0.0 a floor asks for.
        compared = Version(found.public)
        if cls.MINIMUM_VERSION is not None and compared < cls.MINIMUM_VERSION:
            raise UnsupportedToolVersion(
                f"{cls.__name__} needs version {cls.MINIMUM_VERSION} or newer, "
                f"but {cls.executable()} is {found}. {cls.VERSION_HINT}".strip()
            )
        if cls.MAXIMUM_VERSION is not None and compared > cls.MAXIMUM_VERSION:
            raise UnsupportedToolVersion(
                f"{cls.__name__} needs version {cls.MAXIMUM_VERSION} or older, "
                f"but {cls.executable()} is {found}. {cls.VERSION_HINT}".strip()
            )

    @classmethod
    def run(
        cls,
        args: list[str] | None = None,
        stdin_data: str = "",
        check_version: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run the tool executable, capturing output and raising on failure.

        Parameters
        ----------
        args : list[str] | None
            Arguments passed to the executable.
        stdin_data : str
            Data piped to the executable's stdin.
        check_version : bool
            Whether to enforce the supported version range first. `version`
            clears it so that asking the tool what it is does not ask again.

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

        if check_version:
            _check_version_once(cls, str(cls.executable()))

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
