package attr_pack_W_IO_IO_1_bidirectional_frame_config_pass is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack_W_IO_IO_1_bidirectional_frame_config_pass.all;
-- Library UNISIM;
-- use UNISIM.vcomponents.all;
entity IO_1_bidirectional_frame_config_pass is
  -- Generic ( NoConfigBits : integer := 0 ); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (
    -- Pin0
    I     : in std_logic; -- from fabric to external pin
    T     : in std_logic; -- tristate control
    O     : out std_logic; -- from external pin to fabric
    Q     : out std_logic; -- from external pin to fabric (registered)
    I_top : out std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    T_top : out std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    O_top : in std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    -- Tile IO ports from BELs
    UserCLK : in std_logic -- (* FABulous, EXTERNAL, SHARED_PORT *) -- ## the EXTERNAL keyword will send this signal all the way to top and the --SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    -- ConfigBits : in   STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
  );
  attribute FABulous of IO_1_bidirectional_frame_config_pass : entity is "TRUE";
  attribute BelMap of IO_1_bidirectional_frame_config_pass   : entity is "TRUE";
  attribute EXTERNAL of UserCLK                              : signal is "TRUE"; -- EXTERNAL has to ge
  attribute SHARED_PORT of UserCLK                           : signal is "TRUE"; -- SHARED_PORT allows multiple BELs using the same port (e.g. for exporting a clock to the top)
end entity IO_1_bidirectional_frame_config_pass;

architecture Behavioral of IO_1_bidirectional_frame_config_pass is

  --                        _____
  --    I-----T_DRIVER----->|PAD|--+-------> O
  --              |         -----  |
  --    T---------+                +-->FF--> Q

  -- I am instantiating an IOBUF primitive.
  -- However, it is possible to connect corresponding pins all the way to top, just by adding an "-- EXTERNAL" comment (see PAD in the entity)

  -- signal fromPad : std_logic;

begin

  -- Slice outputs
  O <= O_top;

  process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      Q <= O_top;
    end if;
  end process;

  I_top <= I;
  T_top <= not T;

  -- IOBUF_inst0 : IOBUF
  -- port map (
  -- O => fromPad, -- 1-bit output: Buffer output
  -- I => I, -- 1-bit input: Buffer input
  -- IO => PAD, -- 1-bit inout: Buffer inout (connect directly to top-level port)
  -- T => T -- 1-bit input: 3-state enable input
  -- );

end architecture Behavioral;
