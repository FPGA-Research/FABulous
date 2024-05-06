-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity eFPGA_Config is
  generic (
    RowSelectWidth : integer := 5;
    FrameBitsPerRow : integer := 32;
    NumberOfRows : integer := 16;
    desync_flag : integer := 20
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
end entity; 

-- Generated from Verilog module Config (Config_template.v:1)
--   FrameBitsPerRow = 32
--   RowSelectWidth = 5
architecture from_verilog of eFPGA_Config is
  signal BitBangActive : std_logic := '0'; 
  signal BitBangWriteData : std_logic_vector(31 downto 0); 
  signal BitBangWriteData_Mux : std_logic_vector(31 downto 0);  
  signal BitBangWriteStrobe : std_logic := '0';  
  signal BitBangWriteStrobe_Mux : std_logic := '0';  
  signal Command : unsigned(7 downto 0);  
  signal Reset : std_logic := '0';  
  signal UART_ComActive : std_logic := '0';  
  signal UART_LED : std_logic := '0';  
  signal UART_WriteData : unsigned(31 downto 0);  
  signal UART_WriteData_Mux : std_logic_vector(31 downto 0); 
  signal UART_WriteStrobe : std_logic := '0';  
  signal UART_WriteStrobe_Mux : std_logic := '0'; 
  
  component ConfigFSM is
    generic (
      FrameBitsPerRow : integer := FrameBitsPerRow;
      NumberOfRows : integer := NumberOfRows;
      RowSelectWidth : integer := RowSelectWidth;
      desync_flag : integer := desync_flag
    );
    port (
      CLK : in std_logic;
      FrameAddressRegister : out std_logic_vector(31 downto 0);
      LongFrameStrobe : out std_logic;
      Reset : in std_logic;
      RowSelect : out std_logic_vector(4 downto 0);
      WriteData : in std_logic_vector(31 downto 0);
      WriteStrobe : in std_logic
    );
 end component;
  signal FrameAddressRegister_Readable : std_logic_vector(31 downto 0);  -- Needed to connect outputs
  signal LongFrameStrobe_Readable : std_logic;  -- Needed to connect outputs
  signal RowSelect_Readable : std_logic_vector(4 downto 0);  -- Needed to connect outputs
  
  component config_UART is
    port (
      CLK : in std_logic;
      ComActive : out std_logic;
      Command : out unsigned(7 downto 0);
      ReceiveLED : out std_logic;
      Rx : in std_logic;
      WriteData : out unsigned(31 downto 0);
      WriteStrobe : out std_logic
    );
  end component;
  
  component bitbang is
    port (
      active : out std_logic;
      clk : in std_logic;
      data : out std_logic_vector(31 downto 0);
      s_clk : in std_logic;
      s_data : in std_logic;
      strobe : out std_logic
    );
  end component;
begin
  ConfigWriteData <= UART_WriteData_Mux;
  ConfigWriteStrobe <= UART_WriteStrobe_Mux;
  Reset <= UART_ComActive or BitBangActive;
  ComActive <= UART_ComActive;
  ReceiveLED <= UART_LED xor BitBangWriteStrobe;
  BitBangWriteData_Mux <= std_logic_vector(BitBangWriteData) when BitBangActive = '1' else SelfWriteData;
  BitBangWriteStrobe_Mux <= BitBangWriteStrobe when BitBangActive = '1' else SelfWriteStrobe;
  UART_WriteData_Mux <= std_logic_vector(UART_WriteData) when UART_ComActive = '1' else BitBangWriteData_Mux;
  UART_WriteStrobe_Mux <= UART_WriteStrobe when UART_ComActive = '1' else BitBangWriteStrobe_Mux;
  FrameAddressRegister <= FrameAddressRegister_Readable;
  LongFrameStrobe <= LongFrameStrobe_Readable;
  RowSelect <= RowSelect_Readable;
  
  -- Generated from instantiation at Config_template.v:81
  ConfigFSM_inst: ConfigFSM
    port map (
      CLK => CLK,
      FrameAddressRegister => FrameAddressRegister_Readable,
      LongFrameStrobe => LongFrameStrobe_Readable,
      Reset => Reset,
      RowSelect => RowSelect_Readable,
      WriteData => UART_WriteData_Mux,
      WriteStrobe => UART_WriteStrobe_Mux
    );
  
  -- Generated from instantiation at Config_template.v:41
  INST_config_UART: config_UART
    port map (
      CLK => CLK,
      ComActive => UART_ComActive,
      Command => Command,
      ReceiveLED => UART_LED,
      Rx => Rx,
      WriteData => UART_WriteData,
      WriteStrobe => UART_WriteStrobe
    );
  
  -- Generated from instantiation at Config_template.v:52
  Inst_bitbang: bitbang
    port map (
      active => BitBangActive,
      clk => CLK,
      data => BitBangWriteData,
      s_clk => s_clk,
      s_data => s_data,
      strobe => BitBangWriteStrobe
    );
end architecture;