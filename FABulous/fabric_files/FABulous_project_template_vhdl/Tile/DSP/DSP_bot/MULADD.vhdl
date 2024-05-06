library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

-- (* FABulous, BelMap, A_reg=0, B_reg=1, C_reg=2, ACC=3, signExtension=4, ACCout=5 *)

entity MULADD is
    Generic ( NoConfigBits : integer := 6 );	-- has to be adjusted manually (we don't use an arithmetic parser for the value)
    Port (      -- IMPORTANT: this has to be in a dedicated line
		A7 	: in	std_logic;					-- operand A
		A6 	: in	std_logic;					
		A5 	: in	std_logic;					
		A4 	: in	std_logic;					
		A3 	: in	std_logic;					
		A2 	: in	std_logic;					
		A1 	: in	std_logic;					
		A0 	: in	std_logic;					
 	
		B7 	: in	std_logic;					-- operand B
		B6 	: in	std_logic;					
		B5 	: in	std_logic;					
		B4 	: in	std_logic;					
		B3 	: in	std_logic;					
		B2 	: in	std_logic;					
		B1 	: in	std_logic;					
		B0 	: in	std_logic;					
  
		C19	: in	std_logic;					-- operand C
		C18	: in	std_logic;					
		C17	: in	std_logic;					
		C16	: in	std_logic;					
		C15	: in	std_logic;					
		C14	: in	std_logic;					
		C13	: in	std_logic;					
		C12	: in	std_logic;					
		C11	: in	std_logic;					
		C10	: in	std_logic;					
		C9 	: in	std_logic;					
		C8 	: in	std_logic;					
		C7 	: in	std_logic;					
		C6 	: in	std_logic;					
		C5 	: in	std_logic;					
		C4 	: in	std_logic;					
		C3 	: in	std_logic;					
		C2 	: in	std_logic;					
		C1 	: in	std_logic;					
		C0 	: in	std_logic;					
		
		Q19	: out	std_logic;					-- result
		Q18	: out	std_logic;					
		Q17	: out	std_logic;					
		Q16	: out	std_logic;					
		Q15	: out	std_logic;					
		Q14	: out	std_logic;					
		Q13	: out	std_logic;					
		Q12	: out	std_logic;					
		Q11	: out	std_logic;					
		Q10	: out	std_logic;					
		Q9 	: out	std_logic;					
		Q8 	: out	std_logic;					
		Q7 	: out	std_logic;					
		Q6 	: out	std_logic;					
		Q5 	: out	std_logic;					
		Q4 	: out	std_logic;					
		Q3 	: out	std_logic;					
		Q2 	: out	std_logic;					
		Q1 	: out	std_logic;					
		Q0 	: out	std_logic;					
		
		clr : in	std_logic;	
		
	UserCLK : in	STD_LOGIC; -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this sisgnal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	-- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	ConfigBits : in 	 STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
	);
end entity MULADD;

architecture Behavioral of MULADD is

signal A : std_logic_vector(7 downto 0);		-- port A read data 
signal B : std_logic_vector(7 downto 0);		-- port B read data 
signal C : std_logic_vector(19 downto 0);		-- port B read data 

signal A_reg : std_logic_vector(7 downto 0);		-- port A read data register
signal B_reg : std_logic_vector(7 downto 0);		-- port B read data register
signal C_reg : std_logic_vector(19 downto 0);		-- port B read data register

signal OPA : std_logic_vector(7 downto 0);		-- port A 
signal OPB : std_logic_vector(7 downto 0);		-- port B 
signal OPC : std_logic_vector(19 downto 0);		-- port B  

signal ACC  : std_logic_vector(19 downto 0);		-- accumulator register
signal sum  : unsigned(19 downto 0);		-- port B read data register
signal sum_in  : std_logic_vector(19 downto 0);		-- port B read data register

signal product  : unsigned(15 downto 0);	
signal product_extended  : unsigned(19 downto 0);	


begin

A <= A7 & A6 & A5 & A4 & A3 & A2 & A1 & A0;
B <= B7 & B6 & B5 & B4 & B3 & B2 & B1 & B0;
C <= C19 & C18 & C17 & C16 & C15 & C14 & C13 & C12 & C11 & C10 & C9 & C8 & C7 & C6 & C5 & C4 & C3 & C2 & C1 & C0;

OPA <= A when (ConfigBits(0) = '0') else A_reg;
OPB <= B when (ConfigBits(1) = '0') else B_reg;
OPC <= C when (ConfigBits(2) = '0') else C_reg;

sum_in <= OPC when (ConfigBits(3) = '0') else ACC;		-- we can

product <= unsigned(OPA) * unsigned(OPB);

-- The sign extension was not tested
product_extended <= "0000" & product when (ConfigBits(4) = '0') else product(product'high) & product(product'high) & product(product'high) & product(product'high) & product;

sum <= product_extended + unsigned(sum_in);

Q19	<= sum( 19 ) when (ConfigBits(5) = '0') else ACC( 19 );
Q18	<= sum( 18 ) when (ConfigBits(5) = '0') else ACC( 18 );
Q17	<= sum( 17 ) when (ConfigBits(5) = '0') else ACC( 17 );
Q16	<= sum( 16 ) when (ConfigBits(5) = '0') else ACC( 16 );
Q15	<= sum( 15 ) when (ConfigBits(5) = '0') else ACC( 15 );
Q14	<= sum( 14 ) when (ConfigBits(5) = '0') else ACC( 14 );
Q13	<= sum( 13 ) when (ConfigBits(5) = '0') else ACC( 13 );
Q12	<= sum( 12 ) when (ConfigBits(5) = '0') else ACC( 12 );
Q11	<= sum( 11 ) when (ConfigBits(5) = '0') else ACC( 11 );
Q10	<= sum( 10 ) when (ConfigBits(5) = '0') else ACC( 10 );
Q9 	<= sum( 9  ) when (ConfigBits(5) = '0') else ACC( 9  );
Q8 	<= sum( 8  ) when (ConfigBits(5) = '0') else ACC( 8  );
Q7 	<= sum( 7  ) when (ConfigBits(5) = '0') else ACC( 7  );
Q6 	<= sum( 6  ) when (ConfigBits(5) = '0') else ACC( 6  );
Q5 	<= sum( 5  ) when (ConfigBits(5) = '0') else ACC( 5  );
Q4 	<= sum( 4  ) when (ConfigBits(5) = '0') else ACC( 4  );
Q3 	<= sum( 3  ) when (ConfigBits(5) = '0') else ACC( 3  );
Q2 	<= sum( 2  ) when (ConfigBits(5) = '0') else ACC( 2  );
Q1 	<= sum( 1  ) when (ConfigBits(5) = '0') else ACC( 1  );
Q0 	<= sum( 0  ) when (ConfigBits(5) = '0') else ACC( 0  );

process(UserCLK)
begin
	if UserCLK'event and UserCLK='1' then
		A_reg <= A;
		B_reg <= B;
		C_reg <= C;
		if clr = '1' then
			ACC <= (others => '0');
		else
			ACC <= std_logic_vector(sum);
		end if;
	end if;
end process;

end architecture Behavioral;
