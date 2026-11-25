(uv-install)=
# `uv` based setup

[uv](https://github.com/astral-sh/uv) is a high-performance Python package manager that provides faster dependency resolution and installation. While not required for end users, it offers significant speed improvements and reproducible environments.

## Installing uv

Linux/macOS:

```bash
$ curl -LsSf https://astral.sh/uv/install.sh | sh
# restart your shell or source the env snippet the installer prints
```

macOS with Homebrew:

```bash
brew install uv
```

Windows:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

PyPI:

```bash
pip install uv
```

## Install FABulous

Install FABulous as a tool along with its bundled `task` (`go-task-bin`) and
`bit_gen` (`fabulous-bit-gen`) executables so they are available globally:

```bash
uv tool install --with-executables-from go-task-bin,fabulous-bit-gen fabulous-fpga
```

:::{note}
If `task` or `bit_gen` is already installed globally on your system, omit that
package from `--with-executables-from` (or drop the flag entirely if both are
installed) so `uv` does not conflict with or shadow your existing binaries.
:::

Verify the installation:

```bash
FABulous --version
```

To upgrade later:

```bash
uv tool upgrade fabulous-fpga
```
