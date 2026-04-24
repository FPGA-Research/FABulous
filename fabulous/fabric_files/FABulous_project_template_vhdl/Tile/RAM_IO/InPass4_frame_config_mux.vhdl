package attr_pack_ram_io_inpass4_frame_config_mux is

  attribute fabulous    : string;
  attribute belmap      : string;
  attribute i0_reg      : integer;
  attribute i1_reg      : integer;
  attribute i2_reg      : integer;
  attribute i3_reg      : integer;
  attribute external    : string;
  attribute shared_port : string;
  attribute global      : string;

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
    noconfigbits : integer := 4 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (
    -- Pin0
    i : in    std_logic_vector(3 downto 0); -- (* FABulous, EXTERNAL *)
    o : out   std_logic_vector(3 downto 0);
    -- Tile IO ports from BELs
    userclk : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    configbits : in    std_logic_vector(noconfigbits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );

  attribute fabulous of InPass4_frame_config_mux : entity is "TRUE";
  attribute belmap of InPass4_frame_config_mux   : entity is "TRUE";
  attribute i0_reg of InPass4_frame_config_mux   : entity is 0;
  attribute i1_reg of InPass4_frame_config_mux   : entity is 1;
  attribute i2_reg of InPass4_frame_config_mux   : entity is 2;
  attribute i3_reg of InPass4_frame_config_mux   : entity is 3;
  attribute external of I                        : signal is "TRUE";
  attribute external of UserCLK                  : signal is "TRUE";
  attribute shared_port of UserCLK               : signal is "TRUE";
  attribute global of ConfigBits                 : signal is "TRUE";
end entity inpass4_frame_config_mux;

architecture behavioral of inpass4_frame_config_mux is

  --              ______   ______
  --    I----+--->|FLOP|-Q-|1 M |
  --         |             |  U |-------> O
  --         +-------------|0 X |

  -- I am instantiating an IOBUF primitive.
  -- Corresponding pins can connect all the way to top by adding
  -- an "-- EXTERNAL" comment (see PAD in the entity).

  signal q : std_logic_vector(3 downto 0); -- FLOPs

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      s  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

begin

  process_001 : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      q <= i;
    end if;

  end process process_001;

  cus_mux21_inst0 : component cus_mux21
    port map (
      a0 => i(0),
      a1 => q(0),
      s  => configbits(0),
      x  => o(0)
    );

  cus_mux21_inst1 : component cus_mux21
    port map (
      a0 => i(1),
      a1 => q(1),
      s  => configbits(1),
      x  => o(1)
    );

  cus_mux21_inst2 : component cus_mux21
    port map (
      a0 => i(2),
      a1 => q(2),
      s  => configbits(2),
      x  => o(2)
    );

  cus_mux21_inst3 : component cus_mux21
    port map (
      a0 => i(3),
      a1 => q(3),
      s  => configbits(3),
      x  => o(3)
    );

end architecture behavioral;
