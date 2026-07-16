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

The sections above cover developing FABulous itself. If you are instead building a project _on top of_ FABulous, such as a chip or fabric that you harden to GDS, you do not vendor the toolchain yourself. You add FABulous's flake as an input and build your project shell from `mkConsumerShell`.

FABulous's flake exposes one composition helper, `fabulous.lib.<system>.mkConsumerShell`, which builds a ready-to-use, non-editable shell containing:

- the `librelane` CLI with the `librelane_plugin_fabulous` GDS plugin already discovered,
- the `FABulous` and `fabulous` CLIs,
- the full EDA toolchain (Yosys, NextPNR, OpenROAD, GHDL, and the rest),
- FABulous's Python environment, pinned by FABulous's `uv.lock`.

It takes two extension surfaces so your project adds what it needs without vendoring anything:

- `extraPackages`, the non-Python tools your project needs (simulators, waveform viewers, `make`). A list, or a function `pkgs: [ ... ]` selecting from FABulous's own package set.
- `extraPythonPackages`, your project's own Python tooling (cocotb, pytest, and so on), as a function `ps: [ ... ]` selecting from nixpkgs.

FABulous's own Python packages (FABulous, librelane, the plugin) are pinned by `uv.lock` and are not overridable downstream by design. To change one, open a pull request against FABulous. Your project's verification Python in `extraPythonPackages` is yours to choose; where it shares a dependency with FABulous, FABulous's pinned version wins.

### Example

```nix
{
  inputs.fabulous.url = "github:FPGA-Research/FABulous";

  # FABulous and its toolchain are prebuilt in the fossi-foundation cache.
  # Without this, entering the shell rebuilds the whole EDA toolchain from source.
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
    in
    {
      devShells.${system}.default = fabulous.lib.${system}.mkConsumerShell {
        # Non-Python tools this project brings itself.
        extraPackages = pkgs: with pkgs; [ iverilog verilator gtkwave gnumake ];
        # This project's own Python verification tooling.
        extraPythonPackages = ps: with ps; [ cocotb pytest ];
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
