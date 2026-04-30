library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

package my_package is

  component config_latch is
    port (
      d  : in    std_logic;
      e  : in    std_logic;
      q  : out   std_logic;
      qn : out   std_logic
    );
  end component config_latch;

end package my_package;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_latch is
  port (
    d  : in    std_logic;
    e  : in    std_logic;
    q  : out   std_logic;
    qn : out   std_logic
  );
end entity config_latch;

architecture from_verilog of config_latch is

begin

  process_001 : process (e, d) is
  begin

    if (e = '1') then
      q  <= d;
      qn <= not d;
    end if;

  end process process_001;

end architecture from_verilog;
