-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;


entity Frame_Select is
  generic (
    FrameSelectWidth : integer := 5;
    MaxFramesPerCol : integer := 20;
    Col : integer := 18
  );
  port (
    FrameSelect : in std_logic_vector(FrameSelectWidth-1 downto 0);
    FrameStrobe : in std_logic;
    FrameStrobe_I : in std_logic_vector(MaxFramesPerCol-1 downto 0);
    FrameStrobe_O : out std_logic_vector(MaxFramesPerCol-1 downto 0)
  );
end entity; 


architecture from_verilog of Frame_Select is
  signal FrameStrobe_O_Reg : std_logic_vector(19 downto 0);
begin
  FrameStrobe_O <= FrameStrobe_O_Reg;
  
  -- Generated from always process in Frame_Select (Frame_Select_template.v:11)
  process (FrameStrobe, FrameSelect, FrameStrobe_I) is
  begin
    if (FrameStrobe = '1') and to_integer(unsigned(FrameSelect)) = Col then
      FrameStrobe_O_Reg <= FrameStrobe_I;
    else
      FrameStrobe_O_Reg <= X"00000";
    end if;
  end process;
end architecture;

