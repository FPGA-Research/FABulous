(nix-install)=
# Nix-based Development Environment

For the GDS backend flow, we use [Nix](https://nixos.org/) as our environment manager and development tool. Nix provides a reproducible, isolated environment for development and usage, ensuring that all dependencies are correctly managed. This is especially useful for complex EDA toolchains that have many dependencies and require specific versions of libraries and tools to function correctly.

## Setting Up the Nix Environment

You can install the Nix environment by running the following command:

```bash
FABulous install-nix
```

Or follow [this guide](https://github.com/fossi-foundation/nix-eda/blob/main/docs/installation.md#i-dont-have-nix) to install it manually.

The `FABulous install-nix` command will download and run the Nix installation scripts with installation cache set up to speed up the process. Note that during the installation you will be prompted to provide `sudo` access. If this is not possible, you can try installing Nix as a standalone executable by following this [guide](https://nixos.org/download.html#nix-standalone).

## Already have Nix setup

If you already have Nix installed, you will need to add the binary cache yourself and enable the experimental feature, `flake`. For more details check the following [guide](https://github.com/fossi-foundation/nix-eda/blob/main/docs/installation.md#i-already-have-nix).

## Activating the Nix Shell

Once the Nix environment is set up, you can activate the development shell by running:

```bash
# with a bash shell
nix develop

# if you use zsh or fish
nix develop .#zsh
nix develop .#fish

```

On first start this will take a bit of time. Subsequent starts will be much faster. This command sets up the environment with the necessary dependencies and tools required for FABulous development and usage. After running it, your shell prompt should change, indicating that you are now in the Nix development environment.

We recommend running a quick smoke test to ensure everything is working correctly. You can do this by running:

```bash
which openroad
which yosys
```

You should see the paths to the `openroad` and `yosys` executables printed, and they should point to the Nix store paths.

For `openroad`, you might see something like:

```bash
/nix/store/fkpj5szgsm7ydnykm7zcsvxqdmklf0m3-devshell-dir/bin/openroad
```

This indicates that the `openroad` tool is correctly installed and available in your Nix development environment. You should see similar output for `yosys`. If the commands point back to your system's default installation paths, the Nix environment is not set up correctly. This can happen if another environment was active before you ran `nix develop`. In that case, open a new terminal and make sure to deactivate any active environment (for example, run `deactivate`) before running `nix develop`.
