package attr_pack_w_io_io_1_bidirectional_frame_config_pass is

  attribute fabulous    : string;
  attribute belmap      : string;
  attribute external    : string;
  attribute shared_port : string;
  attribute global      : string;

end package attr_pack_w_io_io_1_bidirectional_frame_config_pass;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_w_io_io_1_bidirectional_frame_config_pass.all;
-- Library UNISIM;
-- use UNISIM.vcomponents.all;

entity io_1_bidirectional_frame_config_pass is
  -- Generic ( NoConfigBits : integer := 0 );
  -- NoConfigBits has to be adjusted manually.
  port (
    -- Pin0
    i     : in    std_logic; -- from fabric to external pin
    t     : in    std_logic; -- tristate control
    o     : out   std_logic; -- from external pin to fabric
    q     : out   std_logic; -- from external pin to fabric (registered)
    i_top : out   std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    t_top : out   std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    o_top : in    std_logic; -- (* FABulous, EXTERNAL *) has to ge to top-level entity not the switch matrix
    -- Tile IO ports from BELs
    userclk : in    std_logic -- (* FABulous, EXTERNAL, SHARED_PORT *)
  -- EXTERNAL sends this signal all the way to top.
  -- SHARED allows multiple BELs to use the same port.
  -- GLOBAL pins connected to the switch matrix must precede the GLOBAL label.
  -- ConfigBits : in   STD_LOGIC_VECTOR( NoConfigBits -1 downto 0 )
  );
  attribute fabulous of IO_1_bidirectional_frame_config_pass : entity is "TRUE";
  attribute belmap of IO_1_bidirectional_frame_config_pass   : entity is "TRUE";
  attribute external of UserCLK                              : signal is "TRUE"; -- EXTERNAL has to ge
  attribute shared_port of UserCLK                           : signal is "TRUE";
end entity io_1_bidirectional_frame_config_pass;

architecture behavioral of io_1_bidirectional_frame_config_pass is

--                        _____
--    I-----T_DRIVER----->|PAD|--+-------> O
--              |         -----  |
--    T---------+                +-->FF--> Q

-- I am instantiating an IOBUF primitive.
-- Corresponding pins can connect all the way to top by adding
-- an "-- EXTERNAL" comment (see PAD in the entity).

begin

  -- Slice outputs
  o <= o_top;

  process_001 : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      q <= o_top;
    end if;

  end process process_001;

  i_top <= i;
  t_top <= not t;

-- IOBUF_inst0 : IOBUF
-- port map (
-- O => fromPad, -- 1-bit output: Buffer output
-- I => I, -- 1-bit input: Buffer input
-- IO => PAD, -- 1-bit inout: Buffer inout (connect directly to top-level port)
-- T => T -- 1-bit input: 3-state enable input
-- );

end architecture behavioral;
