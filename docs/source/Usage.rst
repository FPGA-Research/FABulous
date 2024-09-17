.. _Quick start:

Quick start
===========
.. _setup:

Prerequisites
-------------

The following packages need to be installed for generating fabric HDLs

:Python:

Version >= 3.12

:Dependencies:

.. code-block:: console

    $ sudo apt-get install python3-tk python3-virtualenv

.. note::

    If you get the warning ``ModuleNotFoundError: No module named 'tkinter'``
    or errors when installing the requirements, you have to install the
    dependencies for your specific python version. For Python 3.12 use

    .. code-block:: console

       $ sudo apt-get install python3.12-tk python3.12-virtualenv

:FABulous repository:

.. code-block:: console

    $ git clone https://github.com/FPGA-Research-Manchester/FABulous

:Virtual environment:

We recommend using python virtual environments for the usage of FABulous.
If you are not sure what this is and why you should use it, please read the
`virtualenv documentation <https://virtualenv.pypa.io/en/latest/index.html>`_.

.. code-block:: console

   $ cd FABulous
   $ virtualenv venv
   $ source venv/bin/activate

Now there is a ``(venv)`` at the beginning of your command prompt.
You can deactivate the virtual environment with the ``deactivate`` command.
Please note, that you always have to enable the virtual environment
with ``source venv/bin/activate`` to use FABulous.

:Python dependencies:

.. code-block:: console

    (venv)$ pip install -r requirements.txt


The following packages need to be installed for the CAD toolchain:


:`Yosys <https://github.com/YosysHQ/yosys>`_:
 version > 0.26+0

:`Nextpnr-generic <https://github.com/YosysHQ/nextpnr#nextpnr-generic>`_:
 version > 0.4-28-gac17c36b

.. note::

   We recommend using the `OSS CAD Suite
   <https://github.com/YosysHQ/oss-cad-suite-build>`_ to
   install the packages.

   If you just want to install Yosys using **apt**, make
   sure you have at least Ubuntu 23.10 (24.04 for the LTS
   versions) installed to meet the above requirement.


Install FABulous with "editable" option:

.. code-block:: console

    (venv)$ pip install -e .

Building Fabric and Bitstream
-----------------------------


.. code-block:: console

   (venv)$ FABulous -c <name_of_project>
   (venv)$ FABulous <name_of_project>
   
   # inside the FABulous shell
   FABulous> load_fabric
   FABulous> run_FABulous_fabric
   FABulous> run_FABulous_bitstream npnr user_design/sequential_16bit_en.v

.. note::

  You will probably receive a warning for the FASM package like the following:
      .. code-block:: text
  
          RuntimeWarning: Unable to import fast Antlr4 parser implementation.
          ImportError: cannot import name 'antlr_to_tuple' from partially initialized module 'fasm.parser' (most likely due to a circular import)

          Falling back to the much slower pure Python textX based parser
          implementation.

          Getting the faster antlr parser can normally be done by installing the
          required dependencies and then reinstalling the fasm package with:
            pip uninstall
            pip install -v fasm

  This usually happens when FASM can't find the Antlr4 package, but this is not mandatory for us.
  If you still want to fix this issue, you have to install FASM in your virtual environment from source.
  Please have a look at the `FASM documentation <https://github.com/chipsalliance/fasm>`_ for more information.
   
After a successful call with the command ``run_FABulous_fabric`` the RTL file of each of the tiles can be found in the ``Tile`` folder and the fabric RTL file can be found in the ``Fabric`` folder.

After a successful call with the command ``run_FABulous_bitstream user_design/sequential_16bit_en.v``.
The bitstream and all the log files generated during synthesis and place and route can be found under
the ``user_design`` folder. The bitstream will be named as ``sequential_16bit_en.bin``.

Running in a Docker container
-----------------------------

Within the FABulous repo we provide a Dockerfile that allows users to run the FABulous flow within a Docker container, installing all requirements automatically.

**Setting up the Docker environment**

To set up the Docker environment, navigate to the FABulous root directory and run:

.. code-block:: console

     $ docker build -t fabulous .

**Running the Docker environment**

To run the Docker environment, stay in the FABulous root directory (this is vital as the command mounts the current directory as the container's filesystem) and run:

.. code-block:: console

     $ docker run -it -v $PWD:/workspace fabulous

This will bring up an interactive bash environment within the Docker container, within which you can use FABulous as if hosted natively on your machine. When you are finished using FABulous, simply type ``exit``, and all changes made will have been made to your copy of the FABulous repository.

FABulous Environment Variables
------------------------------

FABulous can use environment variables to configure options, paths and projects. We distinguish between two types of environment variables: global and project specific environment variables.
Global environment variables are used to configure FABulous itself, while project specific environment variables are used to configure a specific FABulous project.
All environment variables can be set in the shell before running FABulous or can be set via .env files.

.. note::

   Environment variables can be set in the shell before running FABulous. Shell environment variables always have the highest priority.

Global Environment Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Global environment variables always start with ``FAB_``` and are used to configure FABulous itself.
To add a global .env file, create a file named ``.env`` in the root directory of the FABulous repository or use the ``--globalDotEnv`` command line argument when running FABulous.
The following global environment variables are available:

=================== =============================================== ===========================================================================
Variable Name        Description                                     Default Value
=================== =============================================== ===========================================================================
FAB_ROOT            The root directory of the FABulous repository   The directory where the FABulous repository is located
FAB_FABULATOR_ROOT  The root directory of the FABulator repository  <None>
FAB_YOSYS_PATH      Path to Yosys binary                            yosys  (Uses global Yosys installation)
FAB_NEXTPNR_PATH    Path to Nextpnr binary                          nextpnr-generic  (Uses global Nextpnr installation)
FAB_IVERILOG_PATH   Path to Icarus Verilog binary                   iverilog  (Uses global Icarus Verilog installation)
FAB_VVP_PATH        Path to Verilog VVP binary                      vvp  (Uses global Verilog VVP installation)
FAB_PROJ_DIR        The root directory of the FABulous project      The directory where the FABulous project is located, given by command line
=================== =============================================== ===========================================================================

Project Specific Environment Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Project specific environment variables always start with ``FAB_PROJ_`` and are used to configure a specific FABulous project.
To add a project specific .env file, create a file named ``.env`` in the ``.FABulous`` directory of the FABulous project or use the ``--projectDotEnv`` command line argument when running FABulous.
The following project specific environment variables are available:

.. note::

  The project specific environment variables overwrite the global environment variables.

=================== =============================================== ===========================================================================
Variable Name       Description                                     Default Value
=================== =============================================== ===========================================================================
FAB_PROJ_LANG       The language of the project. (verilog/vhdl)     verilog (default) or language specified by ``-w`` command line argument
=================== =============================================== ===========================================================================


