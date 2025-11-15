(venv-install)=
# `venv` based setup

## Dependencies

```bash
sudo apt-get install python3-virtualenv
```

:::{note}
If you get the warning `ModuleNotFoundError: No module named 'virtualenv'`
or errors when installing the requirements, you have to install the
dependencies for your specific python version. For Python 3.12 use

```bash
sudo apt-get install python3.12-virtualenv
```

:::

:::{note}
If you are using an older version than Ubuntu 24.04, you may need to install tkinter.
Otherwise, you might get the warning `ModuleNotFoundError: No module named 'tkinter'`.

```bash
sudo apt-get install python3-tk
```

:::

## FABulous repository

```bash
git clone https://github.com/FPGA-Research-Manchester/FABulous
```

## Virtual environment

We recommend using python virtual environments for the usage of FABulous.
If you are not sure what this is and why you should use it, please read the
[virtualenv documentation](https://virtualenv.pypa.io/en/latest/index.html).

```bash
cd FABulous
virtualenv venv
source venv/bin/activate

```

Now there is a `(venv)` at the beginning of your command prompt.
You can deactivate the virtual environment with the `deactivate` command.
Please note, that you always have to enable the virtual environment
with `source venv/bin/activate` to use FABulous.
