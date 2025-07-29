package attr_pack is
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
  attribute FF_con      : integer;
  attribute IOmux       : integer;
  attribute SET_NORESET : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack.all;

-- (* FABulous, BelMap, INIT=0, INIT[1]=1, INIT[2]=2, INIT[3]=3, INIT[4]=4, INIT[5]=5, INIT[6]=6, INIT[7]=7, INIT[8]=8, INIT[9]=9, INIT[10]=10, INIT[11]=11,INIT[12]=12, INIT[13]=13, INIT[14]=14, INIT[15]=15, FF=16, IOmux=17, SET_NORESET=18 *)

entity LUT4c_frame_config_dffesr is
  generic (NoConfigBits : integer := 19); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (-- IMPORTANT: this has to be in a dedicated line
    I       : in std_logic_vector(3 downto 0); -- LUT inputs
    O       : out std_logic; -- LUT output (combinatorial or FF)
    Ci      : in std_logic; -- carry chain input
    Co      : out std_logic; -- carry chain output
    SR      : in std_logic; -- SHARED_RESET
    EN      : in std_logic; -- SHARED_ENABLE
    UserCLK : in std_logic; -- EXTERNAL -- SHARED_PORT -- ## the EXTERNAL keyword will send this sisgnal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
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
  attribute FF_con of LUT4c_frame_config_dffesr      : entity is 16;
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

  signal LUT_index : unsigned(LUT_SIZE - 1 downto 0);

  signal LUT_out                           : std_logic;
  signal LUT_flop                          : std_logic;
  signal I0mux                             : std_logic; -- normal input '0', or carry input '1'
  signal c_out_mux, c_I0mux, c_reset_value : std_logic; -- extra configuration bits

  component MUX16PTv2 is
    port (
      IN1  : in std_logic;
      IN10 : in std_logic;
      IN11 : in std_logic;
      IN12 : in std_logic;
      IN13 : in std_logic;
      IN14 : in std_logic;
      IN15 : in std_logic;
      IN16 : in std_logic;
      IN2  : in std_logic;
      IN3  : in std_logic;
      IN4  : in std_logic;
      IN5  : in std_logic;
      IN6  : in std_logic;
      IN7  : in std_logic;
      IN8  : in std_logic;
      IN9  : in std_logic;
      O    : out std_logic;
      S1   : in std_logic;
      S2   : in std_logic;
      S3   : in std_logic;
      S4   : in std_logic
    );
  end component MUX16PTv2;
begin

  LUT_values    <= ConfigBits(15 downto 0);
  c_out_mux     <= ConfigBits(16);
  c_I0mux       <= ConfigBits(17);
  c_reset_value <= ConfigBits(18);

  --CONFout <= c_I0mux;

  I0mux <= I(0) when (c_I0mux = '0') else
    Ci;
  LUT_index <= I(3) & I(2) & I(1) & I0mux;

  -- The LUT is just a multiplexer
  -- for a first shot, I am using a 16:1
  -- LUT_out <= LUT_values(TO_INTEGER(LUT_index));
  inst_MUX16PTv2_E6BEG1 : MUX16PTv2
  port map
  (
    IN1  => LUT_values(0),
    IN2  => LUT_values(1),
    IN3  => LUT_values(2),
    IN4  => LUT_values(3),
    IN5  => LUT_values(4),
    IN6  => LUT_values(5),
    IN7  => LUT_values(6),
    IN8  => LUT_values(7),
    IN9  => LUT_values(8),
    IN10 => LUT_values(9),
    IN11 => LUT_values(10),
    IN12 => LUT_values(11),
    IN13 => LUT_values(12),
    IN14 => LUT_values(13),
    IN15 => LUT_values(14),
    IN16 => LUT_values(15),
    S1   => LUT_index(0),
    S2   => LUT_index(1),
    S3   => LUT_index(2),
    S4   => LUT_index(3),
    O    => LUT_out);

  O <= LUT_flop when (c_out_mux = '1') else
    LUT_out;

  Co <= (Ci and I(1)) or (Ci and I(2)) or (I(1) and I(2)); -- iCE40 like carry chain (as this is supported in Josys; would normally go for fractured LUT

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
