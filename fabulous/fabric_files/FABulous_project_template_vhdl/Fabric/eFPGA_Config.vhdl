library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity eFPGA_Config is
  generic (
    NumberOfRows    : integer := 16;
    RowSelectWidth  : integer := 5;
    FrameBitsPerRow : integer := 32;
    desync_flag     : integer := 20;
    bitbang_enable  : integer := 1;
    uart_enable     : integer := 1;
    spi_enable      : integer := 0;
    parallel_enable : integer := 1;
    axi_enable      : integer := 0
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

    -- SPI configuration port
    sck  : in    std_logic;
    mosi : in    std_logic;
    ss_n : in    std_logic;

    -- AXI configuration port (types match config_AXI entity)
    s_axi_awaddr  : in    unsigned(31 downto 0);
    s_axi_awvalid : in    std_logic;
    s_axi_awready : buffer std_logic;
    s_axi_wdata   : in    unsigned(31 downto 0);
    s_axi_wstrb   : in    unsigned(3 downto 0);
    s_axi_wvalid  : in    std_logic;
    s_axi_wready  : buffer std_logic;
    s_axi_bresp   : out   unsigned(1 downto 0);
    s_axi_bvalid  : buffer std_logic;
    s_axi_bready  : in    std_logic;
    s_axi_araddr  : in    unsigned(31 downto 0);
    s_axi_arvalid : in    std_logic;
    s_axi_arready : buffer std_logic;
    s_axi_rdata   : out   unsigned(31 downto 0);
    s_axi_rresp   : out   unsigned(1 downto 0);
    s_axi_rvalid  : buffer std_logic;
    s_axi_rready  : in    std_logic;

    -- Parallel configuration port
    SelfWriteData     : in    std_logic_vector(31 downto 0);
    SelfWriteStrobe   : in    std_logic;
    ConfigWriteData   : out   std_logic_vector(31 downto 0);
    ConfigWriteStrobe : out   std_logic;

    -- Configuration frame outputs
    FrameAddressRegister : out   std_logic_vector(FrameBitsPerRow - 1 downto 0);
    LongFrameStrobe      : out   std_logic;
    RowSelect            : out   std_logic_vector(RowSelectWidth - 1 downto 0)
  );
end entity eFPGA_Config;

architecture from_verilog of eFPGA_Config is

  -- UART signals
  signal UART_WriteData   : unsigned(31 downto 0);
  signal UART_WriteStrobe : std_logic;
  signal UART_ComActive   : std_logic;
  signal UART_LED         : std_logic;
  signal Command          : unsigned(7 downto 0);

  -- BitBang signals
  signal BitBangActive      : std_logic;
  signal BitBangWriteData   : unsigned(31 downto 0);
  signal BitBangWriteStrobe : std_logic;

  -- SPI signals
  signal spi_active     : std_logic;
  signal spi_write_data : unsigned(31 downto 0);
  signal spi_strobe     : std_logic;

  -- AXI signals
  signal axi_active     : std_logic;
  signal axi_write_data : unsigned(31 downto 0);
  signal axi_strobe     : std_logic;

  -- Parallel gated signals
  signal parallel_data_gated   : std_logic_vector(31 downto 0);
  signal parallel_strobe_gated : std_logic;

  -- Multiplexed signals (kept as std_logic_vector; boundary casts go around)
  signal BitBangWriteData_Mux   : std_logic_vector(31 downto 0);
  signal BitBangWriteStrobe_Mux : std_logic;
  signal spi_write_data_mux     : std_logic_vector(31 downto 0);
  signal spi_strobe_mux         : std_logic;
  signal UART_WriteData_Mux     : std_logic_vector(31 downto 0);
  signal UART_WriteStrobe_Mux   : std_logic;
  signal axi_write_data_mux     : std_logic_vector(31 downto 0);
  signal axi_strobe_mux         : std_logic;

  signal FSM_Reset : std_logic;

  -- Readable outputs from ConfigFSM
  signal FrameAddressRegister_Readable : unsigned(31 downto 0);
  signal LongFrameStrobe_Readable      : std_logic;
  signal RowSelect_Readable            : unsigned(4 downto 0);

  component ConfigFSM is
    port (
      CLK                    : in    std_logic;
      frame_address_register : out   unsigned(31 downto 0);
      fsm_reset              : in    std_logic;
      long_frame_strobe      : out   std_logic;
      reset_n                : in    std_logic;
      row_select             : out   unsigned(4 downto 0);
      write_data             : in    unsigned(31 downto 0);
      write_strobe           : in    std_logic
    );
  end component ConfigFSM;

  component config_UART is
    port (
      CLK         : in    std_logic;
      ComActive   : out   std_logic;
      Command     : out   unsigned(7 downto 0);
      ReceiveLED  : out   std_logic;
      Rx          : in    std_logic;
      WriteData   : out   unsigned(31 downto 0);
      WriteStrobe : out   std_logic;
      reset_n     : in    std_logic
    );
  end component config_UART;

  component bitbang is
    port (
      active  : out   std_logic;
      clk     : in    std_logic;
      data    : out   unsigned(31 downto 0);
      reset_n : in    std_logic;
      s_clk   : in    std_logic;
      s_data  : in    std_logic;
      strobe  : out   std_logic
    );
  end component bitbang;

  component config_SPI is
    port (
      active  : out   std_logic;
      clk     : in    std_logic;
      data    : out   unsigned(31 downto 0);
      mosi    : in    std_logic;
      reset_n : in    std_logic;
      sck     : in    std_logic;
      ss_n    : in    std_logic;
      strobe  : out   std_logic
    );
  end component config_SPI;

  component config_AXI is
    port (
      active        : out   std_logic;
      clk           : in    std_logic;
      data          : out   unsigned(31 downto 0);
      reset_n       : in    std_logic;
      s_axi_araddr  : in    unsigned(31 downto 0);
      s_axi_arready : buffer std_logic;
      s_axi_arvalid : in    std_logic;
      s_axi_awaddr  : in    unsigned(31 downto 0);
      s_axi_awready : buffer std_logic;
      s_axi_awvalid : in    std_logic;
      s_axi_bready  : in    std_logic;
      s_axi_bresp   : out   unsigned(1 downto 0);
      s_axi_bvalid  : buffer std_logic;
      s_axi_rdata   : out   unsigned(31 downto 0);
      s_axi_rready  : in    std_logic;
      s_axi_rresp   : out   unsigned(1 downto 0);
      s_axi_rvalid  : buffer std_logic;
      s_axi_wdata   : in    unsigned(31 downto 0);
      s_axi_wready  : buffer std_logic;
      s_axi_wstrb   : in    unsigned(3 downto 0);
      s_axi_wvalid  : in    std_logic;
      strobe        : out   std_logic
    );
  end component config_AXI;

begin

  -- Parallel port gating
  parallel_data_gated   <= SelfWriteData when parallel_enable = 1 else
                           (others => '0');
  parallel_strobe_gated <= SelfWriteStrobe when parallel_enable = 1 else
                           '0';

  -- Configuration port priority muxing: AXI > UART > SPI > BitBang > Parallel
  BitBangWriteData_Mux   <= std_logic_vector(BitBangWriteData) when BitBangActive = '1' else
                            parallel_data_gated;
  BitBangWriteStrobe_Mux <= BitBangWriteStrobe when BitBangActive = '1' else
                            parallel_strobe_gated;

  spi_write_data_mux <= std_logic_vector(spi_write_data) when spi_active = '1' else
                        BitBangWriteData_Mux;
  spi_strobe_mux     <= spi_strobe when spi_active = '1' else
                        BitBangWriteStrobe_Mux;

  UART_WriteData_Mux   <= std_logic_vector(UART_WriteData) when UART_ComActive = '1' else
                          spi_write_data_mux;
  UART_WriteStrobe_Mux <= UART_WriteStrobe when UART_ComActive = '1' else
                          spi_strobe_mux;

  axi_write_data_mux <= std_logic_vector(axi_write_data) when axi_active = '1' else
                        UART_WriteData_Mux;
  axi_strobe_mux     <= axi_strobe when axi_active = '1' else
                        UART_WriteStrobe_Mux;

  ConfigWriteData   <= axi_write_data_mux;
  ConfigWriteStrobe <= axi_strobe_mux;

  FSM_Reset <= UART_ComActive or BitBangActive or spi_active or axi_active;

  ComActive  <= UART_ComActive;
  ReceiveLED <= UART_LED xor BitBangWriteStrobe;

  FrameAddressRegister <= std_logic_vector(FrameAddressRegister_Readable);
  LongFrameStrobe      <= LongFrameStrobe_Readable;
  RowSelect            <= std_logic_vector(RowSelect_Readable);

  -- ConfigFSM instance (no generics on the entity)
  configfsm_inst : component ConfigFSM
    port map (
      CLK                    => CLK,
      frame_address_register => FrameAddressRegister_Readable,
      fsm_reset              => FSM_Reset,
      long_frame_strobe      => LongFrameStrobe_Readable,
      reset_n                => resetn,
      row_select             => RowSelect_Readable,
      write_data             => unsigned(axi_write_data_mux),
      write_strobe           => axi_strobe_mux
    );

  -- UART

  gen_uart_enabled : if uart_enable = 1 generate

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

  end generate gen_uart_enabled;

  gen_uart_disabled : if uart_enable = 0 generate
    UART_WriteData   <= (others => '0');
    UART_ComActive   <= '0';
    UART_WriteStrobe <= '0';
    Command          <= (others => '0');
    UART_LED         <= '0';
  end generate gen_uart_disabled;

  -- BitBang

  gen_bitbang_enabled : if bitbang_enable = 1 generate

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

  end generate gen_bitbang_enabled;

  gen_bitbang_disabled : if bitbang_enable = 0 generate
    BitBangWriteData   <= (others => '0');
    BitBangWriteStrobe <= '0';
    BitBangActive      <= '0';
  end generate gen_bitbang_disabled;

  -- SPI

  gen_spi_enabled : if spi_enable = 1 generate

    inst_config_spi : component config_SPI
      port map (
        sck     => sck,
        mosi    => mosi,
        ss_n    => ss_n,
        strobe  => spi_strobe,
        data    => spi_write_data,
        active  => spi_active,
        clk     => CLK,
        reset_n => resetn
      );

  end generate gen_spi_enabled;

  gen_spi_disabled : if spi_enable = 0 generate
    spi_strobe     <= '0';
    spi_write_data <= (others => '0');
    spi_active     <= '0';
  end generate gen_spi_disabled;

  -- AXI

  gen_axi_enabled : if axi_enable = 1 generate

    inst_config_axi : component config_AXI
      port map (
        clk           => CLK,
        reset_n       => resetn,
        s_axi_awaddr  => s_axi_awaddr,
        s_axi_awvalid => s_axi_awvalid,
        s_axi_awready => s_axi_awready,
        s_axi_wdata   => s_axi_wdata,
        s_axi_wstrb   => s_axi_wstrb,
        s_axi_wvalid  => s_axi_wvalid,
        s_axi_wready  => s_axi_wready,
        s_axi_bresp   => s_axi_bresp,
        s_axi_bvalid  => s_axi_bvalid,
        s_axi_bready  => s_axi_bready,
        s_axi_araddr  => s_axi_araddr,
        s_axi_arvalid => s_axi_arvalid,
        s_axi_arready => s_axi_arready,
        s_axi_rdata   => s_axi_rdata,
        s_axi_rresp   => s_axi_rresp,
        s_axi_rvalid  => s_axi_rvalid,
        s_axi_rready  => s_axi_rready,
        strobe        => axi_strobe,
        data          => axi_write_data,
        active        => axi_active
      );

  end generate gen_axi_enabled;

  gen_axi_disabled : if axi_enable = 0 generate
    axi_strobe     <= '0';
    axi_write_data <= (others => '0');
    axi_active     <= '0';

    s_axi_awready <= '0';
    s_axi_wready  <= '0';
    s_axi_bresp   <= "00";
    s_axi_bvalid  <= '0';
    s_axi_arready <= '0';
    s_axi_rdata   <= (others => '0');
    s_axi_rresp   <= "00";
    s_axi_rvalid  <= '0';
  end generate gen_axi_disabled;

end architecture from_verilog;
