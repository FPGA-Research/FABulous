-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;


entity Frame_Data_Reg is
  generic (
    RowSelectWidth : integer := 5;
    FrameBitsPerRow : integer := 32;
    Row : integer := 1
  );
  port (
    CLK : in std_logic;
    FrameData_I : in std_logic_vector(FrameBitsPerRow-1 downto 0);
    FrameData_O : out std_logic_vector(FrameBitsPerRow-1 downto 0);
    RowSelect : in std_logic_vector(RowSelectWidth-1 downto 0)
  );
end entity; 


architecture from_verilog of Frame_Data_Reg is
  signal FrameData_O_Reg : std_logic_vector(31 downto 0);
begin
  FrameData_O <= FrameData_O_Reg;
  
  -- Generated from always process in Frame_Data_Reg (Frame_Data_Reg_template.v:10)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if to_integer(unsigned(RowSelect)) = Row then
        FrameData_O_Reg <= FrameData_I;
      end if;
    end if;
  end process;
end architecture;

