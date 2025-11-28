"""Hook-based Typer integration for cmd2 (clean implementation)."""

from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING, Any, cast

import click
import typer
from cmd2 import Cmd
from cmd2.parsing import Statement
from loguru import logger

from fabulous.custom_exception import CommandError

if TYPE_CHECKING:
    from collections.abc import Callable

# TYPE_CHECKING block removed as it's no longer needed


class CompleterSpec:
    """Specification for tab completion behavior.

    Used to declare completion functions that the plugin will wire up to both Click's
    autocompletion and cmd2's tab completion.

    Parameters
    ----------
    completer : Callable[..., list[str]]
        Function that takes either (text, line, begidx, endidx) or
        (self, text, line, begidx, endidx) and returns a list of
        completion strings. Both signatures are supported.
    """

    def __init__(
        self,
        completer: Callable[..., list[str]],
    ) -> None:
        self.completer = completer


class Cmd2TyperPlugin(Cmd):
    """Optional mixin supplying default Typer integration attributes.

    Inherit alongside your ``cmd2.Cmd`` subclass if you want convenient defaults,
    or simply define the same attributes on your class directly.

    Attributes
    ----------
    typer_auto_enable : bool
        Whether to automatically enable Typer integration.
    typer_skip_commands : set[str]
        Set of command names to skip during Typer registration.
    typer_command_kwargs : dict[str, dict[str, Any]]
        Additional keyword arguments for specific Typer commands.
    typer_command_builder : Callable[[Callable[..., Any], str, dict[str, Any]], click.Command] | None
        Optional custom command builder function.
    standard_cmd2_commands : set[str]
        Set of standard cmd2 commands to exclude from Typer registration.

    Parameters
    ----------
    *args : object
        Positional arguments passed to parent Cmd class.
    **kwargs : object
        Keyword arguments passed to parent Cmd class.
    """  # noqa: E501

    typer_auto_enable: bool = True
    typer_skip_commands: set[str] = set()
    typer_command_kwargs: dict[str, dict[str, Any]] = {}
    typer_command_builder: (
        Callable[[Callable[..., Any], str, dict[str, Any]], click.Command] | None
    ) = None

    __inner_app: typer.Typer

    standard_cmd2_commands: set[str] = {
        "do_exit",
        "do_quit",
        "do_q",
        "do_help",
        "do_history",
        "do_edit",
        "do_shell",
        "do_alias",
        "do_unalias",
        "do_shortcuts",
        "do_macro",
        "do_run_pyscript",
        "do_run_script",
        "do_set",
        "do_settable",
    }

    def _extract_completion_specs(
        self, func: Callable[..., Any]
    ) -> dict[str, CompleterSpec]:
        """Extract CompletionSpecs from function parameter annotations."""
        specs = {}
        sig = inspect.signature(func)
        for param in sig.parameters.values():
            if param.name == "self":
                continue

            ann = param.annotation
            if ann is inspect.Signature.empty:
                continue

            # Handle Annotated types
            origin = getattr(ann, "__origin__", None)
            if origin is not None:
                # For Annotated[type, metadata...], check metadata
                metadata = getattr(ann, "__metadata__", ())
                for item in metadata:
                    if isinstance(item, CompleterSpec):
                        specs[param.name] = item
        return specs

    def cmd_register(self) -> None:
        """Register all cmd2 do_* methods as Typer commands."""
        skip = set(self.standard_cmd2_commands)
        skip.update(self.typer_skip_commands)

        for attr in dir(self):
            if not attr.startswith("do_"):
                continue
            if attr in skip or attr[3:] in skip:
                continue
            func = getattr(type(self), attr, None)
            if func is None or not inspect.isfunction(func):
                continue
            if func.__module__.startswith("cmd2."):
                continue

            cmd_name = attr[3:]
            bound_cb = cast("Callable[..., Any]", func.__get__(self))
            completer_specs = self._extract_completion_specs(func)
            self.__inner_app.command(name=cmd_name)(bound_cb)

            if not completer_specs:
                continue

            # Parameter names in order (excluding self)
            param_names = [
                p.name
                for p in inspect.signature(func).parameters.values()
                if p.name != "self"
            ]

            # cmd2 expects a complete_* callable with signature
            # (text, line, begidx, endidx). We'll close over `self`.
            def _completer(
                text: str,
                line: str,
                begidx: int,
                endidx: int = -1,
                _param_names: list[str] = param_names,
                _specs: dict[str, CompleterSpec] = completer_specs,
            ) -> list[str]:
                try:
                    parts = line.split()
                    if not parts:
                        return []
                    cmd_part = parts[0]
                    args = parts[1:] if len(parts) > 1 else []
                    current_pos = len(cmd_part) + 1

                    # Within an existing arg?
                    for i, arg in enumerate(args):
                        arg_start = current_pos
                        arg_end = arg_start + len(arg)
                        if arg_start <= begidx <= arg_end:
                            pname = _param_names[i] if i < len(_param_names) else None
                            if pname:
                                spec = _specs.get(pname)
                                if spec is not None:
                                    # Access self from outer scope
                                    outer_self = self
                                    try:
                                        # Try with self first (for methods)
                                        return spec.completer(
                                            outer_self, text, line, begidx, endidx
                                        )
                                    except TypeError:
                                        try:
                                            # Try with self but 3 args
                                            return spec.completer(
                                                outer_self, text, line, begidx
                                            )
                                        except TypeError:
                                            try:
                                                # Try without self, 4 args
                                                return spec.completer(
                                                    text, line, begidx, endidx
                                                )
                                            except TypeError:
                                                # Try without self, 3 args
                                                return spec.completer(
                                                    text, line, begidx
                                                )
                            break
                        current_pos = arg_end + 1

                    # Starting a new arg?
                    if begidx >= current_pos:
                        idx = len(args)
                        pname = _param_names[idx] if idx < len(_param_names) else None
                        if pname:
                            spec = _specs.get(pname)
                            if spec is not None:
                                # Access self from outer scope
                                outer_self = self
                                try:
                                    # Try with self first (for methods)
                                    return spec.completer(
                                        outer_self, text, line, begidx, endidx
                                    )
                                except TypeError:
                                    try:
                                        # Try with self but 3 args
                                        return spec.completer(
                                            outer_self, text, line, begidx
                                        )
                                    except TypeError:
                                        try:
                                            # Try without self, 4 args
                                            return spec.completer(
                                                text, line, begidx, endidx
                                            )
                                        except TypeError:
                                            # Try without self, 3 args
                                            return spec.completer(text, line, begidx)
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Completer wrapper error: {e}")
                    return []
                else:
                    return []

            # Set the completer function directly
            setattr(self, f"complete_{cmd_name}", _completer)
            logger.debug(f"Registered completer for command: {cmd_name}")

    def do_help(self, args: str) -> None:
        """Override cmd2's help to show Typer help for Typer commands."""
        # Parse the help argument
        arg_list = args.split() if args else []

        if not arg_list:
            # No specific command requested, show cmd2's default help
            return super().do_help(args)

        command_name = arg_list[0]

        # Check if this is a Typer command
        cmds = typer.main.get_command(self.__inner_app)
        if isinstance(cmds, click.Group) and command_name in cmds.commands:
            # Show Typer's help for this command
            with contextlib.suppress(SystemExit):
                # Typer/Click tries to exit after showing help, catch it
                cmds.commands[command_name].main(
                    args=["--help"],
                    prog_name=command_name,
                    standalone_mode=False,
                    obj=self.__inner_app,
                )
            return None

        # Not a Typer command, use cmd2's default help
        return super().do_help(args)

    def onecmd(
        self, statement: Statement | str, *, add_to_history: bool = True
    ) -> bool:
        """Route commands through Typer when possible, falling back to cmd2."""
        # Convert string to Statement object (Statement inherits from str)
        if not isinstance(statement, Statement) and isinstance(statement, str):
            statement = self.statement_parser.parse(statement)

        cmds = typer.main.get_command(self.__inner_app)
        if isinstance(cmds, click.Group) and isinstance(statement, Statement):
            if statement.command not in cmds.commands:
                return super().onecmd(statement, add_to_history=add_to_history)
            # Execute the Typer command and return False (don't stop the cmdloop)
            cmds.commands[statement.command].main(
                args=list(statement.arg_list),
                prog_name=statement.command,
                standalone_mode=False,
                obj=self.__inner_app,
            )
            return False  # Don't stop the cmdloop
        raise CommandError("Invalid command or statement")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        logger.debug("cmd2_typer plugin_start for {}", type(self).__name__)
        self.__inner_app = typer.Typer(add_completion=False)

        self.cmd_register()

        # Debug: List all completion methods
        completers = [attr for attr in dir(self) if attr.startswith("complete_")]
        logger.debug(f"Available completers: {completers}")

        # Note: to test completion wiring, create a do_test_cmd and a corresponding
        # complete_test_cmd method on your Cmd subclass if needed.
