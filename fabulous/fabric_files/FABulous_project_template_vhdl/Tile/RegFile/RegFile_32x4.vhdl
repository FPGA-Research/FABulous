package attr_pack_regfile_regfile_32x4 is

  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute AD_reg      : integer;
  attribute BD_reg      : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;

end package attr_pack_regfile_regfile_32x4;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_regfile_regfile_32x4.all;

-- (* FABulous, BelMap, AD_reg=0, BD_reg=1 *)

entity regfile_32x4 is
  generic (
    NoConfigBits : integer := 2 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (                                        -- IMPORTANT: this has to be in a dedicated line
    D     : in    std_logic_vector(3 downto 0); -- Register File write port
    W_ADR : in    std_logic_vector(4 downto 0); -- Register File write address
    W_en  : in    std_logic;

    AD    : out   std_logic_vector(3 downto 0); -- Register File read port A
    A_ADR : in    std_logic_vector(4 downto 0); -- Register File read address A
    BD    : out   std_logic_vector(3 downto 0); -- Register File read port B
    B_ADR : in    std_logic_vector(4 downto 0); -- Register File read address B

    UserCLK : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in    std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );

  attribute FABulous of RegFile_32x4 : entity is "TRUE";
  attribute BelMap of RegFile_32x4   : entity is "TRUE";
  attribute AD_reg of RegFile_32x4   : entity is 0;
  attribute BD_reg of RegFile_32x4   : entity is 1;
  attribute EXTERNAL of UserCLK      : signal is "TRUE";
  attribute SHARED_PORT of UserCLK   : signal is "TRUE";
  attribute GLOBAL of ConfigBits     : signal is "TRUE";
end entity regfile_32x4;

architecture behavioral of regfile_32x4 is

  type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); -- 32 entries of 4 bit

  signal mem : memtype;

  signal ad_reg    : std_logic_vector(3 downto 0); -- port A read data register
  signal bd_reg    : std_logic_vector(3 downto 0); -- port B read data register
  signal ad_signal : std_logic_vector(3 downto 0); -- port A read data signal
  signal bd_signal : std_logic_vector(3 downto 0); -- port B read data signal

begin

  p_write : process (UserCLK) is
  begin

    if (UserCLK'event and UserCLK = '1') then
      if (W_en = '1') then
        mem(TO_INTEGER(UNSIGNED(W_ADR))) <= D;
      end if;
    end if;

  end process p_write;

  ad_signal <= mem(TO_INTEGER(UNSIGNED(A_ADR)));
  bd_signal <= mem(TO_INTEGER(UNSIGNED(B_ADR)));

  process_001 : process (UserCLK) is
  begin

    if (UserCLK'event and UserCLK = '1') then
      ad_reg <= ad_signal;
      bd_reg <= bd_signal;
    end if;

  end process process_001;

  AD <= ad_signal when (ConfigBits(0) = '0') else
        ad_reg;
  BD <= bd_signal when (ConfigBits(1) = '0') else
        bd_reg;

end architecture behavioral;
