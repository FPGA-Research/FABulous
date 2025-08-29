package attr_pack_RAM_IO_OutPass4_frame_config_mux is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute O0_reg      : integer;
  attribute O1_reg      : integer;
  attribute O2_reg      : integer;
  attribute O3_reg      : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack_RAM_IO_OutPass4_frame_config_mux.all;
-- InPassFlop2 and OutPassFlop2 are the same except for changing which side I0,I1 or O0,O1 gets connected to the top entity

-- (* FABulous, BelMap, I0_reg=0, I1_reg=1, I2_reg=2, I3_reg=3 *)
entity OutPass4_frame_config_mux is
  generic (NoConfigBits : integer := 4); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (
    -- Pin0
    I : in std_logic_vector(3 downto 0);
    O : out std_logic_vector(3 downto 0); -- (* FABulous, EXTERNAL *)
    -- Tile IO ports from BELs
    UserCLK : in std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );

  attribute FABulous of OutPass4_frame_config_mux : entity is "TRUE";
  attribute BelMap of OutPass4_frame_config_mux   : entity is "TRUE";
  attribute O0_reg of OutPass4_frame_config_mux   : entity is 0;
  attribute O1_reg of OutPass4_frame_config_mux   : entity is 1;
  attribute O2_reg of OutPass4_frame_config_mux   : entity is 2;
  attribute O3_reg of OutPass4_frame_config_mux   : entity is 3;
  attribute EXTERNAL of O                         : signal is "TRUE";
  attribute EXTERNAL of UserCLK                   : signal is "TRUE";
  attribute SHARED_PORT of UserCLK                : signal is "TRUE";
  attribute GLOBAL of ConfigBits                  : signal is "TRUE";
end entity OutPass4_frame_config_mux;

architecture Behavioral of OutPass4_frame_config_mux is

  --              ______   ______
  --    I----+--->|FLOP|-Q-|1 M |
  --         |             |  U |-------> O
  --         +-------------|0 X |
  -- I am instantiating an IOBUF primitive.
  -- However, it is possible to connect corresponding pins all the way to top, just by adding an "-- EXTERNAL" comment (see PAD in the entity)

  signal Q : std_logic_vector(3 downto 0); -- FLOPs
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
      Q <= I;
    end if;
  end process;

  -- O(0) <= I(0) when ConfigBits(0) = '0' else Q0;
  -- O(1) <= I(1) when ConfigBits(1) = '0' else Q1;
  -- O(2) <= I(2) when ConfigBits(2) = '0' else Q2;
  -- O(3) <= I(3) when ConfigBits(3) = '0' else Q3;

  cus_mux21_inst : cus_mux21
  port map
  (
    A0 => I(0),
    A1 => Q(0),
    S  => ConfigBits(0),
    X  => O(0)
  );

  cus_mux21_inst1 : cus_mux21
  port map
  (
    A0 => I(1),
    A1 => Q(1),
    S  => ConfigBits(1),
    X  => O(1)
  );
  cus_mux21_2_inst2 : cus_mux21
  port map
  (
    A0 => I(2),
    A1 => Q(2),
    S  => ConfigBits(2),
    X  => O(2)
  );
  cus_mux21_inst3 : cus_mux21
  port map
  (
    A0 => I(3),
    A1 => Q(3),
    S  => ConfigBits(3),
    X  => O(3)
  );
end architecture Behavioral;
