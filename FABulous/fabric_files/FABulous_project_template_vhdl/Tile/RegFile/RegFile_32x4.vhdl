library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;
use work.my_package.all;

-- (* FABulous, BelMap, AD_reg=0, BD_reg=1 *)

entity RegFile_32x4 is
    Generic ( NoConfigBits : integer := 2 );	-- has to be adjusted manually (we don't use an arithmetic parser for the value)
    Port (      -- IMPORTANT: this has to be in a dedicated line
	D0	: in	STD_LOGIC; -- Register File write port
	D1	: in	STD_LOGIC;
	D2	: in	STD_LOGIC;
	D3	: in	STD_LOGIC;
	W_ADR0 : in	STD_LOGIC; 
	W_ADR1 : in	STD_LOGIC; 
	W_ADR2 : in	STD_LOGIC; 
	W_ADR3 : in	STD_LOGIC; 
	W_ADR4 : in	STD_LOGIC; 
	W_en : in	STD_LOGIC;
	
	AD0	: out	STD_LOGIC; -- Register File read port A
	AD1	: out	STD_LOGIC; 
	AD2	: out	STD_LOGIC; 
	AD3	: out	STD_LOGIC; 
	A_ADR0 : in	STD_LOGIC; 
	A_ADR1 : in	STD_LOGIC; 
	A_ADR2 : in	STD_LOGIC; 
	A_ADR3 : in	STD_LOGIC; 
	A_ADR4 : in	STD_LOGIC; 

	BD0	: out	STD_LOGIC; -- Register File read port B
	BD1	: out	STD_LOGIC; 
	BD2	: out	STD_LOGIC; 
	BD3	: out	STD_LOGIC; 
	B_ADR0 : in	STD_LOGIC; 
	B_ADR1 : in	STD_LOGIC; 
	B_ADR2 : in	STD_LOGIC; 
	B_ADR3 : in	STD_LOGIC; 
	B_ADR4 : in	STD_LOGIC; 

	UserCLK : in	STD_LOGIC; -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this sisgnal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	-- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	ConfigBits : in 	 STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
	);
end entity RegFile_32x4;

architecture Behavioral of RegFile_32x4 is

type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); -- 32 entries of 4 bit
signal mem : memtype := (others => (others => '0'));      

signal W_ADR : std_logic_vector(4 downto 0);	-- write address
signal A_ADR : std_logic_vector(4 downto 0);	-- port A read address
signal B_ADR : std_logic_vector(4 downto 0);	-- port B read address

signal D : std_logic_vector(3 downto 0);		-- write data
signal AD : std_logic_vector(3 downto 0);		-- port A read data
signal BD : std_logic_vector(3 downto 0);		-- port B read data

signal AD_reg : std_logic_vector(3 downto 0);		-- port A read data register
signal BD_reg : std_logic_vector(3 downto 0);		-- port B read data register


begin

W_ADR <= W_ADR4 & W_ADR3 & W_ADR2 & W_ADR1 & W_ADR0;
A_ADR <= A_ADR4 & A_ADR3 & A_ADR2 & A_ADR1 & A_ADR0;
B_ADR <= B_ADR4 & B_ADR3 & B_ADR2 & B_ADR1 & B_ADR0;

D <= D3 & D2 & D1 & D0;

P_write: process (UserCLK)
begin
	if UserCLK'event and UserCLK = '1' then
		if W_en = '1' then
			mem(TO_INTEGER(UNSIGNED(W_ADR))) <= D ;
		end if;
	end if;
end process;

AD <= mem(TO_INTEGER(UNSIGNED(A_ADR)));
BD <= mem(TO_INTEGER(UNSIGNED(B_ADR)));

process(UserCLK)
begin
	if UserCLK'event and UserCLK='1' then
		AD_reg <= AD;
		BD_reg <= BD;
	end if;
end process;

AD0 <= AD (0) when (ConfigBits(0) = '0') else AD_reg(0);
AD1 <= AD (1) when (ConfigBits(0) = '0') else AD_reg(1);
AD2 <= AD (2) when (ConfigBits(0) = '0') else AD_reg(2);
AD3 <= AD (3) when (ConfigBits(0) = '0') else AD_reg(3);

BD0 <= BD (0) when (ConfigBits(1) = '0') else BD_reg(0);
BD1 <= BD (1) when (ConfigBits(1) = '0') else BD_reg(1);
BD2 <= BD (2) when (ConfigBits(1) = '0') else BD_reg(2);
BD3 <= BD (3) when (ConfigBits(1) = '0') else BD_reg(3);

end architecture Behavioral;
