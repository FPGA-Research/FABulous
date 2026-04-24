package attr_pack_ram_io_inpass4_frame_config_mux is

  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute I0_reg      : integer;
  attribute I1_reg      : integer;
  attribute I2_reg      : integer;
  attribute I3_reg      : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;

end package attr_pack_ram_io_inpass4_frame_config_mux;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_ram_io_inpass4_frame_config_mux.all;

-- InPassFlop2 and OutPassFlop2 differ only in which side I0/I1 or O0/O1
-- connects to the top entity.
-- (* FABulous, BelMap, I0_reg=0, I1_reg=1, I2_reg=2, I3_reg=3 *)

entity inpass4_frame_config_mux is
  generic (
    NoConfigBits : integer := 4 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (
    -- Pin0
    I : in    std_logic_vector(3 downto 0); -- (* FABulous, EXTERNAL *)
    O : out   std_logic_vector(3 downto 0);
    -- Tile IO ports from BELs
    UserCLK : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in    std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
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
end entity inpass4_frame_config_mux;

architecture behavioral of inpass4_frame_config_mux is

  --              ______   ______
  --    I----+--->|FLOP|-Q-|1 M |
  --         |             |  U |-------> O
  --         +-------------|0 X |

  -- I am instantiating an IOBUF primitive.
  -- Corresponding pins can connect all the way to top by adding
  -- an "-- EXTERNAL" comment (see PAD in the entity).

  signal Q : std_logic_vector(3 downto 0); -- FLOPs

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      S  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

begin

  process_001 : process (UserCLK) is
  begin

    if (UserCLK'event and UserCLK = '1') then
      Q <= I;
    end if;

  end process process_001;

  cus_mux21_inst0 : component cus_mux21
    port map (
      a0 => I(0),
      a1 => Q(0),
      S  => ConfigBits(0),
      x  => O(0)
    );

  cus_mux21_inst1 : component cus_mux21
    port map (
      a0 => I(1),
      a1 => Q(1),
      S  => ConfigBits(1),
      x  => O(1)
    );

  cus_mux21_inst2 : component cus_mux21
    port map (
      a0 => I(2),
      a1 => Q(2),
      S  => ConfigBits(2),
      x  => O(2)
    );

  cus_mux21_inst3 : component cus_mux21
    port map (
      a0 => I(3),
      a1 => Q(3),
      S  => ConfigBits(3),
      x  => O(3)
    );

end architecture behavioral;
