# FABulous bitstream generation

## Bitstream for a single tile

The fabric description file contains a table with the allocation of all tiles, like for example:

|FabricBegin| | | | | | | | | |
|---|---|---|---|---|---|---|---|---|---|
|NULL|N_term_single2|N_term_single2|N_term_single|N_term_single|N_term_single|N_term_single|N_term_single|N_term_single|NULL|
|W_IO|RegFile|DSP_top|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_bot|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_top|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_bot|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_top|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_bot|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_top|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|W_IO|RegFile|DSP_bot|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|LUT4AB|CPU_IO|
|NULL|S_term_single2|S_term_single2|S_term_single|S_term_single|S_term_single|S_term_single|S_term_single|S_term_single|NULL|
|**FabricEnd**|

Let us take tile type LUT4AB as an example for the bitstream. This tile has the following BELs:

| | | |
|---|---|---|
|BEL|LUT4c_frame_config.vhdl|LA_|
|BEL|LUT4c_frame_config.vhdl|LB_|
|BEL|LUT4c_frame_config.vhdl|LC_|
|BEL|LUT4c_frame_config.vhdl|LD_|
|BEL|LUT4c_frame_config.vhdl|LE_|
|BEL|LUT4c_frame_config.vhdl|LF_|
|BEL|LUT4c_frame_config.vhdl|LG_|
|BEL|LUT4c_frame_config.vhdl|LH_|
|BEL|MUX8LUT_frame_config.vhdl|
|MATRIX|LUT4AB_switch_matrix.VHDL|
|EndTILE|

These are 8 LUT BELs (each of which use 18 configuration bits) and a MUX8LUT (which uses 2 configuration bits). The latter BEL is used to cascade multiple smaller LUTs to implement one or more larger LUTs, if needed. The LUT4AB tile also provides a switch matrix (which uses 392 configuration bits).

The configuration bits for each LUT4c BEL are:

	- [15…0]	LUT init value (the truth table)
	- [16]		c_out_mux; ‘1’: use flip flop output, ‘0’: use combinatorial LUT output
	- [17]		c_I0mux; ‘1’: use I0 as Carry in; ‘0’ normal mode (I0 driven by  input routing multiplexer)

The 2 configuration bits of the MUX8LUT BEL describe if we cascade to implement 4 x LUT5, 2 x LUT6 or 1 x LUT7.

The switch matrix is generated from the adjacency table ```LUT4AB_switch_matrix.csv```.

In that file, each row describes one configurable switch matrix multiplexer. The exact encoding of switch matrix multiplexers is defined in function TODO where we generate the multiplexer and where we write a dictionary for the final bitstream assembly.
The configuration bits of the individual switch matrix multiplexers are concatenated in the order they appear in the adjacency table, as can be seen in the generated RTL code:

```
-- switch matrix multiplexer  N1BEG0 		MUX-4
N1BEG0_input 	 <= J_l_CD_END1 & JW2END3 & J2MID_CDb_END3 & LC_O after 80 ps;
N1BEG0	<= N1BEG0_input(TO_INTEGER(UNSIGNED(ConfigBits(1 downto 0))));

-- switch matrix multiplexer  N1BEG1 		MUX-4
N1BEG1_input 	 <= J_l_EF_END2 & JW2END0 & J2MID_EFb_END0 & LD_O after 80 ps;
N1BEG1	<= N1BEG1_input(TO_INTEGER(UNSIGNED(ConfigBits(3 downto 2))));

…

-- switch matrix multiplexer  J_l_GH_BEG3 		MUX-4
J_l_GH_BEG3_input 	 <= JW2END4 & W2END0 & E6END0 & N4END0 after 80 ps;
J_l_GH_BEG3	<= J_l_GH_BEG3_input(TO_INTEGER(UNSIGNED(ConfigBits(391 downto 390))));
```

When generating the Multiplexers, FABulous is writing metadata that contains a dictionary that denotes for each possible switch matrix multiplexer setting the corresponding bits.

A tile bitstream is formed by concatenating all configuration bits of all BELs in exactly the order as specified in the LUT4AB tile descriptor followed by the switch matrix configuration bits.
Note that all BELs (including the LUTs, DSPs, etc.) and the switch matrix expose their configuration bits in the respective BEL interface and the configuration bits are stored centralized in a module <tile_type>_ConfigMem, which is provided in each tile.
For a LUT4AB tile, the concatenated tile bitstream is:

| | |
|---|---|
|[17…0]|LUT LA|
|[35…18]|LUT LB|
|[53…36]|LUT LC|
|[71…54]|LUT LD|
|[89…72]|LUT LE|
|[107…90]|LUT LF|
|[125…108]|LUT LG|
|[143…126]|LUT LH|
|[145…144]|MUX8LUT|
|[537…146]|Switch matrix|

The bold numbers are the base configuration bit offsets for the different BELs and the switch matrix. For instance, to configure the C-LUT (LC) as a 4-input AND gate using the flip-flop output and not using the carry chain, we have to set the tile configuration bits:

| | |
|---|---|
|[53]|‘0’	# no carry chain|
|[52]|‘1’	# use flip-flop output|
|[51…36]|‘1000_0000_0000_0000’	# AND truth table|

In order to translate a FASM switch matrix routing entry into the tile configuration, we look up the FASM entry in the corresponding tile type switch matrix routing dictionary (file TODO) and add the base bit offset (here 146) to the reported bits.
For instance, to configure the switch matrix setting JW2END0  N1BEG1, we set tile configuration bits [149]=’1’ and [148]=’0’.

## Shift register configuration mode

In shift register configuration mode, the tile configuration bitstream is implemented as a single long shift register. At the moment we configure bitserial. To speed this up, multiple parallel chains (e.g., 32) maybe used. However, bitserial mode is expensive as it needs flip flops (rather than latches) and it is not well suited for partial reconfiguration.
Therefore, we recommend shift register configuration only for tiny fabrics (less than 200 LUTs) as frame-based reconfiguration is in almost any case superior.

## Frame-based configuration

A typical CLB tile with 8 LUTs will have somewhere between 500 and 1500 configuration bits. This is mostly depending on the LUT size and switch matrix multiplexer encoding (e.g. binary encoded versus one-hot).
These configuration bits have to be packed into i configuration frames with a tile frame data width of j bits. Ideally, i and j are about the same for minimal wire cost. In FABulous, we use j horizontal frame data bits per CLB row. This means that we use the same number of horizontal fame data bits for all tile types. The number of configuration frames (which correspond to an equal number of vertical select frame lines), will be adjusted for the actual total number of required tile configuration bits. For example, a DSP tile commonly needs fewer configuration bits as a LUT tile.

As a pragmatic solution, we defined the frame data width j=32 bits in FABulous. This fits well most practical requirements and makes it easy to interface the configuration logic with standard buses.

For the LUT2AB tile with 538 tile configuration bits, we have selected i=20 configuration frames. This results in i x j = 640 addressable configuration bits. In this example, we will leave 640 – 538 = 102 addressable configuration bits unused in each LUT4AB tile. Note that no latches will be generated for those unused configuration bits.

By default, FABulous is tightly packing the used configuration bits (538 for the LUT4AB example) in their original order into 32-bit frames (starting with frame 0).
However, a user can specify a tile configuration mapping file that looks as follows (see file LUT4AB_ConfigMem.csv for the full example):

```
#frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges
frame0,0,32,1111_1111_1111_1111_0001_0001_0001_0001,15:00,16,17,144,145
frame1,1,32,1111_1111_1111_1111_0001_0001_0000_0000,33:18,34,35
frame2,2,32,1111_1111_1111_1111_0001_0001_0011_0011,51:36,52,53,515:514,517:516,#,J_l_CD_BEG0,J_l_CD_BEG1
frame3,3,32,1111_1111_1111_1111_0001_0001_0011_0011,69:54,70,71,519:518,521:520,#,J_l_CD_BEG2,J_l_CD_BEG3
```

The important information in each line (i.e. a tile configuration frame) is a bitmask that is for each frame denoting which addressable configuration bits will be used. For instance in frame0, we are using 20 configuration bits (out of the 32 possible configuration bits). The bitmask is specified MSB to LSB index [31…0].

After the bit mask, we specify a list of tile configuration bits in exactly the same order as the bit mask. These tile configuration bits will be mapped to the frame configuration bits.

For example, the 20 bits of frame0 are specified as:

```frame0,0,32,1111_1111_1111_1111_0001_0001_0001_0001,15:00,16,17,144,145```

This will map tile configuration bit [15] to bit 31 in frame0, 14 to bit 30 and so forth until tile configuration bit 145 is mapped to bit 0 in frame0. Therefore, the number of tile configuration bits has to match the number of ones in the frame mask. Ranges of tile configuration bits can be specified with the : operator. In the example, the tile configuration bits 15:0 are the init values of the A-LUT and they will be mapped to the 16 MSBs in frame0.

Future versions of FABulous will use the bitstream mapping feature for optimizing the physical implementation. In our first test chip, we used this feature to create a more human readable bitstream. For instance, we use this to locate the A-LUT to H-LUT init values in the first 8 frames at the high word position. The configuration modes are shown by nibbles (which will show up as one digit in a hex editor). Similarly, most multiplexers are represented by a single hex digit.

## Bitstream assembly and configuration frame addressing

Configuration frames are composed by concatenating the same configuration frame index for an entire resource column. For instance, in our example, we are considering an FPGA fabric with 8 rows and 10 columns. This corresponds to resource columns with 8 CLBs, 8 RegFiles or 4 DSPs (DSPs take two vertically aligned tiles).
Each configuration frame is masked by a frame_address_mask in 32 bits. ```frame_address_mask[31:27]``` performs as binary index to indicate the column index. ```frame_address_mask[19:0]``` performs as one-hot data code to index the frame address.

In the following example, the first line is the frame_address_mask, ```frame_address_mask[31:27] = 00100``` presents the 8th column (X7), ```frame_address_mask[19:0] = 0000_0000_0000_0000_0010``` presents 2nd frame (frame1). The rest 8 lines binary bits will be masked to all LUT4ABs' frame1 at column X7.

```
20 00 00 02
FF FE FF FE
FF FE 00 00
FF FF FF FF
00 00 00 00
FF FF FF FF
00 00 00 00
FF FE FF FE
FF FE FF FE
```


