library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity eFPGA_Config is
  generic (
    NumberOfRows    : integer := 16;
    RowSelectWidth  : integer := 5;
    FrameBitsPerRow : integer := 32;
    desync_flag     : integer := 20
  );
  port (
    CLK    : in    std_logic;
    resetn : in    std_logic;
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

architecture from_verilog of eFPGA_Config is

  component config_UART is
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
      data    : out   std_logic_vector(31 downto 0);
      active  : out   std_logic;
      clk     : in    std_logic;
      reset_n : in    std_logic
    );
  end component bitbang;

  component ConfigFSM is
    generic (
      NumberOfRows    : integer;
      RowSelectWidth  : integer;
      FrameBitsPerRow : integer;
      desync_flag     : integer
    );
    port (
      CLK                    : in    std_logic;
      reset_n                : in    std_logic;
      write_data             : in    std_logic_vector(31 downto 0);
      write_strobe           : in    std_logic;
      fsm_reset              : in    std_logic;
      frame_address_register : out   std_logic_vector(FrameBitsPerRow - 1 downto 0);
      long_frame_strobe      : out   std_logic;
      row_select             : out   std_logic_vector(RowSelectWidth - 1 downto 0)
    );
  end component ConfigFSM;

  signal Command                : unsigned(7 downto 0);
  signal UART_WriteData         : unsigned(31 downto 0);
  signal UART_WriteStrobe       : std_logic;
  signal UART_WriteData_Mux     : std_logic_vector(31 downto 0);
  signal UART_WriteStrobe_Mux   : std_logic;
  signal UART_ComActive         : std_logic;
  signal UART_LED               : std_logic;
  signal BitBangWriteData       : std_logic_vector(31 downto 0);
  signal BitBangWriteStrobe     : std_logic;
  signal BitBangWriteData_Mux   : std_logic_vector(31 downto 0);
  signal BitBangWriteStrobe_Mux : std_logic;
  signal BitBangActive          : std_logic;
  signal fsm_reset              : std_logic;

begin

  inst_config_uart : component config_UART
    port map (
      CLK         => CLK,
      reset_n     => resetn,
      Rx          => Rx,
      WriteData   => UART_WriteData,
      ComActive   => UART_ComActive,
      WriteStrobe => UART_WriteStrobe,
      Command     => Command,
      ReceiveLED  => UART_LED
    );

  inst_bit_bang : component bitbang
    port map (
      s_clk   => s_clk,
      s_data  => s_data,
      strobe  => BitBangWriteStrobe,
      data    => BitBangWriteData,
      active  => BitBangActive,
      clk     => CLK,
      reset_n => resetn
    );

  -- Configuration port priority (highest to lowest): UART > BitBang > Parallel

  BitBangWriteData_Mux   <= BitBangWriteData when BitBangActive = '1' else
                            SelfWriteData;
  BitBangWriteStrobe_Mux <= BitBangWriteStrobe when BitBangActive = '1' else
                            SelfWriteStrobe;

  UART_WriteData_Mux   <= std_logic_vector(UART_WriteData) when UART_ComActive = '1' else
                          BitBangWriteData_Mux;
  UART_WriteStrobe_Mux <= UART_WriteStrobe when UART_ComActive = '1' else
                          BitBangWriteStrobe_Mux;

  ConfigWriteData   <= UART_WriteData_Mux;
  ConfigWriteStrobe <= UART_WriteStrobe_Mux;

  fsm_reset <= UART_ComActive or BitBangActive;

  ComActive  <= UART_ComActive;
  ReceiveLED <= UART_LED xor BitBangWriteStrobe;

  configfsm_inst : component ConfigFSM
    generic map (
      NumberOfRows    => NumberOfRows,
      RowSelectWidth  => RowSelectWidth,
      FrameBitsPerRow => FrameBitsPerRow,
      desync_flag     => desync_flag
    )
    port map (
      CLK                    => CLK,
      reset_n                => resetn,
      write_data             => UART_WriteData_Mux,
      write_strobe           => UART_WriteStrobe_Mux,
      fsm_reset              => fsm_reset,
      frame_address_register => FrameAddressRegister,
      long_frame_strobe      => LongFrameStrobe,
      row_select             => RowSelect
    );

end architecture from_verilog;
