(install)=

# Installation Method

```{warning}
**Windows Support**

FABulous is not officially supported on native Windows. While the tool may work, you may encounter errors and unexpected behavior.
**For the best experience on Windows-based systems, we strongly recommend using Windows Subsystem for Linux (WSL).**

To set up WSL, visit: https://docs.microsoft.com/en-us/windows/wsl/install
```

We provide multiple ways to install and use FABulous.

We recommend [uv](#uv-install) for most users as it provides fast, reproducible dependency resolution. If you prefer a simpler setup using Python's built-in tooling, use [venv](#venv-install). After FABulous installation you will also need to install the [CAD tools](#cad-tool-install). If you want an all-in-one package with full encapsulation, go with [docker](#docker-install). If you want to run the GDS flow, go with [nix](#nix-install).

```{toctree}
uv
venv
cad-tool
docker
nix-env
```
