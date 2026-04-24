package attr_pack_lut4ab_mux8lut_frame_config_mux is

  attribute fabulous    : string;
  attribute belmap      : string;
  attribute c0          : integer;
  attribute c1          : integer;
  attribute external    : string;
  attribute shared_port : string;
  attribute global      : string;

end package attr_pack_lut4ab_mux8lut_frame_config_mux;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_lut4ab_mux8lut_frame_config_mux.all;

-- (* FABulous, BelMap, c0=0, c1=1 *)

entity mux8lut_frame_config_mux is
  generic (
    noconfigbits : integer := 2 -- has to be adjusted manually (we don't use an arithmetic parser for the value)
  );
  port (                                       -- IMPORTANT: this has to be in a dedicated line
    a    : in    std_logic;                    -- MUX inputs
    b    : in    std_logic;
    c    : in    std_logic;
    d    : in    std_logic;
    e    : in    std_logic;
    f    : in    std_logic;
    g    : in    std_logic;
    h    : in    std_logic;
    s    : in    std_logic_vector(3 downto 0); -- MUX select lines
    m_ab : out   std_logic;
    m_ad : out   std_logic;
    m_ah : out   std_logic;
    m_ef : out   std_logic;
    -- GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    configbits : in    std_logic_vector(noconfigbits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );
  attribute fabulous of MUX8LUT_frame_config_mux : entity is "TRUE";
  attribute belmap of MUX8LUT_frame_config_mux   : entity is "TRUE";
  attribute c0 of MUX8LUT_frame_config_mux       : entity is 0;
  attribute c1 of MUX8LUT_frame_config_mux       : entity is 1;
  attribute global of ConfigBits                 : signal is "TRUE";
end entity mux8lut_frame_config_mux;

architecture behavioral of mux8lut_frame_config_mux is

  signal ab    : std_logic;
  signal cd    : std_logic;
  signal ef    : std_logic;
  signal gh    : std_logic;
  signal scd   : std_logic;
  signal sef   : std_logic;
  signal sgh   : std_logic;
  signal seh   : std_logic;
  signal ad    : std_logic;
  signal eh    : std_logic;
  signal ah    : std_logic;
  signal eh_gh : std_logic;

  signal c0, c1 : std_logic; -- configuration bits

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      s  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

begin

  c0 <= configbits(0);
  c1 <= configbits(1);

  -- see figure (column-wise left-to-right)

  -- AB <= A when (S(0) = '0') else B;
  cus_mux21_ab : component cus_mux21
    port map (
      a0 => a,
      a1 => b,
      s  => s(0),
      x  => ab
    );

  -- CD <= C when (sCD = '0') else D;
  cus_mux21_cd : component cus_mux21
    port map (
      a0 => c,
      a1 => d,
      s  => scd,
      x  => cd
    );

  -- EF <= E when (sEF = '0') else F;
  cus_mux21_ef : component cus_mux21
    port map (
      a0 => e,
      a1 => f,
      s  => sef,
      x  => ef
    );

  -- GH <= G when (sGH = '0') else H;
  cus_mux21_gh : component cus_mux21
    port map (
      a0 => g,
      a1 => h,
      s  => sgh,
      x  => gh
    );

  -- sCD <= S(1) when (c0 = '0') else S(0);
  cus_mux21_scd : component cus_mux21
    port map (
      a0 => s(1),
      a1 => s(0),
      s  => c0,
      x  => scd
    );

  -- sEF <= S(2) when (c1 = '0') else S(0);
  cus_mux21_sef : component cus_mux21
    port map (
      a0 => s(2),
      a1 => s(0),
      s  => c1,
      x  => sef
    );

  -- sGH <= sEH when (c0 = '0') else sEF;
  cus_mux21_sgh : component cus_mux21
    port map (
      a0 => seh,
      a1 => sef,
      s  => c0,
      x  => sgh
    );

  -- sEH <= S(3) when (c1 = '0') else S(1);
  cus_mux21_seh : component cus_mux21
    port map (
      a0 => s(3),
      a1 => s(1),
      s  => c1,
      x  => seh
    );

  -- AD <= AB when (S(1) = '0') else CD;
  cus_mux21_ad : component cus_mux21
    port map (
      a0 => ab,
      a1 => cd,
      s  => s(1),
      x  => ad
    );

  -- EH <= EF when (sEH = '0') else GH;
  cus_mux21_eh : component cus_mux21
    port map (
      a0 => ef,
      a1 => gh,
      s  => seh,
      x  => eh
    );

  -- AH <= AD when (S(3) = '0') else EH;
  cus_mux21_ah : component cus_mux21
    port map (
      a0 => ad,
      a1 => eh,
      s  => s(3),
      x  => ah
    );

  m_ab <= ab;

  -- M_AD <= CD when (c0 = '0') else AD;
  cus_mux21_m_ad : component cus_mux21
    port map (
      a0 => cd,
      a1 => ad,
      s  => c0,
      x  => m_ad
    );

  -- M_AH <= EH_GH when (c1 = '0') else AH;
  cus_mux21_m_ah : component cus_mux21
    port map (
      a0 => eh_gh,
      a1 => ah,
      s  => c1,
      x  => m_ah
    );

  m_ef <= ef;

end architecture behavioral;
