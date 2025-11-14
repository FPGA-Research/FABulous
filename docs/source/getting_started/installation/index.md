(install)=

# Installation Method

```{warning}
**Windows Support**

FABulous is not officially supported on native Windows. While the tool may work, you may encounter errors and unexpected behavior.
**For the best experience on Windows-based systems, we strongly recommend using Windows Subsystem for Linux (WSL).**

To set up WSL, visit: https://docs.microsoft.com/en-us/windows/wsl/install
```

We provide multiple ways to install and use FABulous.

If you would like to just get started and don't want to care about anything else, go with [venv](#venv-install). If you would like proper python package isolation and prevent dependency problem, go with [uv](#uv-install). After FABulous installation you will also need to install the [CAD tools](#cad-tool-install). If you want an all-in-one package and with absolute encapsulation, go with [docker](#docker-install). If want to run the GDS flow, go with [nix](#nix-install)

```{toctree}
venv
uv
cad-tool
docker
nix-env
```
