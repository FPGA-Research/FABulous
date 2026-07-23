(bitstream)=

# Bitstream remapping

FABulous will take care when implementing the configuration logic and bitstream encoding and the mapping of this into configuration bitstreams. This can be done automatically.
However, users can influence the mapping of configuration bits into the bitstream. For our first chip, we used remapping to create a human-readable bitstream which is more convenient to modify in a hex editor, as described later in this subsection.

In the code example for a LUT, it was shown that the configuration bits are exported into the LUT interface:

```{code-block} VHDL
:emphasize-lines: 5

entity LUT4 is
 Generic ( NoConfigBits : integer := 18 );   -- has to be adjusted manually
 Port (      -- IMPORTANT: this has to be in a dedicated line
 ...
 ConfigBits : in      STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )  -- These are the configuration bits
```

Exporting configuration bits is a requirement for any primitive or switch matrix that uses configuration bits. The tile configuration bitstream is formed by concatenating first the primitive configuration bits (if primitives are available and use configuration bits) and then the switch matrix configuration bits (again, only if the switch matrix uses configuration bits) into one long tile configuration word.
This is done in the order that the primitives are declared by `BEL` entries in the tile definition. Configuration bitstream vectors are defined in the *downto* direction and the first BEL primitive configuration bits will be placed at the LSB side of the tile bitstream and the configuration switch matrix at the MSB side.

Using the **shift-register configuration mode** will form a tile configuration chain. FABulous only supports one long bit-serial configuration chain. While configuration speed could possibly be boosted by using multiple parallel (and correspondingly shorter) chains, we have not added further optimisations, because shift register configuration is inferior to frame-based configuration mode.

For **frame-based configuration mode**, FABulous will pack those configuration bits into frames. By default, FABulous will start with frame 0 and pack the first `FrameBitsPerRow` bits from the tile configuration bitstream starting with the MSBs of the tile bitstream frame-by-frame until all configuration bits are packed. This may leave some of the `FrameBitsPerRow` x `MaxFramesPerCol` possible configuration bits unused.

FABulous is recording the bitstream mapping file (in CSV format) that follows the naming convention `<tile_descriptor>_ConfigMem.init.csv` (e.g., LUT4AB_ConfigMem.init.csv). The file has `MaxFramesPerCol` lines (one per configuration frame, which includes empty frames). A line has the format:

```python
<frame_name>, \<frame_index>, \<bits_used>, \<used_bits_mask>, \<ConfigBits_ranges>
```

Where the fields mean:

- \<frame_name> is a symbolic name for a frame which is not further used internally by FABulous.

- \<frame_index> is indexed 0 to `MaxFramesPerCol` -1.

- \<bits_used> denotes the number of bits that are used in this frame and must be in the range 0 to `FrameBitsPerRow`.

- \<used_bits_mask> denotes which bits in a frame will be used. The bitmask is defined MSBs downto LSBs and a `1` denotes a used configuration bit, while a `0` denotes a gap bit that will not be used. Note that FABulous will not generate a configuration latch for those gap bits. Again, in frame-based reconfiguration, not all possible `FrameBitsPerRow` x `MaxFramesPerCol` bits will usually be used and the bitmask specifies the used and unused bits. The number of `1` entries per frame is redundant to \<bits_used>. FABulous will count the `1` entries and use that value while \<bits_used> is used for checking only.

- \<ConfigBits_ranges> denotes a comma-separated list of configuration bits (given by their index) from the tile bitstream. The field can be individual bits or ranges of tile bitstream bits in the form \<left_index>:\<right_index>. The number of specified bits has to match the number of used configuration bits as specified by the mask and the mapping is performed in the order the configuration bits are listed, as illustrated in the following figure:

  :::{figure} figs/bitstream_mask_mapping.*
  :alt: An illustration of the mapping of configuration bits as specified by the mask in the order of listing.
  :width: 60%
  :::

The following example is the FABulous-generated mapping file of the CLB implemented for our first FABulous TSMC chip.

```python
frame_name,  frame_index, bits_used, used_bits_mask,                          ConfigBits_ranges
frame0,      0,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 537:506
frame1,      1,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 505:474
frame2,      2,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 473:442
frame3,      3,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 441:410
frame4,      4,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 409:378
frame5,      5,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 377:346
frame6,      6,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 345:314
frame7,      7,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 313:282
frame8,      8,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 281:250
frame9,      9,           32,        1111_1111_1111_1111_1111_1111_1111_1111, 249:218
frame10,     10,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 217:186
frame11,     11,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 185:154
frame12,     12,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 153:122
frame13,     13,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 121:90
frame14,     14,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 89:58
frame15,     15,          32,        1111_1111_1111_1111_1111_1111_1111_1111, 57:26
frame16,     16,          26,        1111_1111_1111_1111_1111_1111_1100_0000, 25:0
frame17,     17,          0,         0000_0000_0000_0000_0000_0000_0000_0000,
frame18,     18,          0,         0000_0000_0000_0000_0000_0000_0000_0000,
frame19,     19,          0,         0000_0000_0000_0000_0000_0000_0000_0000,
```

FABulous will generate a default \<tile_descriptor>\_ConfigMem.csv, and users are not required to modify the \<tile_descriptor>\_ConfigMem.csv file. However, if FABulous finds a file called \<tile_descriptor>\_ConfigMem.csv before generating it, it will use the bitstream mapping provided instead. The following example shows the basic idea that was used to provide a human-readable bitstream encoding. It is not intended to understand the example in detail. The basic idea is to align configuration LUT function tables, settings and the switch matrix multiplexer encoding to be nibble aligned such that they are easy to find in a hex editor. For instance, in the example below, the first 8 frames are mostly encoding the LUTs where the 16 MSBs are the LUT tables and the next two nibbles are encoding a flop and carry-chain mode:

```python
frame_name, frame_index, bits_used_in_frame, used_bits_mask, ConfigBits_ranges
frame0,0,32,1111_1111_1111_1111_0001_0001_0001_0001,15:00,16,17,144,145
frame1,1,32,1111_1111_1111_1111_0001_0001_0000_0000,33:18,34,35
frame2,2,32,1111_1111_1111_1111_0001_0001_0011_0011,51:36,52,53,515:514,517:516,#,J_l_CD_BEG0,J_l_CD_BEG1
frame3,3,32,1111_1111_1111_1111_0001_0001_0011_0011,69:54,70,71,519:518,521:520,#,J_l_CD_BEG2,J_l_CD_BEG3
frame4,4,32,1111_1111_1111_1111_0001_0001_0011_0011,87:72,88,89,523:522,525:524,#,J_l_EF_BEG0,J_l_EF_BEG1
frame5,5,32,1111_1111_1111_1111_0001_0001_0011_0011,105:90,106,107,527:526,529:528,#,J_l_EF_BEG2,J_l_EF_BEG3
frame6,6,32,1111_1111_1111_1111_0001_0001_0011_0011,123:108,124,125,531:530,533:532,#,J_l_GH_BEG0,J_l_GH_BEG1
frame7,7,32,1111_1111_1111_1111_0001_0001_0011_0011,141:126,142,143,535:534,537:536,#,J_l_GH_BEG2,J_l_GH_BEG3
#,E6BEG0   ,E6BEG1   ,W6BEG0   ,W6BEG1   ,JN2BEG0  ,JN2BEG1  ,JN2BEG2  ,JN2BEG3
frame8,8,32,1111_1111_1111_1111_1111_1111_1111_1111,173:170,177:174,205:202,209:206,381:378,385:382,389:386,393:390
#,JN2BEG4  ,JN2BEG5  ,JN2BEG6  ,JN2BEG7  ,JE2BEG0  ,JE2BEG1  ,JE2BEG2  ,JE2BEG3
frame9,9,32,1111_1111_1111_1111_1111_1111_1111_1111,397:394,401:398,405:402,409:406,413:410,417:414,421:418,425:422
...
```

The more important use case of bitstream remapping is to optimize the physical
implementation of the configuration tiles. FABulous includes a corresponding
optimizer that generates the bitstream remapping files automatically. The
process is described in detail in Chung et al {cite}`10.1145/3490422.3502371`.
