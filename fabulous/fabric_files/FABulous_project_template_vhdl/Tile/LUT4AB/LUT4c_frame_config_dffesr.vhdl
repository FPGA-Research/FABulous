package attr_pack_lut4ab_lut4c_frame_config_dffesr is

  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute INIT        : integer;
  attribute INIT_1      : integer;
  attribute INIT_2      : integer;
  attribute INIT_3      : integer;
  attribute INIT_4      : integer;
  attribute INIT_5      : integer;
  attribute INIT_6      : integer;
  attribute INIT_7      : integer;
  attribute INIT_8      : integer;
  attribute INIT_9      : integer;
  attribute INIT_10     : integer;
  attribute INIT_11     : integer;
  attribute INIT_12     : integer;
  attribute INIT_13     : integer;
  attribute INIT_14     : integer;
  attribute INIT_15     : integer;
  attribute FAB_ATTR_FF : integer;
  attribute IOmux       : integer;
  attribute SET_NORESET : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;

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
    NoConfigBits : integer := 19 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (                                     -- IMPORTANT: this has to be in a dedicated line
    I  : in    std_logic_vector(3 downto 0); -- LUT inputs
    O  : out   std_logic;                    -- LUT output (combinatorial or FF)
    Ci : in    std_logic;                    -- carry chain input
    Co : out   std_logic;                    -- carry chain output
    SR : in    std_logic;                    -- (* FABulous, SHARED_RESET *)
    EN : in    std_logic;                    -- (* FABulous, SHARED_ENABLE *)
    -- EXTERNAL sends this signal all the way to top.
    -- SHARED allows multiple BELs to use the same port.
    UserCLK : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in    std_logic_vector(NoConfigBits - 1 downto 0)
  );

  attribute FABulous of LUT4c_frame_config_dffesr    : entity is "TRUE";
  attribute BelMap of LUT4c_frame_config_dffesr      : entity is "TRUE";
  attribute INIT of LUT4c_frame_config_dffesr        : entity is 0;
  attribute INIT_1 of LUT4c_frame_config_dffesr      : entity is 1;
  attribute INIT_2 of LUT4c_frame_config_dffesr      : entity is 2;
  attribute INIT_3 of LUT4c_frame_config_dffesr      : entity is 3;
  attribute INIT_4 of LUT4c_frame_config_dffesr      : entity is 4;
  attribute INIT_5 of LUT4c_frame_config_dffesr      : entity is 5;
  attribute INIT_6 of LUT4c_frame_config_dffesr      : entity is 6;
  attribute INIT_7 of LUT4c_frame_config_dffesr      : entity is 7;
  attribute INIT_8 of LUT4c_frame_config_dffesr      : entity is 8;
  attribute INIT_9 of LUT4c_frame_config_dffesr      : entity is 9;
  attribute INIT_10 of LUT4c_frame_config_dffesr     : entity is 10;
  attribute INIT_11 of LUT4c_frame_config_dffesr     : entity is 11;
  attribute INIT_12 of LUT4c_frame_config_dffesr     : entity is 12;
  attribute INIT_13 of LUT4c_frame_config_dffesr     : entity is 13;
  attribute INIT_14 of LUT4c_frame_config_dffesr     : entity is 14;
  attribute INIT_15 of LUT4c_frame_config_dffesr     : entity is 15;
  attribute FAB_ATTR_FF of LUT4c_frame_config_dffesr : entity is 16;
  attribute IOmux of LUT4c_frame_config_dffesr       : entity is 17;
  attribute SET_NORESET of LUT4c_frame_config_dffesr : entity is 18;
  attribute EXTERNAL of UserCLK                      : signal is "TRUE";
  attribute SHARED_PORT of UserCLK                   : signal is "TRUE";
  attribute GLOBAL of ConfigBits                     : signal is "TRUE";
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
      S  : in    std_logic;
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

  lut_values    <= ConfigBits(15 downto 0);
  c_out_mux     <= ConfigBits(16);
  c_i0mux       <= ConfigBits(17);
  c_reset_value <= ConfigBits(18);

  -- I0mux <= I(0) when (c_I0mux = '0') else
  --   Ci;

  inst_cus_mux21_i0mux : component cus_mux21
    port map (
      a0 => I(0),
      a1 => Ci,
      S  => c_i0mux,
      x  => i0mux
    );

  lut_index <= I(3) & I(2) & I(1) & i0mux;

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
      S  => c_out_mux,
      x  => O
    );

  -- iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT
  Co <= (Ci and I(1)) or (Ci and I(2)) or (I(1) and I(2));

  process_001 : process (UserCLK) is
  begin

    if (UserCLK'event and UserCLK = '1') then
      if (EN = '1') then
        if (SR = '1') then
          lut_flop <= c_reset_value;
        else
          lut_flop <= lut_out;
        end if;
      end if;
    end if;

  end process process_001;

end architecture behavioral;
