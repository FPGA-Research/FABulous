package attr_pack_LUT4AB_LUT4c_frame_config_dffesr is
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
end package;
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack_LUT4AB_LUT4c_frame_config_dffesr.all;

-- (* FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2, INIT_3=3, INIT_4=4, INIT_5=5, INIT_6=6, INIT_7=7, INIT_8=8, INIT_9=9, INIT_10=10, INIT_11=11,INIT_12=12, INIT_13=13, INIT_14=14, INIT_15=15, FAB_ATTR_FF=16, IOmux=17, SET_NORESET=18 *)

entity LUT4c_frame_config_dffesr is
  generic (NoConfigBits : integer := 19); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (-- IMPORTANT: this has to be in a dedicated line
    I  : in std_logic_vector(3 downto 0); -- LUT inputs
    O  : out std_logic; -- LUT output (combinatorial or FF)
    Ci : in std_logic; -- carry chain input
    Co : out std_logic; -- carry chain output
    SR : in std_logic; -- (* FABulous, SHARED_RESET *)
    EN : in std_logic; -- (* FABulous, SHARED_ENABLE *)
    -- ## the EXTERNAL keyword will send this sisgnal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    UserCLK : in std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0)
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
end entity LUT4c_frame_config_dffesr;

architecture Behavioral of LUT4c_frame_config_dffesr is

  constant LUT_SIZE    : integer := 4;
  constant N_LUT_flops : integer := 2 ** LUT_SIZE;
  signal LUT_values    : std_logic_vector(N_LUT_flops - 1 downto 0);

  signal LUT_index    : unsigned(LUT_SIZE - 1 downto 0);
  signal LUT_index_0N : std_logic;
  signal LUT_index_1N : std_logic;
  signal LUT_index_2N : std_logic;
  signal LUT_index_3N : std_logic;

  signal LUT_out                           : std_logic;
  signal LUT_flop                          : std_logic;
  signal I0mux                             : std_logic; -- normal input '0', or carry input '1'
  signal c_out_mux, c_I0mux, c_reset_value : std_logic; -- extra configuration bits

begin

  LUT_values    <= ConfigBits(15 downto 0);
  c_out_mux     <= ConfigBits(16);
  c_I0mux       <= ConfigBits(17);
  c_reset_value <= ConfigBits(18);

  --CONFout <= c_I0mux;

  -- I0mux <= I(0) when (c_I0mux = '0') else
  --   Ci;

  inst_cus_mux21_I0mux : entity work.cus_mux21
  port map
  (
    A0 => I(0),
    A1 => Ci,
    S  => c_I0mux,
    X  => I0mux
  );
  LUT_index <= I(3) & I(2) & I(1) & I0mux;

  -- The LUT is just a multiplexer
  -- for a first shot, I am using a 16:1
  -- LUT_out <= LUT_values(TO_INTEGER(LUT_index));
  LUT_index_0N <= not LUT_index(0);
  LUT_index_1N <= not LUT_index(1);
  LUT_index_2N <= not LUT_index(2);
  LUT_index_3N <= not LUT_index(3);

  inst_cus_mux161_buf : entity work.cus_mux161_buf
  port map
  (
    A0  => LUT_values(0),
    A1  => LUT_values(1),
    A2  => LUT_values(2),
    A3  => LUT_values(3),
    A4  => LUT_values(4),
    A5  => LUT_values(5),
    A6  => LUT_values(6),
    A7  => LUT_values(7),
    A8  => LUT_values(8),
    A9  => LUT_values(9),
    A10 => LUT_values(10),
    A11 => LUT_values(11),
    A12 => LUT_values(12),
    A13 => LUT_values(13),
    A14 => LUT_values(14),
    A15 => LUT_values(15),
    S0  => LUT_index(0),
    S0N => LUT_index_0N,
    S1  => LUT_index(1),
    S1N => LUT_index_1N,
    S2  => LUT_index(2),
    S2N => LUT_index_2N,
    S3  => LUT_index(3),
    S3N => LUT_index_3N,
    X   => LUT_out);

  cus_mux21_O : entity work.cus_mux21
  port map
  (
    A0 => LUT_out,
    A1 => LUT_flop,
    S  => c_out_mux,
    X  => O
  );

  -- iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT
  Co <= (Ci and I(1)) or (Ci and I(2)) or (I(1) and I(2));

  process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      if EN = '1' then
        if SR = '1' then
          LUT_flop <= c_reset_value;
        else
          LUT_flop <= LUT_out;
        end if;
      end if;
    end if;
  end process;
end architecture Behavioral;
