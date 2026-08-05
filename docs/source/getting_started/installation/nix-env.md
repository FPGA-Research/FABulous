(nix-install)=
# Nix-based Development Environment

For the GDS backend flow, we use [Nix](https://nixos.org/) as our environment manager and development tool. Nix provides a reproducible, isolated environment for development and usage, ensuring that all dependencies are correctly managed. This is especially useful for complex EDA toolchains that have many dependencies and require specific versions of libraries and tools to function correctly.

## Setting Up the Nix Environment

You can install the Nix environment by running the following command:

```bash
FABulous install nix
```

Or follow [this guide](https://github.com/fossi-foundation/nix-eda/blob/main/docs/installation.md#i-dont-have-nix) to install it manually.

The `FABulous install nix` command will download and run the Nix installation scripts with installation cache set up to speed up the process. Note that during the installation you will be prompted to provide `sudo` access. If this is not possible, you can try installing Nix as a standalone executable by following this [guide](https://nixos.org/download.html#nix-standalone).

## Already have Nix setup

If you already have Nix installed, you will need to add the binary cache yourself and enable the experimental feature, `flake`. For more details check the following [guide](https://github.com/fossi-foundation/nix-eda/blob/main/docs/installation.md#i-already-have-nix).

## Entering the Nix Environment

The recommended way to enter the Nix development environment is:

```bash
FABulous nix-env
```

This command will:

1. Locate the `flake.nix` at the installed package data
2. Deactivate any active virtual environment or conda environment that could conflict
3. Set up the Nix development shell with all EDA tools (Yosys, NextPNR, OpenROAD, GHDL, etc.)
4. Verify that the tools are correctly sourced from the Nix store
5. Drop you into your preferred shell (auto-detected from `$SHELL`)

On first start this will take a bit of time as Nix downloads and builds the required packages. Subsequent starts will be much faster thanks to the Nix binary cache.

### Options

You can customize the behavior with the following options:

```bash
# Use a specific shell (bash, fish, or zsh)
FABulous nix-env --shell bash
FABulous nix-env --shell fish

# Skip the EDA tool verification check
FABulous nix-env --no-check

# Point to a specific directory containing flake.nix
FABulous nix-env --flake-dir /path/to/fabulous
```

### Tool verification

By default, `FABulous nix-env` silently smoke test that software are available and sourced from the Nix store (`/nix/store/...`). If any tool is missing or not from the Nix store, the command will print an error and exit. You can skip this check with `--no-check`.

### Shell compatibility

`FABulous nix-env` handles a known issue where fish shell re-orders PATH entries on startup, which can cause system-installed tools to shadow Nix tools. The command automatically re-prepends Nix paths after fish's configuration files have loaded.

## Manual Nix Shell Activation

You can also activate the development shell manually using `nix develop`:

```bash
# with a bash shell
nix develop

# if you use zsh or fish
nix develop .#zsh
nix develop .#fish
```

Note that when using `nix develop` directly, you may need to manually deactivate any active virtual environments first, and the automatic tool verification will not run.

## Verifying the Environment

To verify the environment is set up correctly, you can run:

```bash
which openroad
which fab-yosys
```

You should see paths pointing to the Nix store, for example:

```bash
/nix/store/fkpj5szgsm7ydnykm7zcsvxqdmklf0m3-devshell-dir/bin/openroad
```

If the commands point back to your system's default installation paths, the Nix environment is not set up correctly. This can happen if another environment was active before you entered the Nix shell. In that case, open a new terminal and use `FABulous nix-env` to enter a clean environment.

## Using FABulous as a flake input (downstream projects)

The sections above cover developing FABulous itself. If you are instead building a project _on top of_ FABulous, such as a chip or fabric that you harden to GDS, you do not vendor the toolchain yourself. You add FABulous's flake as an input, compose its overlay, and build your project shell from `pkgs.fabulous-shell`.

FABulous exposes `overlays.default`, which contributes the following to any nixpkgs instance you apply it to:

| Attribute | What it is |
| --- | --- |
| `fabulous` | The `FABulous`, `fabulous`, and `librelane` CLIs, wrapped with the toolchain on `PATH` |
| `fabulous-shell` | A ready-to-use, non-editable development shell |
| `fab-yosys` | Yosys with the `ghdl` plugin bundled, installed as `fab-yosys` |
| `fab-nextpnr` | nextpnr, generic architecture |
| `fab-ghdl` | GHDL (prebuilt binary) |
| `fabulator` | The fabric visualiser |

`fabulous-shell` contains the `librelane` CLI with the `librelane_plugin_fabulous` GDS plugin already discovered, the FABulous CLIs, the full EDA toolchain (Yosys, NextPNR, OpenROAD, GHDL, and the rest), and FABulous's Python environment pinned by FABulous's `uv.lock`.

It is overridden the same way `librelane-shell` is, with the same argument names:

- `extra-packages`, the non-Python tools your project needs (simulators, waveform viewers, `make`), as a list.
- `extra-python-packages`, your project's own Python packages, as a function `ps: [ ... ]`.
- `extra-env`, additional environment variables, as a list of `{ name; value; }`.
- `python-env`, the Python environment wholesale, covered under [Bringing your own uv.lock](#bringing-your-own-uvlock) below.

`extra-python-packages` selects from `pkgs.fabulous-python`, described next: an ordinary nixpkgs Python interpreter whose package set is FABulous's `uv.lock`.

Every attribute above is also a flake output, so `nix build github:FPGA-Research/FABulous#fab-yosys` works without composing anything.

### Example

```nix
{
  inputs.fabulous.url = "github:FPGA-Research/FABulous";

  # librelane, nix-eda and the nixpkgs closure they share come from the
  # fossi-foundation cache. FABulous's own derivations are not published to a
  # binary cache yet, so the first `nix develop` still builds those from source.
  nixConfig = {
    extra-substituters = [ "https://nix-cache.fossi-foundation.org" ];
    extra-trusted-public-keys = [
      "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
    ];
  };

  outputs =
    { self, fabulous, ... }:
    let
      system = "x86_64-linux";
      # FABulous's own composed package set: nixpkgs plus nix-eda, librelane,
      # and FABulous. `fabulous.overlays.default` expects those other overlays
      # already applied, so prefer this unless you compose the full stack
      # yourself.
      pkgs = fabulous.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.fabulous-shell.override {
        # Non-Python tools this project brings itself.
        extra-packages = with pkgs; [ iverilog verilator gtkwave gnumake ];
        # This project's own Python verification tooling.
        extra-python-packages = ps: with ps; [ cocotb pytest ];
      };
    };
}
```

Enter it with `nix develop`, then drive the flow as usual. For example, harden a tile through the plugin (see [Hardening through the LibreLane plugin](../../user_guide/building_doc/librelane_plugin.md)):

```bash
nix develop
librelane path/to/tile/config.yaml   # sky130A PDK resolved as usual
```

The `librelane` in this shell already has the FABulous plugin. Confirm with `librelane --version`, which lists `librelane_plugin_fabulous` under _Discovered plugins_.

### The Python environment

`pkgs.fabulous-python` is an ordinary nixpkgs Python interpreter whose package set is FABulous's `uv.lock`. Every package the lock resolves is converted into that set, so the versions are uv's resolution rather than whatever nixpkgs happens to ship, and FABulous composes like any other Python package:

```nix
pkgs.fabulous-python.withPackages (ps: [ ps.fabulous-fpga ps.cocotb ])
pkgs.fabulous-python.pkgs.fabulous-fpga            # as a propagatedBuildInput
pkgs.fabulous-python-env                           # FABulous + tkinter, prebuilt
```

The conversion is generated from `uv.lock`, so `uv lock` on FABulous's side is the only thing that moves it — there is no hand-written list of packages or versions to keep in step.

Scoping matters here: the converted packages live on this interpreter only. `pkgs.python3` in the same nixpkgs instance is untouched, so applying FABulous's overlay does not change the Python anything else in your flake builds against.

Three packages deliberately keep nixpkgs' versions rather than the lock's: `wheel`, `packaging` and `tomli`. nixpkgs' own `buildPythonPackage` is built from them, so converting them would require them to build themselves. All three are build tooling rather than anything FABulous imports, and nixpkgs' versions satisfy its constraints.

```{note}
`pkgs.fabulous-python` and everything built from it cannot be installed on a case-insensitive `/nix`. FABulous ships both a `FABulous` and a `fabulous` command; on such a store the two are one path, and the wheel installer nixpkgs builds with refuses to overwrite, so the build fails outright. This is specific to the nixpkgs conversion — the uv2nix virtualenv behind the development shells installs differently and is unaffected. The Nix installer creates a case-sensitive store volume on macOS by default, so this normally does not arise.
```

(bringing-your-own-uvlock)=
### Bringing your own uv.lock

`extra-python-packages` covers a project whose Python dependencies FABulous's lock already resolves. When that is not true — you need a package the lock does not contain, or a different version of one it pins — build the environment from your own `uv.lock` instead and pass it as `python-env`.

Your lock resolves `fabulous-fpga` as an ordinary dependency alongside your own, so `uv` settles every shared version in a single resolution and a real conflict surfaces as a `uv` resolution error rather than at runtime:

```nix
let
  pkgs = fabulous.legacyPackages.${system};
  workspace = pkgs.loadFabulousWorkspace ./.;
  venv =
    (pkgs.mkFabulousPythonSet { inherit workspace; }).mkVirtualEnv "chip-env"
      workspace.deps.default;
in
{
  devShells.${system}.default = pkgs.fabulous-shell.override {
    python-env = venv;
    extra-packages = with pkgs; [ iverilog gnumake ];
  };
}
```

| Attribute | What it does |
| --- | --- |
| `loadFabulousWorkspace` | Loads a `uv.lock` into a uv2nix workspace. Re-exported so FABulous stays your only flake input — otherwise you would take `uv2nix`, `pyproject-nix` and `build-system-pkgs` as inputs too and have to keep their revisions in step with the ones FABulous built against. |
| `mkFabulousPythonSet` | Turns that workspace into a Python package set with FABulous's build fixups already composed in. Takes `sourcePreference` (default `"wheel"`) and `overrides`, a list of extra uv2nix overlays applied last — that is where `workspace.mkEditablePyprojectOverlay` goes if your own sources should be editable. |

This route trades away the nixpkgs composability above: the result is a sealed virtualenv, not a Python set, so it cannot be passed to `withPackages` or taken as a `propagatedBuildInput`. Prefer `extra-python-packages` unless you specifically need your own lock.

Upgrades stay on the side that owns them:

```bash
nix flake update fabulous                 # FABulous's Python versions and its toolchain
uv lock --upgrade-package fabulous-fpga   # only if you keep your own lock
```
