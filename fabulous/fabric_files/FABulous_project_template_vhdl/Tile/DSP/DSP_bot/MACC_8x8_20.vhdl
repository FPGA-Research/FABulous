-- 8x8 multiply-accumulate unit with optional input registers
--
--  A[7:0] -->[MUX c0]--> OPA --+
--            (A/A_reg)         |   +------+   +--------+   +-----+
--                              +-->| 8x8  |-->|  ext   |-->|     |
--  B[7:0] -->[MUX c1]--> OPB --+-->| MUL  |   | [c4]   |   | ADD |----> sum
--            (B/B_reg)             +------+   +--------+ +>|     |       |
--                                                        | +-----+       |
--  C[19:0] ->[MUX c2]--> OPC -->[MUX c3]--> sum_in ------+               |
--            (C/C_reg)          (OPC/ACC)                                |
--                                   ^          +-------+                 |
--                                   +----------|  ACC  |<----------------+
--                                              | D   Q |<-- clr
--  Q[19:0] <-----[MUX c5]----------------------+-------+
--                (sum/ACC)
--
package attr_pack_DSP_MULADD is
  attribute FABulous      : string;
  attribute BelMap        : string;
  attribute A_reg         : integer;
  attribute B_reg         : integer;
  attribute C_reg         : integer;
  attribute ACC           : integer;
  attribute signExtension : integer;
  attribute ACCout        : integer;
  attribute EXTERNAL      : string;
  attribute SHARED_PORT   : string;
  attribute GLOBAL        : string;
end package;

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.NUMERIC_STD.all;
use work.attr_pack_DSP_MULADD.all;
-- (* FABulous, BelMap, A_reg=0, B_reg=1, C_reg=2, ACC=3, signExtension=4, ACCout=5 *)
entity MULADD is
  generic (NoConfigBits : integer := 6);
  port (-- IMPORTANT: this has to be in a dedicated line
    A          : in std_logic_vector(7 downto 0); -- operand A
    B          : in std_logic_vector(7 downto 0); -- operand B
    C          : in std_logic_vector(19 downto 0); -- operand C
    Q          : out std_logic_vector(19 downto 0);
    clr        : in std_logic; -- clear
    UserCLK    : in std_logic; -- (* FABulous, EXTERNAL, SHARED_PORT *)
    ConfigBits : in std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );
  attribute FABulous of MULADD      : entity is "TRUE";
  attribute BelMap of MULADD        : entity is "TRUE";
  attribute A_reg of MULADD         : entity is 0;
  attribute B_reg of MULADD         : entity is 1;
  attribute C_reg of MULADD         : entity is 2;
  attribute ACC of MULADD           : entity is 3;
  attribute signExtension of MULADD : entity is 4;
  attribute ACCout of MULADD        : entity is 5;
  attribute EXTERNAL of UserCLK     : signal is "TRUE";
  attribute SHARED_PORT of UserCLK  : signal is "TRUE";
  attribute GLOBAL of ConfigBits    : signal is "TRUE";
end entity MULADD;

architecture Behavioral of MULADD is

  signal A_reg : std_logic_vector(7 downto 0);
  signal B_reg : std_logic_vector(7 downto 0);
  signal C_reg : std_logic_vector(19 downto 0);

  signal OPA : std_logic_vector(7 downto 0);
  signal OPB : std_logic_vector(7 downto 0);
  signal OPC : std_logic_vector(19 downto 0);

  signal ACC    : std_logic_vector(19 downto 0);
  signal sum    : unsigned(19 downto 0);
  signal sum_in : std_logic_vector(19 downto 0);

  signal product          : unsigned(15 downto 0);
  signal product_extended : unsigned(19 downto 0);
begin

  OPA <= A when (ConfigBits(0) = '0') else
    A_reg;
  OPB <= B when (ConfigBits(1) = '0') else
    B_reg;
  OPC <= C when (ConfigBits(2) = '0') else
    C_reg;

  sum_in <= OPC when (ConfigBits(3) = '0') else
    ACC;

  product <= unsigned(OPA) * unsigned(OPB);

  -- The sign extension was not tested
  product_extended <= "0000" & product when (ConfigBits(4) = '0') else
    product(product'high) & product(product'high) & product(product'high) & product(product'high) & product;

  sum <= product_extended + unsigned(sum_in);

  Q <=  std_logic_vector(sum) when (ConfigBits(5) = '0') else
    ACC;
  process (UserCLK)
  begin
    if UserCLK'event and UserCLK = '1' then
      A_reg <= A;
      B_reg <= B;
      C_reg <= C;
      if clr = '1' then
        ACC <= (others => '0');
      else
        ACC <= std_logic_vector(sum);
      end if;
    end if;
  end process;

end architecture Behavioral;
