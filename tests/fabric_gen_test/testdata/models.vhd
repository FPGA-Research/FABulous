library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package my_package is

component LHQD1 is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end component;

end package;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity LHQD1 is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end entity;

architecture from_verilog of LHQD1 is
begin
  process (E, D) is
  begin
    if E = '1' then
      Q <= D;
      QN <= not D;
    end if;
  end process;
end architecture;