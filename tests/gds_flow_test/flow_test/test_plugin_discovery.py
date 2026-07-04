"""Auto-discovery tests for the `librelane_plugin_fabulous` side-package.

LibreLane auto-discovers packages named `librelane_plugin_*` and imports
them, which fires the `@Flow.factory.register()` decorators on every FABulous
Step and Flow. These tests exercise that entry point directly -- importing the
package and asserting the flows become resolvable through LibreLane's registry.

This replaces the `plugin-smoke` job of the retired
`.github/workflows/librelane-plugin.yml` nightly, and runs on every PR
instead of only nightly.

`test_fresh_import_registers_all_flows` runs in a subprocess: that is how
LibreLane discovers the plugin (a fresh interpreter that imports the package
before anything under `fabulous.fabric_generator.gds_generator` has started
initialising). Checking in-process would be unfaithful -- the package defers
adapter-flow registration when it detects it is being imported mid circular
import, and pytest's shared interpreter can trip that path depending on
collection order.
"""

import subprocess
import sys

import librelane_plugin_fabulous

# The full set of FABulous flows the plugin must make discoverable. Names are
# the class names as registered via `@Flow.factory.register()`; keep this in
# sync with the flow classes under
# `fabulous.fabric_generator.gds_generator.flows`.
EXPECTED_FLOWS: set[str] = {
    "FABulousTile",
    "FABulousFabric",
    "FABulousTileVerilogMacroFlow",
    "FABulousTileVHDLMacroFlow",
    "FABulousFabricMacroFlow",
    "FABulousFabricVHDLMacroFlow",
    "FABulousFabricOptimisationFlow",
}

_DISCOVERY_SNIPPET = """
import librelane_plugin_fabulous  # noqa: F401
from librelane.flows.flow import Flow

expected = {expected!r}
registered = set(Flow.factory.list())
missing = expected - registered
if missing:
    raise SystemExit(f"MISSING:{{sorted(missing)}}")
print("OK")
"""


class TestPluginAutoDiscovery:
    """Importing the side-package registers every FABulous flow."""

    def test_fresh_import_registers_all_flows(self) -> None:
        """A fresh interpreter importing the package registers all flows.

        Mirrors LibreLane's own plugin discovery and the retired workflow's
        `plugin-smoke` job.
        """
        result = subprocess.run(
            [sys.executable, "-c", _DISCOVERY_SNIPPET.format(expected=EXPECTED_FLOWS)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Plugin discovery failed.\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert result.stdout.strip() == "OK"

    def test_root_reexports_resolve(self) -> None:
        """`FABulousTile` / `FABulousFabric` re-export via `__getattr__`.

        The package resolves these lazily so that deferred submodule
        registration (used to dodge a circular import during LibreLane's plugin
        discovery) completes before a flow class is handed out.
        """
        assert librelane_plugin_fabulous.FABulousTile.__name__ == "FABulousTile"
        assert librelane_plugin_fabulous.FABulousFabric.__name__ == "FABulousFabric"
