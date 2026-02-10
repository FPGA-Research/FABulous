package attr_pack_LUT4AB_MUX8LUT_frame_config_mux is
  attribute FABulous    : string;
  attribute BelMap      : string;
  attribute C0          : integer;
  attribute C1          : integer;
  attribute EXTERNAL    : string;
  attribute SHARED_PORT : string;
  attribute GLOBAL      : string;
end package;

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack_LUT4AB_MUX8LUT_frame_config_mux.all;

-- (* FABulous, BelMap, c0=0, c1=1 *)

entity MUX8LUT_frame_config_mux is
  generic (NoConfigBits : integer := 2); -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  port (-- IMPORTANT: this has to be in a dedicated line
    A    : in std_logic; -- MUX inputs
    B    : in std_logic;
    C    : in std_logic;
    D    : in std_logic;
    E    : in std_logic;
    F    : in std_logic;
    G    : in std_logic;
    H    : in std_logic;
    S    : in std_logic_vector(3 downto 0); -- MUX select lines
    M_AB : out std_logic;
    M_AD : out std_logic;
    M_AH : out std_logic;
    M_EF : out std_logic;
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)

  );
  attribute FABulous of MUX8LUT_frame_config_mux : entity is "TRUE";
  attribute BelMap of MUX8LUT_frame_config_mux   : entity is "TRUE";
  attribute c0 of MUX8LUT_frame_config_mux       : entity is 0;
  attribute c1 of MUX8LUT_frame_config_mux       : entity is 1;
  attribute GLOBAL of ConfigBits                 : signal is "TRUE";
end entity MUX8LUT_frame_config_mux;

architecture Behavioral of MUX8LUT_frame_config_mux is

  signal AB, CD, EF, GH     : std_logic;
  signal sCD, sEF, sGH, sEH : std_logic;
  signal AD, EH, AH         : std_logic;
  signal EH_GH              : std_logic;

  signal c0, c1 : std_logic; -- configuration bits

begin

  c0 <= ConfigBits(0);
  c1 <= ConfigBits(1);

  -- see figure (column-wise left-to-right)

  --AB <= A when (S(0) = '0') else B;
  cus_mux21_AB : entity work.cus_mux21
  port map
  (
    A0 => A,
    A1 => B,
    S  => S(0),
    X  => AB
  );

  --CD <= C when (sCD = '0') else D;
  cus_mux21_CD : entity work.cus_mux21
  port map
  (
    A0 => C,
    A1 => D,
    S  => sCD,
    X  => CD
  );

  --EF <= E when (sEF = '0') else F;
  cus_mux21_EF : entity work.cus_mux21
  port map
  (
    A0 => E,
    A1 => F,
    S  => sEF,
    X  => EF
  );

  --GH <= G when (sGH = '0') else H;
  cus_mux21_GH : entity work.cus_mux21
  port map
  (
    A0 => G,
    A1 => H,
    S  => sGH,
    X  => GH
  );

  -- sCD <= S(1) when (c0 = '0') else S(0);
  cus_mux21_sCD : entity work.cus_mux21
  port map
  (
    A0 => S(1),
    A1 => S(0),
    S  => c0,
    X  => sCD
  );

  -- sEF <= S(2) when (c1 = '0') else S(0);
  cus_mux21_sEF : entity work.cus_mux21
  port map
  (
    A0 => S(2),
    A1 => S(0),
    S  => c1,
    X  => sEF
  );

  -- sGH <= sEH when (c0 = '0') else sEF;
  cus_mux21_sGH : entity work.cus_mux21
  port map
  (
    A0 => sEH,
    A1 => sEF,
    S  => c0,
    X  => sGH
  );

  -- sEH <= S(3) when (c1 = '0') else S(1);
  cus_mux21_sEH : entity work.cus_mux21
  port map
  (
    A0 => S(3),
    A1 => S(1),
    S  => c1,
    X  => sEH
  );

  -- AD <= AB when (S(1) = '0') else CD;
  cus_mux21_AD : entity work.cus_mux21
  port map
  (
    A0 => AB,
    A1 => CD,
    S  => s(1),
    X  => AD
  );
  -- EH <= EF when (sEH = '0') else GH;
  cus_mux21_EH : entity work.cus_mux21
  port map
  (
    A0 => EF,
    A1 => GH,
    S  => sEH,
    X  => EH
  );

  -- AH <= AD when (S(3) = '0') else EH;
  cus_mux21_AH : entity work.cus_mux21
  port map
  (
    A0 => AD,
    A1 => EH,
    S  => S(3),
    X  => AH
  );

  M_AB <= AB;

  -- M_AD <= CD when (c0 = '0') else AD;
  cus_mux21_M_AD : entity work.cus_mux21
  port map
  (
    A0 => CD,
    A1 => AD,
    S  => c0,
    X  => M_AD
  );
  -- M_AH <= EH_GH when (c1 = '0') else AH;
  cus_mux21_M_AH : entity work.cus_mux21
  port map
  (
    A0 => EH_GH,
    A1 => AH,
    S  => c1,
    X  => M_AH
  );
  M_EF <= EF;

end architecture Behavioral;
