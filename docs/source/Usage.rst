.. _Quick start:

Quick start
===========
.. _setup:

Prerequisites
-------------

The following packages need to be installed for generating fabric HDLs

:Python:

Version >= 3.9

:Dependencies:

.. code-block:: console

    $ sudo apt-get install python3-tk python3-virtualenv

:FABulous repository:

.. code-block:: console

    $ git clone https://github.com/FPGA-Research-Manchester/FABulous

:Virtual environment:

We recommend using python virtual environments for the usage of FABulous.
If you are not sure what this is and why you should use it, please read the
:`virtualenv documentation <https://virtualenv.pypa.io/en/latest/index.html>`_:

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


The following packages need to be installed for the CAD toolchain

:`Yosys <https://github.com/YosysHQ/yosys>`_:
 version > 0.26+0

:`Nextpnr-generic <https://github.com/YosysHQ/nextpnr#nextpnr-generic>`_:
 version > 0.4-28-gac17c36b

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

.. note:
  You will probably recieve a Warning for the FASM package like the following:
  
  ```
  RuntimeWarning: Unable to import fast Antlr4 parser implementation.
  ImportError: cannot import name 'antlr_to_tuple' from partially initialized module 'fasm.parser' (most likely due to a circular import)

  Falling back to the much slower pure Python textX based parser
  implementation.

  Getting the faster antlr parser can normally be done by installing the
  required dependencies and then reinstalling the fasm package with:
    pip uninstall
    pip install -v fasm

  ```
  
  This usually happens when FASM can't find the Antlr4 package, but this is not mendatory for us.
  If you still want to fix this issue, you have to install FASM in your virtual environment from source.
  Please have a look at the :`FASM documentation <https://github.com/chipsalliance/fasm>`_ for more information.
   
After a successful call with the command ``run_FABulous_fabric`` the RTL file of each of the tiles can be found in the ``Tile`` folder and the fabric RTL file can be found in the ``Fabric`` folder.

After a successful call with the command ``run_FABulous_bitstream user_design/sequential_16bit_en.v``.
The bitstream and all the log files generated during synthesis and place and route can be found under
the ``user_design`` folder. The bitstream will be named as ``sequential_16bit_en.bin``

Running in a Docker container
-----------------------------

Within the FABulous repo we provide a Dockerfile that allows users to run the FABulous flow within a Docker container, installing all requirements automatically.

:Setting up the Docker environment:

To set up the Docker environment, navigate to the FABulous root directory and run:

.. code-block:: console

     $ docker build -t fabulous .

:Running the Docker environment:

To run the Docker environment, stay in the FABulous root directory (this is vital as the command mounts the current directory as the container's filesystem) and run:

.. code-block:: console

     $ docker run -it -v $PWD:/workspace fabulous

This will bring up an interactive bash environment within the Docker container, within which you can use FABulous as if hosted natively on your machine. When you are finished using FABulous, simply type ``exit``, and all changes made will have been made to your copy of the FABulous repository.

