library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

-- Library UNISIM;
-- use UNISIM.vcomponents.all;


entity IO_1_bidirectional_frame_config_pass is
    -- Generic ( NoConfigBits : integer := 0 );	-- has to be adjusted manually (we don't use an arithmetic parser for the value)
    Port ( 
	-- Pin0
	I	: in	STD_LOGIC; -- from fabric to external pin
	T	: in	STD_LOGIC; -- tristate control
	O	: out	STD_LOGIC; -- from external pin to fabric
	Q	: out	STD_LOGIC; -- from external pin to fabric (registered)
	I_top : out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
	T_top : out STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
	O_top : in STD_LOGIC; -- EXTERNAL has to ge to top-level entity not the switch matrix
	-- Tile IO ports from BELs
 	UserCLK : in	STD_LOGIC -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this signal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	-- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	-- ConfigBits : in 	 STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
	);
end entity IO_1_bidirectional_frame_config_pass;

architecture Behavioral of IO_1_bidirectional_frame_config_pass is

--                        _____
--    I-----T_DRIVER----->|PAD|--+-------> O
--              |         -----  |
--    T---------+                +-->FF--> Q

-- I am instantiating an IOBUF primitive.
-- However, it is possible to connect corresponding pins all the way to top, just by adding an "-- EXTERNAL" comment (see PAD in the entity)

-- signal fromPad : std_logic;

begin

-- Slice outputs
O <= O_top;

process(UserCLK)
begin
	if UserCLK'event and UserCLK='1' then
		Q <= O_top;
	end if;
end process;

I_top <= I;
T_top <= NOT T;

-- IOBUF_inst0 : IOBUF
-- port map (
-- O => fromPad, -- 1-bit output: Buffer output
-- I => I, -- 1-bit input: Buffer input
-- IO => PAD, -- 1-bit inout: Buffer inout (connect directly to top-level port)
-- T => T -- 1-bit input: 3-state enable input
-- );

end architecture Behavioral;
