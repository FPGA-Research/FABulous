-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module Frame_Data_Reg (Frame_Data_Reg.v:1)
--   FrameBitsPerRow = 32
--   Row = 1
--   RowSelectWidth = 5

entity frame_data_reg is
  generic (
    rowselectwidth  : integer := 5;
    framebitsperrow : integer := 32;
    row             : integer := 1
  );
  port (
    clk         : in    std_logic;
    framedata_i : in    std_logic_vector(framebitsperrow - 1 downto 0);
    framedata_o : out   std_logic_vector(framebitsperrow - 1 downto 0);
    rowselect   : in    std_logic_vector(rowselectwidth - 1 downto 0)
  );
end entity frame_data_reg;

-- Generated from Verilog module Frame_Data_Reg (Frame_Data_Reg.v:1)
--   FrameBitsPerRow = 32
--   Row = 1
--   RowSelectWidth = 5

architecture from_verilog of frame_data_reg is

  signal framedata_o_reg : std_logic_vector(31 downto 0);

begin

  framedata_o <= framedata_o_reg;

  -- Generated from always process in Frame_Data_Reg (Frame_Data_Reg.v:10)
  process_001 : process (clk) is
  begin

    if rising_edge(clk) then
      if (to_integer(unsigned(rowselect)) = row) then
        framedata_o_reg <= framedata_i;
      end if;
    end if;

  end process process_001;

end architecture from_verilog;
