"""Tests for the plugin hookspecs module."""

import pluggy

from fabulous.plugins import hookspecs


def test_markers_are_fabulous_project() -> None:
    assert isinstance(hookspecs.hookspec, pluggy.HookspecMarker)
    assert isinstance(hookspecs.hookimpl, pluggy.HookimplMarker)


def test_all_six_hookspecs_present() -> None:
    expected = {
        "fabulous_startup",
        "fabulous_register_commands",
        "fabulous_register_code_generators",
        "fabulous_register_parsers",
        "fabulous_after_fabric_loaded",
        "fabulous_register_settings",
    }
    assert expected <= set(vars(hookspecs))


def test_init_reexports_hookimpl() -> None:
    from fabulous.plugins import hookimpl

    assert hookimpl is hookspecs.hookimpl
