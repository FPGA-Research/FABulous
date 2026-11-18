-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module eFPGA_Config (eFPGA_Config.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20

entity eFPGA_Config is
  generic (
    NumberOfRows    : integer               := 16;
    RowSelectWidth  : integer               := 5;
    FrameBitsPerRow : integer               := 32;
    desync_flag     : integer range 0 to 31 := 20
  );
  port (
    CLK     : in    std_logic;
    reset_n : in    std_logic;
    -- UART configuration port
    Rx         : in    std_logic;
    ComActive  : out   std_logic;
    ReceiveLED : out   std_logic;
    -- BitBang configuration port
    s_clk  : in    std_logic;
    s_data : in    std_logic;
    -- Parallel configuration port
    SelfWriteData        : in    std_logic_vector(31 downto 0);
    SelfWriteStrobe      : in    std_logic;
    ConfigWriteData      : out   std_logic_vector(31 downto 0);
    ConfigWriteStrobe    : out   std_logic;
    FrameAddressRegister : out   std_logic_vector(FrameBitsPerRow - 1 downto 0);
    LongFrameStrobe      : out   std_logic;
    RowSelect            : out   std_logic_vector(RowSelectWidth - 1 downto 0)
  );
end entity eFPGA_Config;

-- Generated from Verilog module eFPGA_Config (eFPGA_Config.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20

architecture from_verilog of eFPGA_Config is

  signal Command : unsigned(7 downto 0);

  signal UART_WriteData       : unsigned(31 downto 0);
  signal UART_WriteStrobe     : std_logic;
  signal UART_WriteData_Mux   : unsigned(31 downto 0);
  signal UART_WriteStrobe_Mux : std_logic;
  signal UART_ComActive       : std_logic;
  signal UART_LED             : std_logic;

  signal BitBangWriteData       : unsigned(31 downto 0);
  signal BitBangWriteStrobe     : std_logic;
  signal BitBangWriteData_Mux   : unsigned(31 downto 0);
  signal BitBangWriteStrobe_Mux : std_logic;
  signal BitBangActive          : std_logic;

  signal fsm_reset : std_logic;

  signal fsm_frame_address : unsigned(FrameBitsPerRow - 1 downto 0);
  signal fsm_row_select    : unsigned(RowSelectWidth - 1 downto 0);

  component ConfigFSM is
    generic (
      NumberOfRows    : integer;
      RowSelectWidth  : integer;
      FrameBitsPerRow : integer;
      desync_flag     : integer range 0 to 31
    );
    port (
      CLK                    : in    std_logic;
      reset_n                : in    std_logic;
      write_data             : in    unsigned(31 downto 0);
      write_strobe           : in    std_logic;
      fsm_reset              : in    std_logic;
      frame_address_register : out   unsigned(FrameBitsPerRow - 1 downto 0);
      long_frame_strobe      : out   std_logic;
      row_select             : out   unsigned(RowSelectWidth - 1 downto 0)
    );
  end component ConfigFSM;

  component config_UART is
    generic (
      Mode    : integer range 0 to 2    := 0;
      ComRate : integer range 1 to 4095 := 217
    );
    port (
      CLK         : in    std_logic;
      reset_n     : in    std_logic;
      Rx          : in    std_logic;
      WriteData   : out   unsigned(31 downto 0);
      ComActive   : out   std_logic;
      WriteStrobe : out   std_logic;
      Command     : out   unsigned(7 downto 0);
      ReceiveLED  : out   std_logic
    );
  end component config_UART;

  component bitbang is
    port (
      s_clk   : in    std_logic;
      s_data  : in    std_logic;
      strobe  : out   std_logic;
      data    : out   unsigned(31 downto 0);
      active  : out   std_logic;
      clk     : in    std_logic;
      reset_n : in    std_logic
    );
  end component bitbang;

begin

  -- Configuration port priority (highest to lowest): UART > BitBang > Parallel

  BitBangWriteData_Mux   <= BitBangWriteData when BitBangActive = '1' else
                            unsigned(SelfWriteData);
  BitBangWriteStrobe_Mux <= BitBangWriteStrobe when BitBangActive = '1' else
                            SelfWriteStrobe;

  UART_WriteData_Mux   <= UART_WriteData when UART_ComActive = '1' else
                          BitBangWriteData_Mux;
  UART_WriteStrobe_Mux <= UART_WriteStrobe when UART_ComActive = '1' else
                          BitBangWriteStrobe_Mux;

  ConfigWriteData   <= std_logic_vector(UART_WriteData_Mux);
  ConfigWriteStrobe <= UART_WriteStrobe_Mux;

  fsm_reset <= UART_ComActive or BitBangActive;

  ComActive  <= UART_ComActive;
  ReceiveLED <= UART_LED xor BitBangWriteStrobe;

  FrameAddressRegister <= std_logic_vector(fsm_frame_address);
  RowSelect            <= std_logic_vector(fsm_row_select);

  inst_configfsm : component ConfigFSM
    generic map (
      NumberOfRows    => NumberOfRows,
      RowSelectWidth  => RowSelectWidth,
      FrameBitsPerRow => FrameBitsPerRow,
      desync_flag     => desync_flag
    )
    port map (
      CLK                    => CLK,
      reset_n                => reset_n,
      write_data             => UART_WriteData_Mux,
      write_strobe           => UART_WriteStrobe_Mux,
      fsm_reset              => fsm_reset,
      frame_address_register => fsm_frame_address,
      long_frame_strobe      => LongFrameStrobe,
      row_select             => fsm_row_select
    );

  inst_config_uart : component config_UART
    port map (
      CLK         => CLK,
      reset_n     => reset_n,
      Rx          => Rx,
      WriteData   => UART_WriteData,
      ComActive   => UART_ComActive,
      WriteStrobe => UART_WriteStrobe,
      Command     => Command,
      ReceiveLED  => UART_LED
    );

  inst_bitbang : component bitbang
    port map (
      s_clk   => s_clk,
      s_data  => s_data,
      strobe  => BitBangWriteStrobe,
      data    => BitBangWriteData,
      active  => BitBangActive,
      clk     => CLK,
      reset_n => reset_n
    );

end architecture from_verilog;
