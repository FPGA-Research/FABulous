"""Abstract base for external EDA tool wrappers.

`Tool` is the root of the tool catalogue. It is never instantiated: every tool is
used as a singleton through classmethods (e.g. `YosysTool.run(...)`). The base
owns the single subprocess entry point (`run`), so every concrete wrapper (Yosys,
OpenSTA, GHDL, and future tools such as nextpnr or OpenROAD) shares one place for
invocation and error handling, and no business-logic code calls `subprocess`
directly. Each subclass resolves its own executable from the FABulous context via
`executable`.

`run` is also where a tool's supported version range is enforced, so no caller
ever asks for the check. The ranges live in `fabulous/tool_versions.toml`, keyed
by each wrapper's `COMMAND`, so a pin changes without touching code. The check
runs once per tool and executable and is skipped for a tool with no entry.
"""

import re
import subprocess
import tomllib
from abc import ABC, abstractmethod
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import ClassVar, NoReturn

from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import TypeAdapter

from fabulous.custom_exception import UnsupportedToolVersion


@cache
def _tool_versions() -> dict[str, SpecifierSet]:
    """Load the supported version range of every pinned tool.

    A value that is not a string or not a valid specifier raises, so a
    malformed pin stops the first `Tool.run` rather than disabling a gate.
    `SpecifierSet` alone would accept a TOML table and read its keys.

    Returns
    -------
    dict[str, SpecifierSet]
        The pins keyed by the `COMMAND` of the tool they apply to.
    """
    text = files("fabulous").joinpath("tool_versions.toml").read_text(encoding="utf-8")
    pins = TypeAdapter(dict[str, str]).validate_python(tomllib.loads(text))
    return {command: SpecifierSet(spec) for command, spec in pins.items()}


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
    `executable` to resolve its command and names it in `COMMAND`, then builds its
    argument list and stdin and calls `run`.
    """

    COMMAND: ClassVar[str]
    VERSION_ARGS: ClassVar[list[str]] = ["--version"]
    # Anchored to the first line: a version further down a banner is some other
    # tool's, such as the GNAT version GHDL prints on its second line.
    VERSION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\A[^\n]*?(\d+(?:\.\d+)+[\w.+-]*)"
    )

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
        """Reject an executable outside this tool's pinned version range.

        Raises
        ------
        UnsupportedToolVersion
            If the executable's version does not match the specifier set
            `tool_versions.toml` pins for `COMMAND`.
        """
        if (pinned := _tool_versions().get(cls.COMMAND)) is None:
            return
        found = cls.version()
        if found is None:
            return
        # PEP 440 matching ignores the local segment, so the `0.66+NN` Yosys
        # oss-cad-suite builds from master satisfies `<=0.66`. `prereleases`
        # admits a nightly such as `6.1.0.dev0` past a `>=6.0.0` floor, while
        # `6.0.0.dev0` still sorts below it.
        if not pinned.contains(found, prereleases=True):
            raise UnsupportedToolVersion(
                f"{cls.__name__} version {found} at {cls.executable()} does not "
                f"match {pinned}."
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
