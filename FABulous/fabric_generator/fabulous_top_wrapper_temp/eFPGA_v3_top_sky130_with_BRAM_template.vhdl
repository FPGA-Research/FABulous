-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity eFPGA_top is
generic (
	FrameBitsPerRow : integer := 32;
	FrameSelectWidth : integer := 5;
	MaxFramesPerCol : integer := 20;
	NumberOfCols : integer := 19;
	NumberOfRows : integer := 16;
	RowSelectWidth : integer := 5;
	desync_flag : integer := 20;
	include_eFPGA : integer := 1
);
	port (
	A_config_C : out std_logic_vector( NumberOfRows * 4 - 1 downto 0);
	B_config_C : out std_logic_vector( NumberOfRows * 4 - 1 downto 0);
	CLK : in std_logic;
	ComActive : out std_logic;
	Config_accessC : out std_logic_vector(63 downto 0);
	FAB2RAM_A : out std_logic_vector(NumberOfRows * 4 * 2 - 1 downto 0);
	FAB2RAM_C : out std_logic_vector(NumberOfRows * 4 - 1 downto 0);
	FAB2RAM_D : out std_logic_vector(NumberOfRows * 4 * 4 -1 downto 0);
	I_top : out std_logic_vector( NumberOfRows * 2 - 1 downto 0);
	O_top : in std_logic_vector( NumberOfRows * 2 - 1 downto 0);
	RAM2FAB_D : in std_logic_vector( NumberOfRows * 4 * 4 - 1 downto 0);
	ReceiveLED : out std_logic;
	Rx : in std_logic;
	SelfWriteData : in std_logic_vector(31 downto 0);
	SelfWriteStrobe : in std_logic;
	T_top : out std_logic_vector(NumberOfRows * 2 - 1 downto 0);
	s_clk : in std_logic;
	s_data : in std_logic
);
end entity; 


architecture Behavioral of eFPGA_top is

    component eFPGA  is 
	Generic ( 
			 MaxFramesPerCol : integer := 20;
			 FrameBitsPerRow : integer := 32;
			 NoConfigBits : integer := 0 );
	Port (
	-- External IO ports exported directly from the corresponding tiles
		Tile_X0Y1_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y1_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y1_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		UserCLK	:	 in	STD_LOGIC; -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this signal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
		Tile_X0Y1_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y1_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y1_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y1_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y1_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y1_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y2_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y2_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y2_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y3_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y3_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y3_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y4_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y4_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y4_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y5_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y5_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y5_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y6_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y6_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y6_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y7_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y7_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y7_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y8_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y8_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y8_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y9_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y9_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y9_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y10_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y10_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y10_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y11_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y11_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y11_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y12_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y12_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y12_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y13_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y13_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y13_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_A_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_A_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_A_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_B_I_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_B_T_top	:	 out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_B_O_top	:	 in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
		Tile_X0Y14_A_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_A_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_A_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_A_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_B_config_C_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_B_config_C_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_B_config_C_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X0Y14_B_config_C_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D0_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D0_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D0_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D0_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D1_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D1_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D1_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D1_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D2_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D2_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D2_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D2_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D3_I0	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D3_I1	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D3_I2	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_RAM2FAB_D3_I3	:	 in	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D2_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D2_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D2_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D2_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D3_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D3_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D3_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_D3_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A0_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A0_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A0_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A0_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A1_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A1_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A1_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_A1_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_C_O0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_C_O1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_C_O2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_FAB2RAM_C_O3	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_Config_accessC_bit0	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_Config_accessC_bit1	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_Config_accessC_bit2	:	 out	STD_LOGIC; -- EXTERNAL
		Tile_X9Y14_Config_accessC_bit3	:	 out	STD_LOGIC; -- EXTERNAL
		 FrameData:     in  std_logic_vector( (FrameBitsPerRow * 16) -1 downto 0 );   -- CONFIG_PORT this is a keyword needed to connect the tile to the bitstream frame register
		 FrameStrobe:   in  std_logic_vector( (MaxFramesPerCol * 10) -1 downto 0 )    -- CONFIG_PORT this is a keyword needed to connect the tile to the bitstream frame register 

	-- global
	);
end component eFPGA ;

	component Config is
		generic (
			numberOfRows : integer := numberOfRows
		);
		port (
		  CLK : in std_logic;
		  ComActive : out std_logic;
		  ConfigWriteData : out std_logic_vector(31 downto 0);
		  ConfigWriteStrobe : out std_logic;
		  FrameAddressRegister : out std_logic_vector(31 downto 0);
		  LongFrameStrobe : out std_logic;
		  ReceiveLED : out std_logic;
		  RowSelect : out std_logic_vector(4 downto 0);
		  Rx : in std_logic;
		  SelfWriteData : in std_logic_vector(31 downto 0);
		  SelfWriteStrobe : in std_logic;
		  s_clk : in std_logic;
		  s_data : in std_logic
		);
	  end component; 

	  component Frame_Select is
		generic (
			FrameSelectWidth : integer := FrameSelectWidth;
			MaxFramesPerCol : integer := MaxFramesPerCol;
			Col : integer := NumberOfCols
		);
		port (
		  FrameSelect : in std_logic_vector(FrameSelectWidth-1 downto 0);
		  FrameStrobe : in std_logic;
		  FrameStrobe_I : in std_logic_vector(MaxFramesPerCol-1 downto 0);
		  FrameStrobe_O : out std_logic_vector(MaxFramesPerCol-1 downto 0)
		);
	  end component; 

	  component Frame_Data_Reg is
		generic (
		  FrameBitsPerRow : integer := FrameBitsPerRow;
		  RowSelectWidth : integer := RowSelectWidth;
		  Row : integer := NumberOfRows
		);
		port (
		  CLK : in std_logic;
		  FrameData_I : in std_logic_vector(FrameBitsPerRow-1 downto 0);
		  FrameData_O : out std_logic_vector(FrameBitsPerRow-1 downto 0);
		  RowSelect : in std_logic_vector(RowSelectWidth-1 downto 0)
		);
	  end component; 
	  
	signal FrameRegister : std_logic_vector((NumberOfRows*FrameBitsPerRow)-1 downto 0);
	signal FrameSelect: std_logic_vector((MaxFramesPerCol*NumberOfCols)-1 downto 0);
	signal  FrameData : std_logic_vector((FrameBitsPerRow*(NumberOfRows+2))-1 downto 0);
	signal FrameAddressRegister : std_logic_vector(FrameBitsPerRow-1 downto 0);
	signal LongFrameStrobe: std_logic;
	signal LocalWriteData : std_logic_vector(FrameBitsPerRow-1 downto 0);
	signal LocalWriteStrobe : std_logic;
	signal RowSelect : std_logic_vector(RowSelectWidth-1 downto 0);
    signal RAM2FAB_D_Readable : std_logic_vector ( NumberOfRows * 4 * 4 - 1 downto 0);

begin
    RAM2FAB_D_Readable <= RAM2FAB_D;
	inst_Config: Config 
		port map (
			CLK => CLK,
			Rx => Rx,
			ComActive => ComActive,
			ReceiveLED => ReceiveLED,
			s_clk => s_clk,
			s_data => s_data,
			SelfWriteData => SelfWriteData,
			SelfWriteStrobe => SelfWriteStrobe,
			
			ConfigWriteData => LocalWriteData,
			ConfigWriteStrobe => LocalWriteStrobe,
			
			FrameAddressRegister => FrameAddressRegister,
			LongFrameStrobe => LongFrameStrobe,
			RowSelect => RowSelect
		);



