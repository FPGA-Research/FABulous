library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;
use work.my_package.all;

-- InPassFlop2 and OutPassFlop2 are the same except for changing which side I0,I1 or O0,O1 gets connected to the top entity

-- (* FABulous, BelMap I0_reg=0, I1_reg=1, I2_reg=2, I3_reg=3 *)
entity OutPass4_frame_config is
    Generic ( NoConfigBits : integer := 4 );	-- has to be adjusted manually (we don't use an arithmetic parser for the value)
    Port ( 
	-- Pin0
	I0	: in	STD_LOGIC; 
	I1	: in	STD_LOGIC; 
	I2	: in	STD_LOGIC; 
	I3	: in	STD_LOGIC; 
	O0	: out	STD_LOGIC; -- EXTERNAL
	O1	: out	STD_LOGIC; -- EXTERNAL
	O2	: out	STD_LOGIC; -- EXTERNAL
	O3	: out	STD_LOGIC; -- EXTERNAL
	-- Tile IO ports from BELs
 	UserCLK : in	STD_LOGIC; -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this signal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	-- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	ConfigBits : in 	 STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
	);
end entity OutPass4_frame_config;

architecture Behavioral of OutPass4_frame_config is

--              ______   ______
--    I----+--->|FLOP|-Q-|1 M |
--         |             |  U |-------> O
--         +-------------|0 X |               


-- I am instantiating an IOBUF primitive.
-- However, it is possible to connect corresponding pins all the way to top, just by adding an "-- EXTERNAL" comment (see PAD in the entity)

signal Q0, Q1, Q2, Q3 : std_logic;   -- FLOPs

begin

process(UserCLK)
begin
	if UserCLK'event and UserCLK='1' then
		Q0 <= I0;
		Q1 <= I1;
		Q2 <= I2;
		Q3 <= I3;
	end if;
end process;

O0 <= I0 when (ConfigBits(0) = '0') else Q0;
O1 <= I1 when (ConfigBits(1) = '0') else Q1;
O2 <= I2 when (ConfigBits(2) = '0') else Q2;
O3 <= I3 when (ConfigBits(3) = '0') else Q3;

end architecture Behavioral;
