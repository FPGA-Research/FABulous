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

========================= =================================================== ===========================================================================
Variable Name              Description                                        Default Value
========================= =================================================== ===========================================================================
FAB_ROOT                  The root directory of the FABulous repository       The directory where the FABulous repository is located
FAB_FABULATOR_ROOT        The root directory of the FABulator repository      <None>
FAB_YOSYS_PATH            Path to Yosys binary                                yosys  (Uses global Yosys installation)
FAB_NEXTPNR_PATH          Path to Nextpnr binary                              nextpnr-generic  (Uses global Nextpnr installation)
FAB_IVERILOG_PATH         Path to Icarus Verilog binary                       iverilog  (Uses global Icarus Verilog installation)
FAB_VVP_PATH              Path to Verilog VVP binary                          vvp  (Uses global Verilog VVP installation)
FAB_GHDL_PATH             Path to GHDL binary                                 ghdl  (Uses global GHDL installation)
FAB_PROJ_DIR              The root directory of the FABulous project          The directory where the FABulous project is located, given by command line
FAB_MODELS_PACK           The models pack for the project                      Pointing to <project_dir>/Fabric/models_pack.<project_lang>
FAB_OSS_CAD_SUITE         Path to the oss-cad-suite installation              <None>
FAB_DEBUG                 Enable debug mode                                   False
FAB_VERBOSE               Enable verbose mode                                 0
FAB_EDITOR                Set the editor to be used by the `edit` command     <None>
========================= =================================================== ===========================================================================

Project Specific Environment Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Project specific environment variables always start with ``FAB_PROJ_`` and are used to configure a specific FABulous project.
To add a project specific .env file, create a file named ``.env`` in the ``.FABulous`` directory of the FABulous project or use the ``--projectDotEnv`` command line argument when running FABulous.
The following project specific environment variables are available:

.. note::

  The project specific environment variables overwrite the global environment variables.

=============================== ======================================================================= ===========================================================================
Variable Name                   Description                                                             Default Value
=============================== ======================================================================= ===========================================================================
FAB_PROJ_LANG                   RTL language used in FABulous project [verilog/vhdl]                    verilog (default) or language specified by ``-w`` command line argument
FAB_SWITCH_MATRIX_DEBUG_SIGNAL  Generate debug signals in switch matrix RTL implementation [True/False] True
FAB_PROJ_VERSION_CREATED        The version of FABulous used to create the project                      Same as the version of FABulous-FPGA package installed
FAB_PROJ_VERSION                The current project version                                             Same as the version of FABulous-FPGA package installed
=============================== ======================================================================= ===========================================================================
