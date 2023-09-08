.. _Quick start:

Quick start
===========
.. _setup:

Prerequisites
-------------

The following packages need to be installed for generating fabric HDLs

:FABulous repository:

.. code-block:: console

    git clone https://github.com/FPGA-Research-Manchester/FABulous

:Python:
 version >= 3.9

:python dependencies:

.. code-block:: console

    pip3 install -r requirements.txt

This will also require installing `Tkinter` for the TCL facilities. To install `Tkinter` on Ubuntu, run:

.. code-block:: console

    sudo apt-get install python3-tk

The following packages need to be installed for the CAD toolchain:

:`Yosys <https://github.com/YosysHQ/yosys>`_:
 version > 0.26+0

:`Nextpnr-generic <https://github.com/YosysHQ/nextpnr#nextpnr-generic>`_:
 version > 0.4-28-gac17c36b

Install FABulous with "editable" option:
.. code-block:: console

    pip3 install -e .

Building Fabric and Bitstream
-----------------------------


.. code-block:: console

   FABulous -c <name_of_project>
   FABulous <name_of_project>
   # inside the FABulous shell
   load_fabric
   run_FABulous_fabric
   run_FABulous_bitstream npnr user_design/sequential_16bit_en.v


After a successful call with the command ``run_FABulous_fabric`` the RTL file of each of the tiles can be found in the ``Tile`` folder and the fabric RTL file can be found in the ``Fabric`` folder.

After a successful call with the command ``run_FABulous_bitstream npnr user_design/sequential_16bit_en.v``.
The bitstream and all the log files generated during synthesis and place and route can be found under
the ``user_design`` folder. The bitstream will be named as ``sequential_16bit_en.bin`` The above command is using
the ``npnr`` options which suggest we are using Yosys for synthesis and Nextpnr for placement and routing. Another
option would be using ``vpr``, which will allow for using Yosys for synthesis and VPR for placement and routing.
(currently, the VPR flow is not working after the refactoring)


Running in a Docker container
-----------------------------

Within the FABulous repo we provide a Dockerfile that allows users to run the FABulous flow within a Docker container, installing all requirements automatically.

:Setting up the Docker environment:

To set up the Docker environment, navigate to the FABulous root directory and run:

.. code-block:: console

     docker build -t fabulous .

:Running the Docker environment:

To run the Docker environment, stay in the FABulous root directory (this is vital as the command mounts the current directory as the container's filesystem) and run:

.. code-block:: console

     docker run -it -v $PWD:/workspace fabulous

This will bring up an interactive bash environment within the Docker container, within which you can use FABulous as if hosted natively on your machine. When you are finished using FABulous, simply type ``exit``, and all changes made will have been made to your copy of the FABulous repository.

