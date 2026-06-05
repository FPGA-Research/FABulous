"""FABulous plugin framework.

Re-exports the ``hookimpl`` marker so plugin authors can write::

    from fabulous.plugins import hookimpl
"""

from fabulous.plugins.hookspecs import hookimpl

__all__ = ["hookimpl"]
