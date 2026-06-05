"""Manager-owned lifecycle dispatch: startup firing and command-set collection."""

import types
from collections.abc import Callable

import pytest
from cmd2 import CommandSet

from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager
from fabulous.plugins.types import PluginError


class _OneCommands(CommandSet):
    def do_one(self, _statement: object) -> None:
        """Do nothing; only its presence in the registry matters."""


class _TwoCommands(CommandSet):
    def do_two(self, _statement: object) -> None:
        """Do nothing; only its presence in the registry matters."""


def _manager_with(
    name: str, skip_broken: bool = False, **hookimpls: Callable
) -> PluginManager:
    """Build a manager whose only plugin exposes the given hookimpls."""
    manager = PluginManager(skip_broken=skip_broken)
    module = types.ModuleType(name)
    for hook_name, func in hookimpls.items():
        setattr(module, hook_name, hookspecs.hookimpl(func))
    manager.pm.register(module, name=name)
    return manager


def test_notify_startup_fires_every_implementation() -> None:
    fired = []
    manager = _manager_with("spy", fabulous_startup=lambda: fired.append(True))

    manager.notify_startup()

    assert fired == [True]


@pytest.mark.parametrize(
    ("hook_name", "call"),
    [
        pytest.param(
            "fabulous_startup",
            lambda m: m.notify_startup(),
            id="startup",
        ),
        pytest.param(
            "fabulous_register_commands",
            lambda m: m.collect_command_sets(),
            id="register-commands",
        ),
    ],
)
def test_broken_lifecycle_hook_aborts_when_strict(
    hook_name: str, call: Callable[[PluginManager], object]
) -> None:
    def _boom() -> None:
        raise RuntimeError("boom")

    manager = _manager_with("broken", **{hook_name: _boom})

    with pytest.raises(PluginError) as exc:
        call(manager)

    assert hook_name in str(exc.value)


@pytest.mark.parametrize(
    ("hook_name", "call", "expected"),
    [
        pytest.param(
            "fabulous_startup",
            lambda m: m.notify_startup(),
            None,
            id="startup",
        ),
        pytest.param(
            "fabulous_register_commands",
            lambda m: m.collect_command_sets(),
            [],
            id="register-commands",
        ),
    ],
)
def test_broken_lifecycle_hook_skipped_when_lenient(
    hook_name: str, call: Callable[[PluginManager], object], expected: object
) -> None:
    def _boom() -> None:
        raise RuntimeError("boom")

    manager = _manager_with("broken", skip_broken=True, **{hook_name: _boom})

    assert call(manager) == expected


@pytest.mark.parametrize(
    ("returned", "expected_types"),
    [
        pytest.param(lambda: _OneCommands(), [_OneCommands], id="single"),
        pytest.param(
            lambda: [_OneCommands(), _TwoCommands()],
            [_OneCommands, _TwoCommands],
            id="list",
        ),
        pytest.param(lambda: None, [], id="none"),
    ],
)
def test_collect_command_sets_flattens_hook_returns(
    returned: Callable[[], object], expected_types: list[type]
) -> None:
    manager = _manager_with("commands", fabulous_register_commands=returned)

    collected = manager.collect_command_sets()

    assert [type(cs) for cs in collected] == expected_types
