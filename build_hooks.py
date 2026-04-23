"""Setuptools build hooks for FABulous packaging."""

from pathlib import Path
from shutil import copy2, rmtree

from setuptools.command.build_py import build_py

_UPSTREAM_PKG = "fabulous.fabric_generator.gds_generator"
_LIBRELANE_PLUGIN_SUBPKGS: tuple[str, ...] = ("steps", "flows")


def _render_librelane_plugin_init() -> str:
    """Render the librelane_plugin_fabulous/__init__.py content."""
    subpkgs = ", ".join(repr(s) for s in _LIBRELANE_PLUGIN_SUBPKGS)
    return f'''\
"""LibreLane plugin: re-export of the FABulous GDS steps and flows.

Ships as a side-package inside the FABulous-FPGA wheel. LibreLane
auto-discovers packages whose name matches ``librelane_plugin_*`` — importing
this package walks every submodule under
``{_UPSTREAM_PKG}.{{steps,flows}}`` so their
``@Step.factory.register()`` / ``@Flow.factory.register()`` decorators fire.

Generated at build time by ``build_hooks.BuildPyWithFabulousNix`` — do not
edit by hand. The source of truth for every Step and Flow lives in
``{_UPSTREAM_PKG}``.
"""

import importlib as _importlib
import pkgutil as _pkgutil

for _sub in {subpkgs!s}:
    _pkg = _importlib.import_module(f"{_UPSTREAM_PKG}.{{_sub}}")
    for _info in _pkgutil.iter_modules(_pkg.__path__):
        _importlib.import_module(f"{_UPSTREAM_PKG}.{{_sub}}.{{_info.name}}")

del _importlib, _pkgutil
'''


class BuildPyWithFabulousNix(build_py):
    """Generate FABulous side-packages (`fabulous_nix` + `librelane_plugin_fabulous`)."""

    _NIX_PACKAGE_NAME = "fabulous_nix"
    _LIBRELANE_PLUGIN_PACKAGE_NAME = "librelane_plugin_fabulous"

    _ASSET_MAP: tuple[tuple[str, str], ...] = (
        ("flake.nix", "flake.nix"),
        ("flake.lock", "flake.lock"),
        ("build_hooks.py", "build_hooks.py"),
        ("pyproject.toml", "pyproject.toml"),
        ("uv.lock", "uv.lock"),
        ("nix/default.nix", "nix/default.nix"),
        ("nix/overlay/python.nix", "nix/overlay/python.nix"),
        ("nix/tools/fabulator.nix", "nix/tools/fabulator.nix"),
        ("nix/tools/ghdl-bin.nix", "nix/tools/ghdl-bin.nix"),
        ("nix/tools/nextpnr.nix", "nix/tools/nextpnr.nix"),
        ("nix/tools/yosys.nix", "nix/tools/yosys.nix"),
    )

    def run(self) -> None:
        super().run()
        self._build_fabulous_nix_package()
        self._build_librelane_plugin_fabulous_package()

    def _build_fabulous_nix_package(self) -> None:
        project_root = Path(__file__).resolve().parent
        target_root = self._target_root(project_root, self._NIX_PACKAGE_NAME)
        rmtree(target_root, ignore_errors=True)
        target_root.mkdir(parents=True, exist_ok=True)

        init_file = target_root / "__init__.py"
        init_file.write_text(
            '"""Build-generated FABulous Nix resources package."""\n',
            encoding="utf-8",
        )

        for source_rel, target_rel in self._ASSET_MAP:
            source_path = project_root / source_rel
            target_path = target_root / target_rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(source_path, target_path)

    def _build_librelane_plugin_fabulous_package(self) -> None:
        """Generate librelane_plugin_fabulous/ as a thin re-export side-package."""
        project_root = Path(__file__).resolve().parent
        target_root = self._target_root(
            project_root, self._LIBRELANE_PLUGIN_PACKAGE_NAME
        )
        rmtree(target_root, ignore_errors=True)
        target_root.mkdir(parents=True, exist_ok=True)
        (target_root / "__init__.py").write_text(
            _render_librelane_plugin_init(), encoding="utf-8"
        )

    def _target_root(self, project_root: Path, package_name: str) -> Path:
        if getattr(self, "editable_mode", False):
            packages = list(self.distribution.packages or [])
            if package_name not in packages:
                packages.append(package_name)
            self.distribution.packages = packages
            return project_root / package_name

        return Path(self.build_lib) / package_name
