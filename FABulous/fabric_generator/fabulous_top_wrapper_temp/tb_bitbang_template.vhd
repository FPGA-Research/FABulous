library IEEE;
use ieee.std_logic_unsigned.all;
use ieee.std_logic_1164.all;
use ieee.std_logic_arith.all;

entity tb_bitbang is
--	port ();
end entity tb_bitbang; 


architecture Behavioral of tb_bitbang is 

component bitbang is
generic (  trigger_pattern : std_logic_vector(15 downto 0) := x"FAB0");     -- ComRate = f_CLK / Boud_rate (e.g., 25 MHz/115200 Boud = 217)
    Port (  s_clk      : in std_logic;     
            s_data     : in std_logic;
            strobe     : out std_Logic;
            data       : out std_logic_vector(31 downto 0);
            clk        : in std_logic);
end component bitbang; 

component  eFPGA_top  is 
	Port (
	-- External USER ports 
		I_top	:	 out STD_LOGIC_VECTOR (32 -1 downto 0); 
		T_top	:	 out STD_LOGIC_VECTOR (32 -1 downto 0); 
		O_top	:	 in  STD_LOGIC_VECTOR (32 -1 downto 0); 
		--PAD		:	inout	STD_LOGIC_VECTOR (32 -1 downto 0);	-- these are for Dirk and go to the pad ring
		OPA		:	in		STD_LOGIC_VECTOR (64 -1 downto 0);	-- these are for Andrew	and go to the CPU
		OPB		:	in		STD_LOGIC_VECTOR (64 -1 downto 0);	-- these are for Andrew	and go to the CPU
		RES0	:	out		STD_LOGIC_VECTOR (64 -1 downto 0);	-- these are for Andrew	and go to the CPU
		RES1	:	out		STD_LOGIC_VECTOR (64 -1 downto 0);	-- these are for Andrew	and go to the CPU
		RES2	:	out		STD_LOGIC_VECTOR (64 -1 downto 0);	-- these are for Andrew	and go to the CPU
		CLK	    : 	in		STD_LOGIC;							-- This clock can go to the CPU (connects to the fabric LUT output flops
		
	-- CPU configuration port
		SelfWriteStrobe:	in		STD_LOGIC; -- must decode address and write enable
		SelfWriteData:		in		STD_LOGIC_VECTOR (32 -1 downto 0);	-- configuration data write port

	-- BitBang configuration port
	   s_clk   :	in		STD_LOGIC;
       s_data  :	in		STD_LOGIC;
		
		Rx:				in		STD_LOGIC; -- alternative UART -> TODO
      ComActive:      out STD_LOGIC;
      ReceiveLED:     out STD_LOGIC
		);
end component eFPGA_top ;


--constant length : integer :=97;
--constant test_data : std_logic_vector(length downto 0) := x"01234567_89ABCDEFAABBCCDD" & "00";
--constant test_ctrl : std_logic_vector(length downto 0) := x"0000FAB0_0000000000000000" & "00";
constant length : integer :=31;
--constant test_data : std_logic_vector(length downto 0) := x"01234567_89ABCDEFAABBCCDD" & "00";
constant test_ctrl : std_logic_vector(length+1 downto 0) := '0' & x"C000FAB1";

signal tb_data    : std_logic_vector (31 downto 0); 
signal tb_s_clk : std_logic := '0'; 
signal tb_s_data : std_logic := '0'; 
signal tb_strobe : std_logic := '0'; 
signal tb_clk : std_logic := '0'; 

signal tb_s_data_debug : std_logic := '0'; 

signal test_index : integer range 0 to 1000 := length;
signal test_index2 : integer range 0 to 1000 := length+1;
signal test_index_debug : integer range -10 to 1000 := -1;
signal sim_tick: std_logic := '0';

type simType is (control, clk_up, data, clk_down);
signal simState : simType;


signal	tb_I_top	:	 STD_LOGIC_VECTOR (32 -1 downto 0); 
signal	tb_T_top	:	 STD_LOGIC_VECTOR (32 -1 downto 0); 
signal	tb_O_top	:	 STD_LOGIC_VECTOR (32 -1 downto 0) := (others => '0'); 
signal 	tb_OPA	:	STD_LOGIC_VECTOR (64 -1 downto 0) := (others => '0');
signal 	tb_OPB	:	STD_LOGIC_VECTOR (64 -1 downto 0) := (others => '0');
signal 	tb_RES0 :	STD_LOGIC_VECTOR (64 -1 downto 0);
signal 	tb_RES1 :	STD_LOGIC_VECTOR (64 -1 downto 0);
signal 	tb_RES2 :	STD_LOGIC_VECTOR (64 -1 downto 0);

signal  tb_ReceiveLED   : std_logic;
signal  tb_ComActive    : std_logic;
signal tb_Rx					: std_logic :='1';

signal next_byte : std_logic_vector(7 downto 0);


begin

tb_clk <= not tb_clk after 10ns;
sim_tick <= not sim_tick after 77ns;

tb_serial_data: process (sim_tick)
    type characterFile_Typ is file of character;
    file f: characterFile_Typ open read_mode is "D:\VituralMachine\shared_folder\fabric_test\meta_gen\fabric_test_big.bit";
    variable c:character;
    variable i:integer:=0;
--    variable next_byte : std_logic_vector(7 downto 0);
    begin
      if sim_tick'event AND sim_tick='1' then   -- on negative edge for readability
        if ((test_index MOD 8)=7 and simState=clk_down) then --start bit position
           IF (NOT endfile(f)) then
              Read( f    => f,
                    value=> c);  
              next_byte <= CONV_STD_LOGIC_VECTOR(character'pos(c),8);
              tb_rx <= '0';     -- we have something to send
           else
              next_byte <= b"1111_1111";
              tb_rx <= '1';     -- we have nothing to send - so no start bit
           end if;
        end if; -- endfile
     --   i := i+1;
    end if ; --tb_CLK_send
end process;

process(sim_tick)
begin
	if sim_tick'event and sim_tick='1' then
	tb_s_data_debug <= 'U';
	test_index_debug <= -1;
	 case simState is
--		when data =>   	    tb_s_data <= test_data(test_index);
		when data =>   	    tb_s_data <= next_byte((test_index+1) MOD 8);
--		                      tb_s_data_debug <= next_byte((test_index+1) MOD 8);
							simState <= clk_up;
		when clk_up =>  	tb_s_clk <= '1';
							simState <= control;
		when control => 	tb_s_data <= test_ctrl(test_index2);
   			                      tb_s_data_debug <= test_ctrl(test_index2);
                 --     test_index_debug <= ((test_index+1) MOD 8);
   	                      test_index_debug <= ((test_index2));
							simState <= clk_down;
		when clk_down =>  	tb_s_clk <= '0';
		                    if test_index > 0 then
		                      test_index <= test_index -1;
		                    elsif test_index = 0 then
		                      test_index <= length;
		                    end if;
		                    if test_index2 > 0 then
		                      test_index2 <= test_index2 -1;
		                    elsif test_index2 = 0 then
		                      test_index2 <= length;
		                    end if;
							simState <= data;
	 end case;
    end if;
end process;


--dut:bitbang
--generic map (trigger_pattern => x"FAB0")
--port map (  s_clk      => tb_s_clk,
--            s_data     => tb_s_data,
--            strobe     => tb_strobe,
--            data       => tb_data,
--            clk        => tb_clk);




DUT_fabric : eFPGA_top
Port Map(
		--PAD		=> 	tb_PAD	,
		I_top	=> 	tb_I_top	, 
		T_top	=> 	tb_T_top	, 
		O_top	=> 	tb_O_top	,
		OPA		=> 	tb_OPA	,
		OPB		=> 	tb_OPB	,
		RES0	=> 	tb_RES0 ,
		RES1	=> 	tb_RES1 ,
		RES2	=> 	tb_RES2 ,
		CLK	    => 	tb_CLK	,
		
	-- CPU configuration port
		SelfWriteStrobe	=> 	tb_strobe	,
        SelfWriteData	=> 	tb_data	,
		
	-- BitBang configuration port
	   s_clk    => tb_s_clk,
	   s_data   => tb_s_data,
		
		Rx	=> 	tb_Rx	,
		ComActive => 	tb_ComActive	,
		ReceiveLED => 	tb_ReceiveLED
);



end Behavioral;