-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module top (./right_shift.v:3)
entity top is
  port (
    clk : in std_logic;
    io_in : in unsigned(27 downto 0);
    io_oeb : out unsigned(27 downto 0);
    io_out : out unsigned(27 downto 0)
  );
end entity; 

-- Generated from Verilog module top (./right_shift.v:3)
architecture from_verilog of top is
  signal tmp_ivl_5 : unsigned(13 downto 0);  -- Temporary created at ./right_shift.v:23
  signal tmp_ivl_7 : unsigned(13 downto 0);  -- Temporary created at ./right_shift.v:23
  signal counter : unsigned(13 downto 0);  -- Declared at ./right_shift.v:6
  signal data_in : unsigned(649 downto 0);  -- Declared at ./right_shift.v:5
  signal rst : std_logic;  -- Declared at ./right_shift.v:4
begin
  rst <= io_in(0);
  tmp_ivl_5 <= data_in(636 + 13 downto 636);
  tmp_ivl_7 <= data_in(0 + 13 downto 0);
  io_out <= tmp_ivl_5 & tmp_ivl_7;
  io_oeb <= X"0000001";
  
  -- Generated from always process in top (./right_shift.v:8)
  process (clk) is
  begin
    if rising_edge(clk) then
      if rst = '1' then
        counter <= "00000000000000";
        data_in <= "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000";
      else
        data_in <= Resize(counter & data_in(13 + 636 downto 13), 650);
        counter <= counter + "00000000000001";
      end if;
    end if;
  end process;
end architecture;

