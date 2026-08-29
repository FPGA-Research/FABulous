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
    RowSelectWidth  : integer := 5;
    FrameBitsPerRow : integer := 32;
    NumberOfRows    : integer := 16;
    desync_flag     : integer := 20;
    bitbang_enable  : integer := 1;
    uart_enable     : integer := 1;
    spi_enable      : integer := 1
  );
  port (
    CLK                  : in    std_logic;
    ComActive            : out   std_logic;
    ConfigWriteData      : out   std_logic_vector(31 downto 0);
    ConfigWriteStrobe    : out   std_logic;
    FrameAddressRegister : out   std_logic_vector(31 downto 0);
    LongFrameStrobe      : out   std_logic;
    ReceiveLED           : out   std_logic;
    RowSelect            : out   std_logic_vector(4 downto 0);
    Rx                   : in    std_logic;
    SelfWriteData        : in    std_logic_vector(31 downto 0);
    SelfWriteStrobe      : in    std_logic;
    resetn               : in    std_logic;
    s_clk                : in    std_logic;
    s_data               : in    std_logic;
    sck                  : in    std_logic;
    mosi                 : in    std_logic;
    ss_n                 : in    std_logic
  );
end entity eFPGA_Config;

-- Generated from Verilog module eFPGA_Config (eFPGA_Config.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20

architecture from_verilog of eFPGA_Config is

  -- UART signals
  signal UART_WriteData   : unsigned(31 downto 0);
  signal UART_WriteStrobe : std_logic;
  signal UART_ComActive   : std_logic;
  signal UART_LED         : std_logic;
  signal Command          : unsigned(7 downto 0);

  -- BitBang signals
  signal BitBangActive      : std_logic;
  signal BitBangWriteData   : std_logic_vector(31 downto 0);
  signal BitBangWriteStrobe : std_logic;

  -- SPI signals (NEW)
  signal spi_active     : std_logic;
  signal spi_write_data : std_logic_vector(31 downto 0);
  signal spi_strobe     : std_logic;

  -- Multiplexed signals
  signal BitBangWriteData_Mux   : std_logic_vector(31 downto 0);
  signal BitBangWriteStrobe_Mux : std_logic;
  signal spi_write_data_mux     : std_logic_vector(31 downto 0);
  signal spi_strobe_mux         : std_logic;
  signal UART_WriteData_Mux     : std_logic_vector(31 downto 0);
  signal UART_WriteStrobe_Mux   : std_logic;

  signal FSM_Reset : std_logic;

  component ConfigFSM is
    generic (
      FrameBitsPerRow : integer := FrameBitsPerRow;
      NumberOfRows    : integer := NumberOfRows;
      RowSelectWidth  : integer := RowSelectWidth;
      desync_flag     : integer := desync_flag
    );
    port (
      CLK                  : in    std_logic;
      FSM_Reset            : in    std_logic;
      FrameAddressRegister : out   std_logic_vector(31 downto 0);
      LongFrameStrobe      : out   std_logic;
      RowSelect            : out   std_logic_vector(4 downto 0);
      WriteData            : in    std_logic_vector(31 downto 0);
      WriteStrobe          : in    std_logic;
      resetn               : in    std_logic
    );
  end component ConfigFSM;

  signal FrameAddressRegister_Readable : std_logic_vector(31 downto 0); -- Needed to connect outputs
  signal LongFrameStrobe_Readable      : std_logic;                     -- Needed to connect outputs
  signal RowSelect_Readable            : std_logic_vector(4 downto 0);  -- Needed to connect outputs

  component config_UART is
    port (
      CLK         : in    std_logic;
      ComActive   : out   std_logic;
      Command     : out   unsigned(7 downto 0);
      ReceiveLED  : out   std_logic;
      Rx          : in    std_logic;
      WriteData   : out   unsigned(31 downto 0);
      WriteStrobe : out   std_logic;
      resetn      : in    std_logic
    );
  end component config_UART;

  component bitbang is
    port (
      active : out   std_logic;
      clk    : in    std_logic;
      data   : out   std_logic_vector(31 downto 0);
      resetn : in    std_logic;
      s_clk  : in    std_logic;
      s_data : in    std_logic;
      strobe : out   std_logic
    );
  end component bitbang;

  component config_SPI is
    port (
      active : out   std_logic;
      clk    : in    std_logic;
      data   : out   std_logic_vector(31 downto 0);
      mosi   : in    std_logic;
      resetn : in    std_logic;
      sck    : in    std_logic;
      ss_n   : in    std_logic;
      strobe : out   std_logic
    );
  end component config_SPI;

begin

  ConfigWriteData        <= UART_WriteData_Mux;
  ConfigWriteStrobe      <= UART_WriteStrobe_Mux;
  FSM_Reset              <= UART_ComActive or BitBangActive or spi_active;
  ComActive              <= UART_ComActive;
  ReceiveLED             <= UART_LED xor BitBangWriteStrobe;
  BitBangWriteData_Mux   <= BitBangWriteData when BitBangActive = '1' else
                            SelfWriteData;
  BitBangWriteStrobe_Mux <= BitBangWriteStrobe when BitBangActive = '1' else
                            SelfWriteStrobe;
  spi_write_data_mux     <= spi_write_data when spi_active = '1' else
                            BitBangWriteData_Mux;
  spi_strobe_mux         <= spi_strobe when spi_active = '1' else
                            BitBangWriteStrobe_Mux;
  UART_WriteData_Mux     <= std_logic_vector(UART_WriteData) when UART_ComActive = '1' else
                            spi_write_data_mux;
  UART_WriteStrobe_Mux   <= UART_WriteStrobe when UART_ComActive = '1' else
                            spi_strobe_mux;
  FrameAddressRegister   <= FrameAddressRegister_Readable;
  LongFrameStrobe        <= LongFrameStrobe_Readable;
  RowSelect              <= RowSelect_Readable;

  -- Generated from instantiation at eFPGA_Config.v:90
  configfsm_inst : component ConfigFSM
    port map (
      CLK                  => CLK,
      FSM_Reset            => FSM_Reset,
      FrameAddressRegister => FrameAddressRegister_Readable,
      LongFrameStrobe      => LongFrameStrobe_Readable,
      RowSelect            => RowSelect_Readable,
      WriteData            => UART_WriteData_Mux,
      WriteStrobe          => UART_WriteStrobe_Mux,
      resetn               => resetn
    );

  -- Generated from instantiation at eFPGA_Config.v:42

  gen_uart_enabled : if uart_enable = 1 generate

    inst_config_uart : component config_UART
      port map (
        CLK         => CLK,
        ComActive   => UART_ComActive,
        Command     => Command,
        ReceiveLED  => UART_LED,
        Rx          => Rx,
        WriteData   => UART_WriteData,
        WriteStrobe => UART_WriteStrobe,
        resetn      => resetn
      );

  end generate gen_uart_enabled;

  -- Tie off the signals if UART is disabled

  gen_uart_disabled : if uart_enable = 0 generate
    UART_WriteData   <= (others => '0');
    UART_ComActive   <= '0';
    UART_WriteStrobe <= '0';
    Command          <= (others => '0');
    UART_LED         <= '0';
  end generate gen_uart_disabled;

  -- Generated from instantiation at eFPGA_Config.v:54

  gen_bitbang_enabled : if bitbang_enable = 1 generate

    inst_bitbang : component bitbang
      port map (
        active => BitBangActive,
        clk    => CLK,
        data   => BitBangWriteData,
        resetn => resetn,
        s_clk  => s_clk,
        s_data => s_data,
        strobe => BitBangWriteStrobe
      );

  end generate gen_bitbang_enabled;

  -- Tie off the signals if bitbang is disabled

  gen_bitbang_disabled : if bitbang_enable = 0 generate
    BitBangActive      <= '0';
    BitBangWriteData   <= (others => '0');
    BitBangWriteStrobe <= '0';
  end generate gen_bitbang_disabled;

  gen_spi_enabled : if spi_enable = 1 generate

    inst_config_spi : component config_SPI
      port map (
        active => spi_active,
        clk    => CLK,
        data   => spi_write_data,
        mosi   => mosi,
        resetn => resetn,
        sck    => sck,
        ss_n   => ss_n,
        strobe => spi_strobe
      );

  end generate gen_spi_enabled;

  gen_spi_disabled : if spi_enable = 0 generate
    spi_active     <= '0';
    spi_write_data <= (others => '0');
    spi_strobe     <= '0';
  end generate gen_spi_disabled;

end architecture from_verilog;
