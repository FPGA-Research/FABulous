package attr_pack is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute AD_reg      : integer;
  attribute BD_reg      : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.my_package.all;
use work.attr_pack.all;

-- (* FABulous, BelMap, AD_reg=0, BD_reg=1 *)

entity RegFile_32x4 is
  generic (NoConfigBits : integer := 2); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (-- IMPORTANT: this has to be in a dedicated line
    D     : in std_logic_vector(3 downto 0); -- Register File write port
    W_ADR : in std_logic_vector(4 downto 0); -- Register File write address
    W_en  : in std_logic;

    AD    : out std_logic_vector (3 downto 0); -- Register File read port A
    A_ADR : in std_logic_vector(4 downto 0); -- Register File read address A
    BD    : out std_logic_vector (3 downto 0); -- Register File read port B
    B_ADR : in std_logic_vector(4 downto 0); -- Register File read address B

    UserCLK : in std_logic; -- EXTERNAL -- SHARED_PORT
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0)
  );

  attribute FABulous of RegFile_32x4 : entity is "TRUE";
  attribute BelMap of RegFile_32x4   : entity is "TRUE";
  attribute AD_reg of RegFile_32x4   : entity is 0;
  attribute BD_reg of RegFile_32x4   : entity is 1;
  attribute EXTERNAL of UserCLK      : signal is "TRUE";
  attribute SHARED_PORT of UserCLK   : signal is "TRUE";
  attribute GLOBAL of ConfigBits     : signal is "TRUE";
end entity RegFile_32x4;

architecture Behavioral of RegFile_32x4 is

  type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); -- 32 entries of 4 bit
  signal mem : memtype := (others => (others => '0'));

  signal W_ADR : std_logic_vector(4 downto 0); -- write address
  signal A_ADR : std_logic_vector(4 downto 0); -- port A read address
  signal B_ADR : std_logic_vector(4 downto 0); -- port B read address

  signal D  : std_logic_vector(3 downto 0); -- write data
  signal AD : std_logic_vector(3 downto 0); -- port A read data
  signal BD : std_logic_vector(3 downto 0); -- port B read data

  signal AD_reg : std_logic_vector(3 downto 0); -- port A read data register
  signal BD_reg : std_logic_vector(3 downto 0); -- port B read data register
begin

  W_ADR <= W_ADR4 & W_ADR3 & W_ADR2 & W_ADR1 & W_ADR0;
  A_ADR <= A_ADR4 & A_ADR3 & A_ADR2 & A_ADR1 & A_ADR0;
  B_ADR <= B_ADR4 & B_ADR3 & B_ADR2 & B_ADR1 & B_ADR0;

  D <= D3 & D2 & D1 & D0;

  P_write : process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      if W_en = '1' then
        mem(TO_INTEGER(UNSIGNED(W_ADR))) <= D;
      end if;
    end if;
  end process;

  AD <= mem(TO_INTEGER(UNSIGNED(A_ADR)));
  BD <= mem(TO_INTEGER(UNSIGNED(B_ADR)));

  process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      AD_reg <= AD;
      BD_reg <= BD;
    end if;
  end process;

  AD <= AD when (ConfigBits(0) = '0') else
    AD_reg;
  BD <= BD when (ConfigBits(1) = '0') else
    BD_reg;

end architecture Behavioral;
