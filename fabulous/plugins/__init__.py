"""FABulous plugin framework.

Re-exports the ``hookimpl`` marker and the current ``PLUGIN_API_VERSION`` so
plugin authors can write::

    from fabulous.plugins import PLUGIN_API_VERSION, hookimpl

    FABULOUS_PLUGIN_API = PLUGIN_API_VERSION
"""

from fabulous.plugins.hookspecs import PLUGIN_API_VERSION, hookimpl

__all__ = ["PLUGIN_API_VERSION", "hookimpl"]
