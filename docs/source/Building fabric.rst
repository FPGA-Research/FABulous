Building fabric
===============

The user can run the flow step by step as well (see below for instructions on building HDLs):

.. figure:: figs/FABulous_flow2.*
        :width: 80%
        :align: center

Other than building the fabric with the ``run_FABulous_fabric`` command as shown in the :ref:`Quick start`, the user can
also build the fabric step by step to suit what they need. We will demonstrate this in the following section from
creating scratch. The following is assuming your current directory is in `$FAB_ROOT` and all the pre-request set up are
completed.

#. Create a new project

   .. prompt:: bash FABulous>

        FABulous -c demo

This will create a new project named ``demo`` in the current directory.

#. Running the FABulous shell

   .. prompt:: bash FABulous>

        FABulous demo

And now, we will be in the FABulous shell. After running the above command, the current working directory will be
moved into the project directory, which is ``demo`` in this case.

#. Load the fabric CSV definition file

   .. prompt:: bash FABulous>

        load_fabric

This command will load in the fabric definition file with the name ``fabric.csv`` in the current directory. If the
definition file is in another directory or named differently, the user can specify the path as an argument to the
command. For example: ``load_fabric fabric2.csv``. From this point onwards, all the files read and write commands, will
be relative to where the specified directory of the ``<definition>.csv`` is located. For example, if the definition file
located at ``some_path/<definition>.csv``, then all the file's read and write commands will be relative to ``some_path``.

#. Generate switch matrix

   .. prompt:: bash FABulous>

        gen_switch_matrix LUT4AB RAM_IO

The above command will generate the switch matrix for the ``LUT4AB`` tile and the ``RAM_IO`` tile. The switch matrix
generated will be based on the ``MATRIX`` entry of the tile definition in the fabric definition file. If the provided
directory is a ``.list`` file, then we will generate a switch matrix for the tile, based on the fabric definition file
and add the content in the ``list`` file to the matrix. If the provided file is a ``.csv`` file, the tool will just load
the data in, and generate a switch base on the data. Finally, if providing a ``.v`` or ``.vhdl`` file, the tool will skip
matrix generation for the tile, and will use the provided file as the switch matrix.

        .. note::
                During model generation, the given file for ``MATRIX`` entry needs to be either a ``.list`` or ``.csv``
                file.


#. Generate the configuration storage (RTL).

   .. prompt:: bash FABulous>

        gen_config_mem LUT4AB RAM_IO

The above command will generate the configuration storage for the ``LUT4AB`` tile and the ``RAM_IO`` tile. If a
``<tile>_ConfigMem.csv`` file does not exist in the ``Tile/<tile>`` directory, then the command will generate a new
``<tile>_ConfigMem.csv`` file.


#. Generate the actual tiles (RTL).

   .. prompt:: bash FABulous>

        gen_tile LUT4AB RAM_IO

The above command will generate the actual tiles for the ``LUT4AB`` tile and the ``RAM_IO`` tile.

All the files generated will be located in the respective tile directory. i.e RTL for ``LUT4AB`` will be in ``Tile/LUT4AB/``

We will need to run the above commands for all the tiles to get all the RTL of all the tiles, which is quite tedious to
do. As a result, the following command will generate all the RTL for all the tiles in the fabric including all the super
tiles within the fabric.

   .. prompt:: bash FABulous>

        gen_all_tile


#. Generate the entire fabric (RTL).

   .. prompt:: bash FABulous>

        gen_fabric

#. Generate Verilog top wrapper.

   .. prompt:: bash FABulous>

        gen_top_wrapper


#. Generate the nextpnr model.

   .. prompt:: bash FABulous>

        gen_model


#. Generate the meta data list for FASM --> Bitstream

   .. prompt:: bash FABulous>

        gen_bitStream_spec
