
-- Models for the embedded FPGA fabric

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

-- LHD1 Latch area 11.76
entity  LHD1  is 
	Port (
    D    : in      STD_LOGIC;     -- global signal 1: configuration, 0: operation
    E    : in      STD_LOGIC;
    Q    : out     STD_LOGIC;
    QN   : out     STD_LOGIC ); 
end entity LHD1 ;

architecture Behavioral of  LHD1  is

signal M_set_gate, M_reset_gate : std_logic := '0';
signal S_set_gate, S_reset_gate : std_logic := '0';
signal M_q, M_qn : std_logic := '0';
signal S_q, S_qn : std_logic := '0';

begin
-- master
M_set_gate   <= D NAND E after 10 ns;
M_reset_gate <= (NOT D) NAND E after 10 ns;
M_q    <= M_qn NAND M_set_gate after 10 ns;
M_qn   <= M_q  NAND M_reset_gate after 10 ns;

Q <= M_q;
QN <= M_qn;

end Behavioral; 

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

-- LHQD1 Latch area 10.67
entity  LHQD1  is 
	Port (
    D    : in      STD_LOGIC;     -- global signal 1: configuration, 0: operation
    E    : in      STD_LOGIC;
    Q    : out     STD_LOGIC ); 
end entity LHQD1 ;

architecture Behavioral of  LHQD1  is

signal M_set_gate   : std_logic := '0';
signal M_reset_gate : std_logic := '1';

signal M_q       : std_logic := '0';
signal M_qn      : std_logic := '1';

begin
-- master
M_set_gate   <= D NAND E after 10 ns;
M_reset_gate <= (NOT D) NAND E after 10 ns;
M_q    <= M_qn NAND M_set_gate after 10 ns;
M_qn   <= M_q  NAND M_reset_gate after 10 ns;

Q <= M_q;

end Behavioral; 

-- (MUX4PTv4) and 1.2ns (MUX16PTv2) in worse case when all select bits=0, so I think they work fine with f=50MHz. 
-- The area are HxW = 7um x 9.86um (MUX4) and 7um x 44.72um (MUX16). 
-- Please note, the pins are named as IN1, IN2, ..., IN16 for inputs, S1, .., S4 for selects and OUT for output.

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

-- LHQD1 Latch area 10.67
entity  MUX4PTv4  is 
	Port (
    IN1  : in      STD_LOGIC;     
    IN2  : in      STD_LOGIC;     
    IN3  : in      STD_LOGIC;     
    IN4  : in      STD_LOGIC;     
    S1   : in      STD_LOGIC;
    S2   : in      STD_LOGIC;
    O    : out     STD_LOGIC ); 
end entity MUX4PTv4 ;

architecture Behavioral of  MUX4PTv4  is

signal SEL : std_logic_vector(1 downto 0);

begin

sel <= S2 & S1; 
with SEL select
    O   <= IN1 when "00",
           IN2 when "01",
           IN3 when "10",
           IN4 when "11",
		   '0' when others;

end Behavioral; 

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

-- LHQD1 Latch area 10.67
entity  MUX16PTv2  is 
	Port (
    IN1  : in      STD_LOGIC;     
    IN2  : in      STD_LOGIC;     
    IN3  : in      STD_LOGIC;     
    IN4  : in      STD_LOGIC;     
    IN5  : in      STD_LOGIC;     
    IN6  : in      STD_LOGIC;     
    IN7  : in      STD_LOGIC;     
    IN8  : in      STD_LOGIC;     
    IN9  : in      STD_LOGIC;     
    IN10 : in      STD_LOGIC;     
    IN11 : in      STD_LOGIC;     
    IN12 : in      STD_LOGIC;     
    IN13 : in      STD_LOGIC;     
    IN14 : in      STD_LOGIC;     
    IN15 : in      STD_LOGIC;     
    IN16 : in      STD_LOGIC;     
    S1   : in      STD_LOGIC;
    S2   : in      STD_LOGIC;
    S3   : in      STD_LOGIC;
    S4   : in      STD_LOGIC;
    O    : out     STD_LOGIC ); 
end entity MUX16PTv2 ;

architecture Behavioral of  MUX16PTv2  is

signal SEL : std_logic_vector(3 downto 0);

begin

sel <= S4 & S3 & S2 & S1; 
with SEL select
    O   <= IN1  when "0000",
           IN2  when "0001",
           IN3  when "0010",
           IN4  when "0011",
		   IN5  when "0100",
		   IN6  when "0101",
		   IN7  when "0110",
		   IN8  when "0111",
		   IN9  when "1000",
		   IN10 when "1001",
		   IN11 when "1010",
		   IN12 when "1011",
		   IN13 when "1100",
		   IN14 when "1101",
		   IN15 when "1110",
		   IN16 when "1111",
		   '0' when others;

end Behavioral; 

library ieee;
use ieee.std_logic_1164.all;

package my_package is

component  LHD1  is 
	Port (
    D    : in      STD_LOGIC;  
    E    : in      STD_LOGIC;
    Q    : out     STD_LOGIC;
    QN   : out     STD_LOGIC ); 
end component LHD1 ;

component  LHQD1  is 
	Port (
    D    : in      STD_LOGIC;    
    E    : in      STD_LOGIC;
    Q    : out     STD_LOGIC ); 
end component LHQD1 ;

component  MUX4PTv4  is 
	Port (
    IN1  : in      STD_LOGIC;     
    IN2  : in      STD_LOGIC;     
    IN3  : in      STD_LOGIC;     
    IN4  : in      STD_LOGIC;     
    S1   : in      STD_LOGIC;
    S2   : in      STD_LOGIC;
    O    : out     STD_LOGIC ); 
end component MUX4PTv4 ;

component  MUX16PTv2  is 
	Port (
    IN1  : in      STD_LOGIC;     
    IN2  : in      STD_LOGIC;     
    IN3  : in      STD_LOGIC;     
    IN4  : in      STD_LOGIC;     
    IN5  : in      STD_LOGIC;     
    IN6  : in      STD_LOGIC;     
    IN7  : in      STD_LOGIC;     
    IN8  : in      STD_LOGIC;     
    IN9  : in      STD_LOGIC;     
    IN10 : in      STD_LOGIC;     
    IN11 : in      STD_LOGIC;     
    IN12 : in      STD_LOGIC;     
    IN13 : in      STD_LOGIC;     
    IN14 : in      STD_LOGIC;     
    IN15 : in      STD_LOGIC;     
    IN16 : in      STD_LOGIC;     
    S1   : in      STD_LOGIC;
    S2   : in      STD_LOGIC;
    S3   : in      STD_LOGIC;
    S4   : in      STD_LOGIC;
    O    : out     STD_LOGIC ); 
end component MUX16PTv2 ;

end package my_package;



















