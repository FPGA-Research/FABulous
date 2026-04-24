-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module Frame_Select (Frame_Select.v:1)
--   Col = 18
--   FrameSelectWidth = 5
--   MaxFramesPerCol = 20

entity frame_select is
  generic (
    frameselectwidth : integer := 5;
    maxframespercol  : integer := 20;
    col              : integer := 18
  );
  port (
    frameselect   : in    std_logic_vector(frameselectwidth - 1 downto 0);
    framestrobe   : in    std_logic;
    framestrobe_i : in    std_logic_vector(maxframespercol - 1 downto 0);
    framestrobe_o : out   std_logic_vector(maxframespercol - 1 downto 0)
  );
end entity frame_select;

-- Generated from Verilog module Frame_Select (Frame_Select.v:1)
--   Col = 18
--   FrameSelectWidth = 5
--   MaxFramesPerCol = 20

architecture from_verilog of frame_select is

  signal framestrobe_o_reg : std_logic_vector(maxframespercol - 1 downto 0);

begin

  framestrobe_o <= framestrobe_o_reg;

  -- Generated from always process in Frame_Select (Frame_Select.v:11)
  process_001 : process (framestrobe, frameselect, framestrobe_i) is
  begin

    if ((framestrobe = '1') and to_integer(unsigned(frameselect)) = col) then
      framestrobe_o_reg <= framestrobe_i;
    else
      framestrobe_o_reg <= (others => '0');
    end if;

  end process process_001;

end architecture from_verilog;
