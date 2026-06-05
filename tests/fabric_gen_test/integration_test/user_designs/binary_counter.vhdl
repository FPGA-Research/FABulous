library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity binary_counter is
  port (
    clk   : in  std_logic;
    rst   : in  std_logic;
    count : out std_logic_vector(3 downto 0)
  );
end binary_counter;

architecture rtl of binary_counter is
  signal ctr : unsigned(3 downto 0);
begin
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        ctr <= (others => '0');
      else
        ctr <= ctr + 1;
      end if;
    end if;
  end process;
  count <= std_logic_vector(ctr);
end rtl;
