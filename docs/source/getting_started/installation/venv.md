(venv-install)=

# `venv` based setup

## Dependencies

Python >= 3.12 is required. The `venv` module is included with Python, but on some distributions you may need to install it separately:

```bash
sudo apt-get install python3-venv
```

:::{note}
If you are using an older version than Ubuntu 24.04, you may need to install tkinter.
Otherwise, you might get the warning `ModuleNotFoundError: No module named 'tkinter'`.

```bash
sudo apt-get install python3-tk
```

:::

## FABulous repository

```bash
git clone https://github.com/FPGA-Research/FABulous
```

## Virtual environment

Create and activate a virtual environment using Python's built-in `venv` module:

```bash
cd FABulous
python3 -m venv .venv
source .venv/bin/activate
```

Now there is a `(.venv)` at the beginning of your command prompt.
You can deactivate the virtual environment with the `deactivate` command.
Please note, that you always have to activate the virtual environment
with `source .venv/bin/activate` to use FABulous.

## Install FABulous

With the virtual environment activated, install FABulous:

```bash
pip install -e .
```
