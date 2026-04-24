package attr_pack_regfile_regfile_32x4 is

  attribute fabulous    : string;
  attribute belmap      : string;
  attribute ad_reg      : integer;
  attribute bd_reg      : integer;
  attribute external    : string;
  attribute shared_port : string;
  attribute global      : string;

end package attr_pack_regfile_regfile_32x4;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_regfile_regfile_32x4.all;

-- (* FABulous, BelMap, AD_reg=0, BD_reg=1 *)

entity regfile_32x4 is
  generic (
    noconfigbits : integer := 2 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (                                        -- IMPORTANT: this has to be in a dedicated line
    d     : in    std_logic_vector(3 downto 0); -- Register File write port
    w_adr : in    std_logic_vector(4 downto 0); -- Register File write address
    w_en  : in    std_logic;

    ad    : out   std_logic_vector(3 downto 0); -- Register File read port A
    a_adr : in    std_logic_vector(4 downto 0); -- Register File read address A
    bd    : out   std_logic_vector(3 downto 0); -- Register File read port B
    b_adr : in    std_logic_vector(4 downto 0); -- Register File read address B

    userclk : in    std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    configbits : in    std_logic_vector(noconfigbits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );

  attribute fabulous of RegFile_32x4 : entity is "TRUE";
  attribute belmap of RegFile_32x4   : entity is "TRUE";
  attribute ad_reg of RegFile_32x4   : entity is 0;
  attribute bd_reg of RegFile_32x4   : entity is 1;
  attribute external of UserCLK      : signal is "TRUE";
  attribute shared_port of UserCLK   : signal is "TRUE";
  attribute global of ConfigBits     : signal is "TRUE";
end entity regfile_32x4;

architecture behavioral of regfile_32x4 is

  type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); -- 32 entries of 4 bit

  signal mem : memtype;

  signal ad_reg    : std_logic_vector(3 downto 0); -- port A read data register
  signal bd_reg    : std_logic_vector(3 downto 0); -- port B read data register
  signal ad_signal : std_logic_vector(3 downto 0); -- port A read data signal
  signal bd_signal : std_logic_vector(3 downto 0); -- port B read data signal

begin

  p_write : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      if (w_en = '1') then
        mem(TO_INTEGER(UNSIGNED(w_adr))) <= d;
      end if;
    end if;

  end process p_write;

  ad_signal <= mem(TO_INTEGER(UNSIGNED(a_adr)));
  bd_signal <= mem(TO_INTEGER(UNSIGNED(b_adr)));

  process_001 : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      ad_reg <= ad_signal;
      bd_reg <= bd_signal;
    end if;

  end process process_001;

  ad <= ad_signal when (configbits(0) = '0') else
        ad_reg;
  bd <= bd_signal when (configbits(1) = '0') else
        bd_reg;

end architecture behavioral;
