"""The Typer entry builds a manager and passes session plugins through."""

from pytest_mock import MockerFixture

from fabulous import fabulous as entry


def test_build_manager_passes_session_plugins(mocker: MockerFixture) -> None:
    create = mocker.patch.object(entry.FABulousPluginManager, "create")
    entry.build_plugin_manager(plugins=["mod_a", "mod_b"], skip_broken=True)
    create.assert_called_once_with(extra_plugins=("mod_a", "mod_b"), skip_broken=True)


def test_build_manager_defaults(mocker: MockerFixture) -> None:
    create = mocker.patch.object(entry.FABulousPluginManager, "create")
    entry.build_plugin_manager(plugins=None, skip_broken=False)
    create.assert_called_once_with(extra_plugins=(), skip_broken=False)
