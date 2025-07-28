package attr_pack is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute I0_reg      : integer;
  attribute I1_reg      : integer;
  attribute I2_reg      : integer;
  attribute I3_reg      : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.my_package.all;
use work.attr_pack.all;

-- InPassFlop2 and OutPassFlop2 are the same except for changing which side I0,I1 or O0,O1 gets connected to the top entity
entity InPass4_frame_config_mux is
  generic (NoConfigBits : integer := 4); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (
    -- Pin0
    I : in std_logic_vector(3 downto 0); -- EXTERNAL
    O : out std_logic_vector(3 downto 0);
    -- Tile IO ports from BELs
    UserCLK : in std_logic;
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0)
  );

  attribute FABulous of InPass4_frame_config_mux : entity is "TRUE";
  attribute BelMap of InPass4_frame_config_mux   : entity is "TRUE";
  attribute I0_reg of InPass4_frame_config_mux   : entity is 0;
  attribute I1_reg of InPass4_frame_config_mux   : entity is 1;
  attribute I2_reg of InPass4_frame_config_mux   : entity is 2;
  attribute I3_reg of InPass4_frame_config_mux   : entity is 3;
  attribute EXTERNAL of I                        : signal is "TRUE";
  attribute EXTERNAL of UserCLK                  : signal is "TRUE";
  attribute SHARED_PORT of UserCLK               : signal is "TRUE";
  attribute GLOBAL of ConfigBits                 : signal is "TRUE";
end entity InPass4_frame_config_mux;

architecture Behavioral of InPass4_frame_config_mux is

  --              ______   ______
  --    I----+--->|FLOP|-Q-|1 M |
  --         |             |  U |-------> O
  --         +-------------|0 X |

  -- I am instantiating an IOBUF primitive.
  -- However, it is possible to connect corresponding pins all the way to top, just by adding an "-- EXTERNAL" comment (see PAD in the entity)

  signal Q0, Q1, Q2, Q3 : std_logic; -- FLOPs

  component cus_mux21 is
    port (
      A0 : in std_logic;
      A1 : in std_logic;
      S  : in std_logic;
      X  : out std_logic
    );
  end component;

begin

  process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      Q0 <= I(0);
      Q1 <= I(1);
      Q2 <= I(2);
      Q3 <= I(3);
    end if;
  end process;

  -- O(0) <= I(0) when ConfigBits(0) = '0' else Q0;
  -- O(1) <= I(1) when ConfigBits(1) = '0' else Q1;
  -- O(2) <= I(2) when ConfigBits(2) = '0' else Q2;
  -- O(3) <= I(3) when ConfigBits(3) = '0' else Q3;

  cus_mux21 : cus_mux21_inst0
  port map
  (
    A0 => I(0),
    A1 => Q0,
    S  => ConfigBits(0),
    X  => O(0)
  );

  cus_mux21_1 : cus_mux21_inst1
  port map
  (
    A0 => I(1),
    A1 => Q1,
    S  => ConfigBits(1),
    X  => O(1)
  );

  cus_mux21_2 : cus_mux21_inst2

  port map
  (
    A0 => I(2),
    A1 => Q2,
    S  => ConfigBits(2),
    X  => O(2)
  );

  cus_mux21_3 : cus_mux21_inst3
  port map
  (
    A0 => I(3),
    A1 => Q3,
    S  => ConfigBits(3),
    X  => O(3)
  );

end architecture Behavioral;
