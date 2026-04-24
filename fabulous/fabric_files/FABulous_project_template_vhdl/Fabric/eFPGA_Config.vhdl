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

entity efpga_config is
  generic (
    rowselectwidth  : integer := 5;
    framebitsperrow : integer := 32;
    numberofrows    : integer := 16;
    desync_flag     : integer := 20
  );
  port (
    clk                  : in    std_logic;
    comactive            : out   std_logic;
    configwritedata      : out   std_logic_vector(31 downto 0);
    configwritestrobe    : out   std_logic;
    frameaddressregister : out   std_logic_vector(31 downto 0);
    longframestrobe      : out   std_logic;
    receiveled           : out   std_logic;
    rowselect            : out   std_logic_vector(4 downto 0);
    rx                   : in    std_logic;
    selfwritedata        : in    std_logic_vector(31 downto 0);
    selfwritestrobe      : in    std_logic;
    resetn               : in    std_logic;
    s_clk                : in    std_logic;
    s_data               : in    std_logic
  );
end entity efpga_config;

-- Generated from Verilog module eFPGA_Config (eFPGA_Config.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20

architecture from_verilog of efpga_config is

  signal bitbangactive          : std_logic;
  signal bitbangwritedata       : std_logic_vector(31 downto 0);
  signal bitbangwritedata_mux   : std_logic_vector(31 downto 0);
  signal bitbangwritestrobe     : std_logic;
  signal bitbangwritestrobe_mux : std_logic;
  signal command                : unsigned(7 downto 0);
  signal fsm_reset              : std_logic;
  signal uart_comactive         : std_logic;
  signal uart_led               : std_logic;
  signal uart_writedata         : unsigned(31 downto 0);
  signal uart_writedata_mux     : std_logic_vector(31 downto 0);
  signal uart_writestrobe       : std_logic;
  signal uart_writestrobe_mux   : std_logic;

  component configfsm is
    generic (
      framebitsperrow : integer := FrameBitsPerRow;
      numberofrows    : integer := NumberOfRows;
      rowselectwidth  : integer := RowSelectWidth;
      desync_flag     : integer := desync_flag
    );
    port (
      clk                  : in    std_logic;
      fsm_reset            : in    std_logic;
      frameaddressregister : out   std_logic_vector(31 downto 0);
      longframestrobe      : out   std_logic;
      rowselect            : out   std_logic_vector(4 downto 0);
      writedata            : in    std_logic_vector(31 downto 0);
      writestrobe          : in    std_logic;
      resetn               : in    std_logic
    );
  end component configfsm;

  signal frameaddressregister_readable : std_logic_vector(31 downto 0); -- Needed to connect outputs
  signal longframestrobe_readable      : std_logic;                     -- Needed to connect outputs
  signal rowselect_readable            : std_logic_vector(4 downto 0);  -- Needed to connect outputs

  component config_uart is
    port (
      clk         : in    std_logic;
      comactive   : out   std_logic;
      command     : out   unsigned(7 downto 0);
      receiveled  : out   std_logic;
      rx          : in    std_logic;
      writedata   : out   unsigned(31 downto 0);
      writestrobe : out   std_logic;
      resetn      : in    std_logic
    );
  end component config_uart;

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

begin

  configwritedata        <= uart_writedata_mux;
  configwritestrobe      <= uart_writestrobe_mux;
  fsm_reset              <= uart_comactive or bitbangactive;
  comactive              <= uart_comactive;
  receiveled             <= uart_led xor bitbangwritestrobe;
  bitbangwritedata_mux   <= bitbangwritedata when bitbangactive = '1' else
                            selfwritedata;
  bitbangwritestrobe_mux <= bitbangwritestrobe when bitbangactive = '1' else
                            selfwritestrobe;
  uart_writedata_mux     <= std_logic_vector(uart_writedata) when uart_comactive = '1' else
                            bitbangwritedata_mux;
  uart_writestrobe_mux   <= uart_writestrobe when uart_comactive = '1' else
                            bitbangwritestrobe_mux;
  frameaddressregister   <= frameaddressregister_readable;
  longframestrobe        <= longframestrobe_readable;
  rowselect              <= rowselect_readable;

  -- Generated from instantiation at eFPGA_Config.v:90
  configfsm_inst : component configfsm
    port map (
      clk                  => clk,
      fsm_reset            => fsm_reset,
      frameaddressregister => frameaddressregister_readable,
      longframestrobe      => longframestrobe_readable,
      rowselect            => rowselect_readable,
      writedata            => uart_writedata_mux,
      writestrobe          => uart_writestrobe_mux,
      resetn               => resetn
    );

  -- Generated from instantiation at eFPGA_Config.v:42
  inst_config_uart : component config_uart
    port map (
      clk         => clk,
      comactive   => uart_comactive,
      command     => command,
      receiveled  => uart_led,
      rx          => rx,
      writedata   => uart_writedata,
      writestrobe => uart_writestrobe,
      resetn      => resetn
    );

  -- Generated from instantiation at eFPGA_Config.v:54
  inst_bitbang : component bitbang
    port map (
      active => bitbangactive,
      clk    => clk,
      data   => bitbangwritedata,
      resetn => resetn,
      s_clk  => s_clk,
      s_data => s_data,
      strobe => bitbangwritestrobe
    );

end architecture from_verilog;
