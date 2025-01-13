# FABulous docs

The upstream FABulous documentation is available at [https://fabulous.readthedocs.io](https://fabulous.readthedocs.io/en/latest/)


## General
Our docs are built using [Sphinx](https://www.sphinx-doc.org/en/master).
The documentation is written in [reStructuredText](https://docutils.sourceforge.io/rst.html) format.


## Prerequisites
To build the documentation, you should already have set up your virtual environment and installed the required packages to use FABulous
as described in the [README](../README.md). Make sure you have picked the right FABulous branch, you want to build the documentation for.

First source your virtual environment:
```bash
$ source venv/bin/activate
```

Then navigate to the `docs` directory and install the required pacakges:
```bash
(venv) $ cd docs
(vevn) $ pip install -r requirements.txt
```


## Building the documentation

### HTML format

To build the documentation in HTML format, run:

```bash
(venv) $ make html
```
This should create a `build/html/` directory path in the `docs` directory for the HTML documentation.

Open it with your browser:

```bash
(venv) $ xdg-open build/html/index.html
```

### PDF format

If you want to build the documentation in PDF format, you need to install additional packages.
and a working LaTeX installation on your system, you can find the needed packages in the
[LaTeXBuilder sphinx documentation](https://www.sphinx-doc.org/en/master/usage/builders/index.html#sphinx.builders.latex.LaTeXBuilder).
You also need to install [Imagemagic](https://imagemagick.org/script/index.php), which you can install via `apt-get`:

```bash
$ sudo apt-get install imagemagick
```

To build the documentation in PDF format, run:

```bash
(venv) $ make latexpdf
```

This should create a `build/latex/` directory path in the `docs` directory for the PDF documentation.
The PDF file is named `fabulous.pdf`.

Open it with your PDF viewer:

```bash
(venv) $ xdg-open build/latex/fabulous.pdf
```

### Clean the build directory

To clean the build directory, run:

```bash
(venv) $ make clean
```

This will remove the `build/` directory.

## Contributing

Thank you for considering contributing to FABulous!
If you find any issues or have any suggestions, improvements, new features or questions,
please open an [issue](https://github.com/FPGA-Research-Manchester/FABulous/issues),
start a [discussion](https://github.com/FPGA-Research-Manchester/FABulous/discussions)
or create a [pull request](https://github.com/FPGA-Research-Manchester/FABulous/pulls).
