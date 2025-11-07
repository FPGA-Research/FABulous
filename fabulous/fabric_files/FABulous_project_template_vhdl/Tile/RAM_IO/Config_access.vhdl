package attr_pack_RAM_IO_Config_access is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute C_bit0      : integer;
  attribute C_bit1      : integer;
  attribute C_bit2      : integer;
  attribute C_bit3      : integer;
  attribute EXTERNAL    : string;
  attribute GLOBAL      : string;
end package;
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use work.attr_pack_RAM_IO_Config_access.all;

-- (* FABulous, BelMap, C_bit0=0, C_bit1=1, C_bit2=2, C_bit3=3 *)
entity Config_access is
  generic (NoConfigBits : integer := 4); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (
    -- Pin0
    C : out std_logic_vector(3 downto 0); -- (* FABulous, EXTERNAL *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );
  attribute FABulous of Config_access : entity is "TRUE";
  attribute BelMap of Config_access   : entity is "TRUE";
  attribute C_bit0 of Config_access   : entity is 0;
  attribute C_bit1 of Config_access   : entity is 1;
  attribute C_bit2 of Config_access   : entity is 2;
  attribute C_bit3 of Config_access   : entity is 3;
  attribute EXTERNAL of C             : signal is "TRUE";
  attribute GLOBAL of ConfigBits      : signal is "TRUE";
end entity Config_access;

architecture Behavioral of Config_access is

begin

  -- we just wire configuration bits to fabric top
  C(0) <= ConfigBits(0);
  C(1) <= ConfigBits(1);
  C(2) <= ConfigBits(2);
  C(3) <= ConfigBits(3);

end architecture Behavioral;
