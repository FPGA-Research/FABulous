library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use work.my_package.all;

-- (* FABulous, BelMap, C_bit0=0, C_bit1=1, C_bit2=2, C_bit3=3 *)
entity Config_access is
    Generic ( NoConfigBits : integer := 4 );	-- has to be adjusted manually (we don't use an arithmetic parser for the value)
    Port ( 
	-- Pin0
	C_bit0	: out	STD_LOGIC; -- EXTERNAL
	C_bit1	: out	STD_LOGIC; -- EXTERNAL
	C_bit2	: out	STD_LOGIC; -- EXTERNAL
	C_bit3	: out	STD_LOGIC; -- EXTERNAL
	-- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	ConfigBits : in 	 STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
	);
end entity Config_access;

architecture Behavioral of Config_access is

begin

-- we just wire configuration bits to fabric top
C_bit0 <= ConfigBits(0) ;
C_bit1 <= ConfigBits(1) ;
C_bit2 <= ConfigBits(2) ;
C_bit3 <= ConfigBits(3) ;

end architecture Behavioral;
