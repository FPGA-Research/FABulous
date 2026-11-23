"""Manager-owned lifecycle dispatch: startup firing and command-set collection."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from cmd2 import CommandSet

from fabulous.custom_exception import PluginError
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager


class _OneCommands(CommandSet):
    def do_one(self, _statement: object) -> None:
        """Do nothing; only its presence in the registry matters."""


class _TwoCommands(CommandSet):
    def do_two(self, _statement: object) -> None:
        """Do nothing; only its presence in the registry matters."""


class _BrokenStartup:
    @hookspecs.hookimpl
    def fabulous_startup(self) -> None:
        raise RuntimeError("boom")


class _BrokenCommands:
    @hookspecs.hookimpl
    def fabulous_register_commands(self) -> CommandSet:
        raise RuntimeError("boom")


@dataclass(frozen=True, eq=False)
class _Commands:
    returned: CommandSet | list[CommandSet] | None

    @hookspecs.hookimpl
    def fabulous_register_commands(self) -> CommandSet | list[CommandSet] | None:
        return self.returned


def _manager_with(
    name: str, plugin: object, *, skip_broken: bool = False
) -> PluginManager:
    """Build a manager whose only plugin is `plugin`."""
    manager = PluginManager(skip_broken=skip_broken)
    manager.pm.register(plugin, name=name)
    return manager


def test_notify_startup_fires_every_implementation() -> None:
    fired: list[bool] = []

    class _Spy:
        @hookspecs.hookimpl
        def fabulous_startup(self) -> None:
            fired.append(True)

    manager = _manager_with("spy", _Spy())

    manager.notify_startup()

    assert fired == [True]


def test_hookimpl_may_omit_spec_arguments() -> None:
    """pluggy lets an implementation take a subset of the spec's arguments."""
    fired: list[bool] = []

    class _Spy:
        @hookspecs.hookimpl
        def fabulous_after_fabric_loaded(self) -> None:
            fired.append(True)

    manager = _manager_with("spy", _Spy())

    manager.notify_fabric_loaded(
        FABulous_API(VerilogCodeGenerator(), plugin_manager=manager)
    )

    assert fired == [True]


@pytest.mark.parametrize(
    ("hook_name", "plugin", "call"),
    [
        pytest.param(
            "fabulous_startup",
            _BrokenStartup(),
            lambda m: m.notify_startup(),
            id="startup",
        ),
        pytest.param(
            "fabulous_register_commands",
            _BrokenCommands(),
            lambda m: m.collect_command_sets(),
            id="register-commands",
        ),
    ],
)
def test_broken_lifecycle_hook_aborts_when_strict(
    hook_name: str, plugin: object, call: Callable[[PluginManager], object]
) -> None:
    manager = _manager_with("broken", plugin)

    with pytest.raises(PluginError) as exc:
        call(manager)

    assert hook_name in str(exc.value)


@pytest.mark.parametrize(
    ("plugin", "call", "expected"),
    [
        pytest.param(
            _BrokenStartup(),
            lambda m: m.notify_startup(),
            None,
            id="startup",
        ),
        pytest.param(
            _BrokenCommands(),
            lambda m: m.collect_command_sets(),
            [],
            id="register-commands",
        ),
    ],
)
def test_broken_lifecycle_hook_skipped_when_lenient(
    plugin: object, call: Callable[[PluginManager], object], expected: object
) -> None:
    manager = _manager_with("broken", plugin, skip_broken=True)

    assert call(manager) == expected


@pytest.mark.parametrize(
    ("returned", "expected_types"),
    [
        pytest.param(_OneCommands(), [_OneCommands], id="single"),
        pytest.param(
            [_OneCommands(), _TwoCommands()],
            [_OneCommands, _TwoCommands],
            id="list",
        ),
        pytest.param(None, [], id="none"),
    ],
)
def test_collect_command_sets_flattens_hook_returns(
    returned: CommandSet | list[CommandSet] | None, expected_types: list[type]
) -> None:
    manager = _manager_with("commands", _Commands(returned))

    collected = manager.collect_command_sets()

    assert [type(cs) for cs in collected] == expected_types
