"""Setuptools build hooks for FABulous packaging."""

from pathlib import Path
from shutil import copy2

from setuptools.command.build_py import build_py


class BuildPyWithFabulousNix(build_py):
    """Generate a build-only ``fabulous_nix`` package with required nix assets."""

    _ASSET_MAP: tuple[tuple[str, str], ...] = (
        ("flake.nix", "flake.nix"),
        ("flake.lock", "flake.lock"),
        ("pyproject.toml", "pyproject.toml"),
        ("uv.lock", "uv.lock"),
        ("nix/default.nix", "default.nix"),
        ("nix/overlay/python.nix", "overlay/python.nix"),
        ("nix/tools/fabulator.nix", "tools/fabulator.nix"),
        ("nix/tools/ghdl-bin.nix", "tools/ghdl-bin.nix"),
        ("nix/tools/nextpnr.nix", "tools/nextpnr.nix"),
        ("nix/tools/yosys.nix", "tools/yosys.nix"),
    )

    def run(self) -> None:
        super().run()
        self._build_fabulous_nix_package()

    def _build_fabulous_nix_package(self) -> None:
        project_root = Path(__file__).resolve().parent
        target_root = Path(self.build_lib) / "fabulous_nix"
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
