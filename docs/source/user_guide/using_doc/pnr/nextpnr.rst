Nextpnr models
==============

After the FABulous flow has run successfully, the ``bel.txt`` and ``pips.txt`` which describe your fabric can be found in the directory ``$FAB_ROOT/<project-dir>/.FABulous``.

``bel.txt`` is the primitive description file in order of tiles

.. code-block:: none
    :emphasize-lines: 7

        #Tile_X0Y1
        X0Y1,X0,Y1,A,IO_1_bidirectional_frame_config_pass,A_I,A_T,A_O,A_Q
        X0Y1,X0,Y1,B,IO_1_bidirectional_frame_config_pass,B_I,B_T,B_O,B_Q
        X0Y1,X0,Y1,C,Config_access,
        X0Y1,X0,Y1,D,Config_access,
        #Tile_X1Y1
        X1Y1,X1,Y1,A,FABULOUS_LC,LA_I0,LA_I1,LA_I2,LA_I3,LA_Ci,LA_SR,LA_EN,LA_O,LA_Co
        X1Y1,X1,Y1,B,FABULOUS_LC,LB_I0,LB_I1,LB_I2,LB_I3,LB_Ci,LB_SR,LB_EN,LB_O,LB_Co
        X1Y1,X1,Y1,C,FABULOUS_LC,LC_I0,LC_I1,LC_I2,LC_I3,LC_Ci,LC_SR,LC_EN,LC_O,LC_Co
        X1Y1,X1,Y1,D,FABULOUS_LC,LD_I0,LD_I1,LD_I2,LD_I3,LD_Ci,LD_SR,LD_EN,LD_O,LD_Co
        X1Y1,X1,Y1,E,FABULOUS_LC,LE_I0,LE_I1,LE_I2,LE_I3,LE_Ci,LE_SR,LE_EN,LE_O,LE_Co
        X1Y1,X1,Y1,F,FABULOUS_LC,LF_I0,LF_I1,LF_I2,LF_I3,LF_Ci,LF_SR,LF_EN,LF_O,LF_Co
        X1Y1,X1,Y1,G,FABULOUS_LC,LG_I0,LG_I1,LG_I2,LG_I3,LG_Ci,LG_SR,LG_EN,LG_O,LG_Co
        X1Y1,X1,Y1,H,FABULOUS_LC,LH_I0,LH_I1,LH_I2,LH_I3,LH_Ci,LH_SR,LH_EN,LH_O,LH_Co
        X1Y1,X1,Y1,I,MUX8LUT_frame_config,A,B,C,D,E,F,G,H,S0,S1,S2,S3,M_AB,M_AD,M_AH,M_EF

+----+------+------+------+--------------+----------------------------------------------------+
|Tile|X-axis|Y-axis|Z-axis|Primitive name|Ports                                               |
+====+======+======+======+==============+====================================================+
|X1Y1|X1    |Y1    |A     |FABULOUS_LC   |LA_I0,LA_I1,LA_I2,LA_I3,LA_Ci,LA_SR,LA_EN,LA_O,LA_Co|
+----+------+------+------+--------------+----------------------------------------------------+

**arch.cc**

* void Arch::assignArchInfo()
* bool Arch::cellsCompatible(const CellInfo \**cells, int count)

**cells.cc**

* std::unique_ptr<CellInfo> create_fabulous_cell(Context \*ctx, IdString type, std::string name)
* void lut_to_lc(const Context \*ctx, CellInfo \*lut, CellInfo \*lc, bool no_dff)

``pips.txt`` is the routing resource description.

.. code-block:: none
    :emphasize-lines: 1

        X1Y1,N1BEG0,X1Y0,N1END0,8,N1BEG0.N1END0
        X1Y1,N1BEG1,X1Y0,N1END1,8,N1BEG1.N1END1
        X1Y1,N1BEG2,X1Y0,N1END2,8,N1BEG2.N1END2
        X1Y1,N1BEG3,X1Y0,N1END3,8,N1BEG3.N1END3
        X1Y1,N2BEG0,X1Y0,N2MID0,8,N2BEG0.N2MID0
        X1Y1,N2BEG1,X1Y0,N2MID1,8,N2BEG1.N2MID1
        X1Y1,N2BEG2,X1Y0,N2MID2,8,N2BEG2.N2MID2
        X1Y1,N2BEG3,X1Y0,N2MID3,8,N2BEG3.N2MID3
        X1Y1,N2BEG4,X1Y0,N2MID4,8,N2BEG4.N2MID4
        X1Y1,N2BEG5,X1Y0,N2MID5,8,N2BEG5.N2MID5
        X1Y1,N2BEG6,X1Y0,N2MID6,8,N2BEG6.N2MID6
        X1Y1,N2BEG7,X1Y0,N2MID7,8,N2BEG7.N2MID7

+-----------+-----------+----------------+----------------+-----+-------------+
|Source tile|Source port|Destination tile|Destination port|Delay|Wire name    |
+===========+===========+================+================+=====+=============+
|X1Y1       |N1BEG0     |X1Y0            |N1END0          |8    |N1BEG0.N1END0|
+-----------+-----------+----------------+----------------+-----+-------------+
