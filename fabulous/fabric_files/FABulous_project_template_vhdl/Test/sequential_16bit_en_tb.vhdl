library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use std.env.finish;
  use std.textio.all;

entity sequential_16bit_en_tb is
end entity sequential_16bit_en_tb;

architecture behavior of sequential_16bit_en_tb is

  component efpga_top is
    generic (
      framebitsperrow  : integer := 32;
      frameselectwidth : integer := 5;
      maxframespercol  : integer := 20;
      numberofcols     : integer := 10;
      numberofrows     : integer := 14;
      rowselectwidth   : integer := 5;
      desync_flag      : integer := 20;
      include_efpga    : integer := 1
    );
    port (
      i_top          : out   std_logic_vector(NumberOfRows * 2 - 1 downto 0);
      t_top          : out   std_logic_vector(NumberOfRows * 2 - 1 downto 0);
      o_top          : in    std_logic_vector(NumberOfRows * 2 - 1 downto 0);
      a_config_c     : out   std_logic_vector(NumberOfRows * 4 - 1 downto 0);
      b_config_c     : out   std_logic_vector(NumberOfRows * 4 - 1 downto 0);
      config_accessc : out   std_logic_vector( 55 downto 0);

      clk             : in    std_logic;
      resetn          : in    std_logic;
      comactive       : out   std_logic;
      receiveled      : out   std_logic;
      rx              : in    std_logic;
      s_clk           : in    std_logic;
      s_data          : in    std_logic;
      selfwritedata   : in    std_logic_vector(31 downto 0);
      selfwritestrobe : in    std_logic
    );
  end component efpga_top;

  component sequential_16bit_en is
    port (
      clk    : in    std_logic;
      io_out : out   std_logic_vector(27 downto 0);
      io_oeb : out   std_logic_vector(27 downto 0);
      io_in  : in    std_logic_vector(27 downto 0)
    );
  end component sequential_16bit_en;

  constant max_bitbytes : integer := 16384;

  signal i_top         : std_logic_vector( 27 downto 0);
  signal t_top         : std_logic_vector(27 downto 0);
  signal o_top         : std_logic_vector( 27 downto 0);
  signal a_cfg         : std_logic_vector(55 downto 0);
  signal b_cfg         : std_logic_vector(55 downto 0);
  signal config_access : std_logic_vector(55 downto 0);

  signal i_top_gold : std_logic_vector(27 downto 0);
  signal t_top_gold : std_logic_vector(27 downto 0);
  signal oeb_gold   : std_logic_vector(27 downto 0);

  signal clk             : std_logic;
  signal resetn          : std_logic;
  signal selfwritestrobe : std_logic;
  signal selfwritedata   : std_logic_vector(31 downto 0);
  signal comactive       : std_logic;
  signal rx              : std_logic;
  signal s_clk           : std_logic;
  signal s_data          : std_logic;
  signal receiveled      : std_logic;

  type bitstream_type is array (max_bitbytes downto 0) of std_logic_vector(7 downto 0);

  signal bitstream : bitstream_type;

  impure function readmemh (
    filename : string
  ) return bitstream_type is

    variable bs        : bitstream_type;
    file     read_file : text open read_mode is "build/sequential_16bit_en.hex";
    variable counter   : integer;
    variable l         : line;
    variable temp      : std_logic_vector(7 downto 0);
    variable good_v    : boolean;

  begin

    counter := 0;

    while not endfile(read_file) loop

      readline (read_file, l);
      hread (l, temp, good_v);
      bs(counter) := temp;
      counter     := counter + 1;

    end loop;

    return bs;

  end function readmemh;

begin

  init_efpga : component efpga_top
    generic map (
      framebitsperrow  => 32,
      frameselectwidth => 5,
      maxframespercol  => 20,
      numberofcols     => 10,
      numberofrows     => 14,
      rowselectwidth   => 5,
      desync_flag      => 20,
      include_efpga    => 1
    )
    port map (
      i_top          => i_top,
      t_top          => t_top,
      o_top          => o_top,
      a_config_c     => a_cfg,
      b_config_c     => b_cfg,
      config_accessc => config_access,

      clk             => clk,
      resetn          => resetn,
      selfwritestrobe => selfwritestrobe,
      selfwritedata   => selfwritedata,

      rx         => rx,
      comactive  => comactive,
      receiveled => receiveled,
      s_clk      => s_clk,
      s_data     => s_data

    );

  init_top : component sequential_16bit_en
    port map (
      clk    => clk,
      io_out => i_top_gold,
      io_oeb => oeb_gold,
      io_in  => o_top
    );

  t_top_gold <= not oeb_gold;

  process_001 : process is
  begin

    clk <= '0';
    wait for 5000 ps;

    loop

      clk <= not clk;
      wait for 5000 ps;

    end loop;

  end process process_001;

  process_002 : process is

    variable i : integer;

  begin

    o_top           <= x"0000000";
    resetn          <= '0';
    selfwritestrobe <= '0';
    selfwritedata   <= x"00000000";
    rx              <= '1';
    s_clk           <= '0';
    s_data          <= '0';
    i               := 0;

    while i < max_bitbytes loop

      bitstream(i) <= x"00";
      i            := i + 1;

    end loop;

    i         := 0;
    bitstream <= readmemh("bitstream.hex");
    wait for 100 ps;
    report "Bitstream loaded into memory array";
    resetn    <= '0';
    wait for 10000 ps;
    resetn    <= '1';
    wait for 10000 ps;

    for verilog_repeat in 1 to 20 loop

      wait until rising_edge(clk);

    end loop;

    wait for 2500 ps;

    while i < max_bitbytes loop

      selfwritedata <= bitstream(i) & bitstream(i + 1) & bitstream(i + 2) & bitstream(i + 3);
      -- wait 2 clock cycles
      wait until rising_edge(clk);
      wait until rising_edge(clk);

      -- report integer'image(i) & " " & to_hstring(SelfWriteData);
      selfwritestrobe <= '1';
      wait until rising_edge(clk);
      selfwritestrobe <= '0';

      -- wait another 2 clock cycles
      wait until rising_edge(clk);
      wait until rising_edge(clk);

      i := i + 4;

    end loop;

    -- wait 100 clock cycles
    for verilog_repeat in 1 to 100 loop

      wait until rising_edge(clk);

    end loop;

    report "Configuration completed";

    -- reset user design
    o_top <= b"0000_0000_0000_0000_0000_0000_0011";

    -- wait 5 clock cycles
    for verilog_repeat in 1 to 5 loop

      wait until rising_edge(clk);

    end loop;

    -- start user design
    o_top <= b"0000_0000_0000_0000_0000_0000_0010";
    wait until rising_edge(clk);

    for verilog_repeat in 0 to 100 loop

      wait until falling_edge(clk);
      report "fabric = " & integer'image(To_Integer(unsigned(i_top))) &
             " gold = " & integer'image(To_Integer(unsigned(i_top_gold)));

      if (To_integer(unsigned(i_top)) /= To_integer(unsigned(i_top_gold))) then
        report "Error: Miss match between fabric output and golden "
          severity error;
      end if;

    end loop;

    report "SIMULATION FINISHED";

    wait for 5000 ps;
    finish;

  end process process_002;

end architecture behavior;
