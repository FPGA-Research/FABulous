library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

package my_package is

  component config_latch is
    port (
      D  : in    std_logic;
      E  : in    std_logic;
      Q  : out   std_logic;
      QN : out   std_logic
    );
  end component config_latch;

end package my_package;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_latch is
  port (
    D  : in    std_logic;
    E  : in    std_logic;
    Q  : out   std_logic;
    QN : out   std_logic
  );
end entity config_latch;

architecture from_verilog of config_latch is

begin

  process (E, D) is
  begin

    if (E = '1') then
      Q  <= D;
      QN <= not D;
    end if;

  end process;

end architecture from_verilog;
