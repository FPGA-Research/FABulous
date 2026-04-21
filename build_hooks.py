"""Setuptools build hooks for FABulous packaging."""

from pathlib import Path
from shutil import copy2, rmtree

from setuptools.command.build_py import build_py


class BuildPyWithFabulousNix(build_py):
    """Generate a build-only `fabulous_nix` package with required nix assets."""

    _PACKAGE_NAME = "fabulous_nix"

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

    def _build_fabulous_nix_package(self) -> None:
        project_root = Path(__file__).resolve().parent
        target_root = self._target_root(project_root)
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

    def _target_root(self, project_root: Path) -> Path:
        if getattr(self, "editable_mode", False):
            packages = list(self.distribution.packages or [])
            if self._PACKAGE_NAME not in packages:
                packages.append(self._PACKAGE_NAME)
            self.distribution.packages = packages
            return project_root / self._PACKAGE_NAME

        return Path(self.build_lib) / self._PACKAGE_NAME
