Yosys models
============

All Yosys model files can be found in the `Yosys repository <https://github.com/YosysHQ/yosys>`_ under ``$YOSYS_ROOT/techlibs/fabulous/``. These files are listed below.

+---------------+-----------------------------------------------------------------------+
| File Name     | Description                                                           |
+===============+=======================================================================+
| prims_ff.v    | Fabric primitives definition                                          |
+---------------+-----------------------------------------------------------------------+
| ff_map.v      | Abitrary D-type Flip-flop with SET/RESET and ENABLE technology mapping|
+---------------+-----------------------------------------------------------------------+
| latches_map.v | Latches technology mapping                                            |
+---------------+-----------------------------------------------------------------------+
| cells_map_ff.v| LUT-4 technology mapping (can be modified to LUT-6)                   |
+---------------+-----------------------------------------------------------------------+

The current synthesis pass is built for FABulous version3. Unlike the previous two versions, the new version supports **ENABLE** and **SET/RESET** functions in D-type Flip-flops (DFF). In the pass, Yosys represents cells ``$_DFF_P_``, ``$_DFFE_PP_``, ``$_SDFF_PP?_`` and ``$_SDFFCE_PP?P_`` for DFFs (More DFF cells definitions can be found in the
`Yosys manual <https://github.com/YosysHQ/yosys-manual-build/releases/download/manual/manual.pdf>`_
Chapter 5.2). User should also define different types of DFF in the ``ff_map.v`` for DFF technology mapping.

+----------------+-------------------------------------------------------+
| $_DFF_P_       | Positive Clock edge DFF                               |
+----------------+-------------------------------------------------------+
| $_DFFE_PP_     | Positive Clock edge, High active Enable               |
+----------------+-------------------------------------------------------+
| $_SDFF_PP?_    | Positive Clock edge, High active Set/Reset            |
+----------------+-------------------------------------------------------+
| $_SDFFCE_PP?P_ | Positive Clock edge, High active Enable and Set/Reset |
+----------------+-------------------------------------------------------+

We have made a comparison between synthesis with and without **ENABLE** and **SET/RESET** DFF on the ``Murax core`` benchmark, as shown below:

+-------------+-----+-----+-----+-----+----------+------+--------+---------+---------+----------+----------+-------------+
| Name        | LUT1| LUT2| LUT3| LUT4| LUT_total| LUTFF| LUTFF_E| LUTFF_SR| LUTFF_SS| LUTFF_ESR| LUTFF_ESS| RegFile_32x4|
+=============+=====+=====+=====+=====+==========+======+========+=========+=========+==========+==========+=============+
| Murax       | 4   | 335 | 1248| 1195| 2782     | 1361 |        |         |         |          |          | 12          |
+-------------+-----+-----+-----+-----+----------+------+--------+---------+---------+----------+----------+-------------+
| Murax_dffesr| 128 | 380 | 637 | 785 | 1930     | 233  | 841    | 86      | 7       | 174      | 20       | 12          |
+-------------+-----+-----+-----+-----+----------+------+--------+---------+---------+----------+----------+-------------+

.. code-block:: none

        Ps.
        LUTFF    : DFF with no enable and no set/reset
        LUTFF_E  : synchronous enable
        LUTFF_SR : synchronous reset to 0
        LUTFF_SS : synchronous set to 1
        LUTFF_ESR: synchronous enable, synchronous reset to 0
        LUTFF_ESS: synchronous enable, synchronous set to 1

Around 30% LUT resources can be saved by *ENABLE* and *SET/RESET* functions added, so it is supported in version 3.
