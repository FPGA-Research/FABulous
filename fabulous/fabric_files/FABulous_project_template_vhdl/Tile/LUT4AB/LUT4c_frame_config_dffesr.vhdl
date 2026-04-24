package attr_pack_lut4ab_lut4c_frame_config_dffesr is

  attribute fabulous    : string;
  attribute belmap      : string;
  attribute init        : integer;
  attribute init_1      : integer;
  attribute init_2      : integer;
  attribute init_3      : integer;
  attribute init_4      : integer;
  attribute init_5      : integer;
  attribute init_6      : integer;
  attribute init_7      : integer;
  attribute init_8      : integer;
  attribute init_9      : integer;
  attribute init_10     : integer;
  attribute init_11     : integer;
  attribute init_12     : integer;
  attribute init_13     : integer;
  attribute init_14     : integer;
  attribute init_15     : integer;
  attribute fab_attr_ff : integer;
  attribute iomux       : integer;
  attribute set_noreset : integer;
  attribute external    : string;
  attribute shared_port : string;
  attribute global      : string;

end package attr_pack_lut4ab_lut4c_frame_config_dffesr;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_lut4ab_lut4c_frame_config_dffesr.all;

-- (* FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2, INIT_3=3, INIT_4=4,
-- INIT_5=5, INIT_6=6, INIT_7=7, INIT_8=8, INIT_9=9, INIT_10=10,
-- INIT_11=11, INIT_12=12, INIT_13=13, INIT_14=14, INIT_15=15,
-- FAB_ATTR_FF=16, IOmux=17, SET_NORESET=18 *)

entity lut4c_frame_config_dffesr is
  generic (
    noconfigbits : integer := 19 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (                                     -- IMPORTANT: this has to be in a dedicated line
    i  : in    std_logic_vector(3 downto 0); -- LUT inputs
    o  : out   std_logic;                    -- LUT output (combinatorial or FF)
    ci : in    std_logic;                    -- carry chain input
    co : out   std_logic;                    -- carry chain output
    sr : in    std_logic;                    -- (* FABulous, SHARED_RESET *)
    en : in    std_logic;                    -- (* FABulous, SHARED_ENABLE *)
    -- EXTERNAL sends this signal all the way to top.
    -- SHARED allows multiple BELs to use the same port.
    userclk : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    configbits : in    std_logic_vector(noconfigbits - 1 downto 0)
  );

  attribute fabulous of LUT4c_frame_config_dffesr    : entity is "TRUE";
  attribute belmap of LUT4c_frame_config_dffesr      : entity is "TRUE";
  attribute init of LUT4c_frame_config_dffesr        : entity is 0;

  attribute init_3 of LUT4c_frame_config_dffesr      : entity is 3;
  attribute init_4 of LUT4c_frame_config_dffesr      : entity is 4;
  attribute init_5 of LUT4c_frame_config_dffesr      : entity is 5;
  attribute init_6 of LUT4c_frame_config_dffesr      : entity is 6;
  attribute init_7 of LUT4c_frame_config_dffesr      : entity is 7;
  attribute init_8 of LUT4c_frame_config_dffesr      : entity is 8;
  attribute init_9 of LUT4c_frame_config_dffesr      : entity is 9;
  attribute init_10 of LUT4c_frame_config_dffesr     : entity is 10;
  attribute init_11 of LUT4c_frame_config_dffesr     : entity is 11;
  attribute init_12 of LUT4c_frame_config_dffesr     : entity is 12;
  attribute init_13 of LUT4c_frame_config_dffesr     : entity is 13;
  attribute init_14 of LUT4c_frame_config_dffesr     : entity is 14;
  attribute init_15 of LUT4c_frame_config_dffesr     : entity is 15;
  attribute fab_attr_ff of LUT4c_frame_config_dffesr : entity is 16;
  attribute iomux of LUT4c_frame_config_dffesr       : entity is 17;
  attribute set_noreset of LUT4c_frame_config_dffesr : entity is 18;
  attribute external of UserCLK                      : signal is "TRUE";
  attribute shared_port of UserCLK                   : signal is "TRUE";
  attribute global of ConfigBits                     : signal is "TRUE";
end entity lut4c_frame_config_dffesr;

architecture behavioral of lut4c_frame_config_dffesr is

  constant lut_size    : integer := 4;
  constant n_lut_flops : integer := 2 ** lut_size;
  signal   lut_values  : std_logic_vector(n_lut_flops - 1 downto 0);

  signal lut_index    : unsigned(lut_size - 1 downto 0);
  signal lut_index_0n : std_logic;
  signal lut_index_1n : std_logic;
  signal lut_index_2n : std_logic;
  signal lut_index_3n : std_logic;

  signal lut_out       : std_logic;
  signal lut_flop      : std_logic;
  signal i0mux         : std_logic; -- normal input '0', or carry input '1'
  signal c_out_mux     : std_logic;
  signal c_i0mux       : std_logic;
  signal c_reset_value : std_logic; -- extra configuration bits

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      s  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

  component cus_mux161 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a10 : in    std_logic;
      a11 : in    std_logic;
      a12 : in    std_logic;
      a13 : in    std_logic;
      a14 : in    std_logic;
      a15 : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      a4  : in    std_logic;
      a5  : in    std_logic;
      a6  : in    std_logic;
      a7  : in    std_logic;
      a8  : in    std_logic;
      a9  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      s2  : in    std_logic;
      s2n : in    std_logic;
      s3  : in    std_logic;
      s3n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux161;

begin

  lut_values    <= configbits(15 downto 0);
  c_out_mux     <= configbits(16);
  c_i0mux       <= configbits(17);
  c_reset_value <= configbits(18);

  -- I0mux <= I(0) when (c_I0mux = '0') else
  --   Ci;

  inst_cus_mux21_i0mux : component cus_mux21
    port map (
      a0 => i(0),
      a1 => ci,
      s  => c_i0mux,
      x  => i0mux
    );

  lut_index <= i(3) & i(2) & i(1) & i0mux;

  -- The LUT is just a multiplexer
  -- for a first shot, I am using a 16:1
  -- LUT_out <= LUT_values(TO_INTEGER(LUT_index));
  lut_index_0n <= not lut_index(0);
  lut_index_1n <= not lut_index(1);
  lut_index_2n <= not lut_index(2);
  lut_index_3n <= not lut_index(3);

  inst_cus_mux161 : component cus_mux161
    port map (
      a0  => lut_values(0),
      a1  => lut_values(1),
      a2  => lut_values(2),
      a3  => lut_values(3),
      a4  => lut_values(4),
      a5  => lut_values(5),
      a6  => lut_values(6),
      a7  => lut_values(7),
      a8  => lut_values(8),
      a9  => lut_values(9),
      a10 => lut_values(10),
      a11 => lut_values(11),
      a12 => lut_values(12),
      a13 => lut_values(13),
      a14 => lut_values(14),
      a15 => lut_values(15),
      s0  => lut_index(0),
      s0n => lut_index_0n,
      s1  => lut_index(1),
      s1n => lut_index_1n,
      s2  => lut_index(2),
      s2n => lut_index_2n,
      s3  => lut_index(3),
      s3n => lut_index_3n,
      x   => lut_out
    );

  cus_mux21_o : component cus_mux21
    port map (
      a0 => lut_out,
      a1 => lut_flop,
      s  => c_out_mux,
      x  => o
    );

  -- iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT
  co <= (ci and i(1)) or (ci and i(2)) or (i(1) and i(2));

  process_001 : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      if (en = '1') then
        if (sr = '1') then
          lut_flop <= c_reset_value;
        else
          lut_flop <= lut_out;
        end if;
      end if;
    end if;

  end process process_001;

end architecture behavioral;
