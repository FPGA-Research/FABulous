-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module top (counter.v:1)
entity top is
  port (
    clk : in std_logic;
    io_in : in unsigned(27 downto 0);
    io_oeb : out unsigned(27 downto 0);
    io_out : out unsigned(27 downto 0)
  );
end entity; 

-- Generated from Verilog module top (counter.v:1)
architecture from_verilog of top is
  signal tmp_ivl_2 : unsigned(9 downto 0);  -- Temporary created at counter.v:11
  signal tmp_ivl_4 : std_logic;  -- Temporary created at counter.v:11
  signal ctr : unsigned(15 downto 0);  -- Declared at counter.v:3
  signal rst : std_logic;  -- Declared at counter.v:2
begin
  rst <= io_in(0);
  io_out <= tmp_ivl_2 & ctr & rst & tmp_ivl_4;
  tmp_ivl_2 <= "0000000000";
  tmp_ivl_4 <= '0';
  io_oeb <= X"0000001";
  
  -- Generated from always process in top (counter.v:5)
  process (clk) is
  begin
    if rising_edge(clk) then
      if rst = '1' then
        ctr <= X"0000";
      else
        ctr <= ctr + X"0001";
      end if;
    end if;
  end process;
end architecture;

