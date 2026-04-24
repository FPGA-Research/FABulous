package attr_pack_dsp_muladd is

  attribute fabulous      : string;
  attribute belmap        : string;
  attribute a_reg         : integer;
  attribute b_reg         : integer;
  attribute c_reg         : integer;
  attribute acc           : integer;
  attribute signextension : integer;
  attribute accout        : integer;
  attribute external      : string;
  attribute shared_port   : string;
  attribute global        : string;

end package attr_pack_dsp_muladd;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use work.attr_pack_dsp_muladd.all;
-- (* FABulous, BelMap, A_reg=0, B_reg=1, C_reg=2, ACC=3, signExtension=4, ACCout=5 *)

entity muladd is
  generic (
    noconfigbits : integer := 6
  );
  port (                                                           -- IMPORTANT: this has to be in a dedicated line
    a          : in    std_logic_vector(7 downto 0);               -- operand A
    b          : in    std_logic_vector(7 downto 0);               -- operand B
    c          : in    std_logic_vector(19 downto 0);              -- operand C
    q          : out   std_logic_vector(19 downto 0);
    clr        : in    std_logic;                                  -- clear
    userclk    : in    std_logic;                                  -- (* FABulous, EXTERNAL, SHARED_PORT *)
    configbits : in    std_logic_vector(noconfigbits - 1 downto 0) -- (* FABulous, GLOBAL *)
  );
  attribute fabulous of MULADD      : entity is "TRUE";
  attribute belmap of MULADD        : entity is "TRUE";
  attribute a_reg of MULADD         : entity is 0;
  attribute b_reg of MULADD         : entity is 1;
  attribute c_reg of MULADD         : entity is 2;
  attribute acc of MULADD           : entity is 3;
  attribute signextension of MULADD : entity is 4;
  attribute accout of MULADD        : entity is 5;
  attribute external of UserCLK     : signal is "TRUE";
  attribute shared_port of UserCLK  : signal is "TRUE";
  attribute global of ConfigBits    : signal is "TRUE";
end entity muladd;

architecture behavioral of muladd is

  signal a_reg : std_logic_vector(7 downto 0);  -- port A read data register
  signal b_reg : std_logic_vector(7 downto 0);  -- port B read data register
  signal c_reg : std_logic_vector(19 downto 0); -- port B read data register

  signal opa : std_logic_vector(7 downto 0);  -- port A
  signal opb : std_logic_vector(7 downto 0);  -- port B
  signal opc : std_logic_vector(19 downto 0); -- port B

  signal acc    : std_logic_vector(19 downto 0); -- accumulator register
  signal sum    : unsigned(19 downto 0);         -- port B read data register
  signal sum_in : std_logic_vector(19 downto 0); -- port B read data register

  signal product          : unsigned(15 downto 0);
  signal product_extended : unsigned(19 downto 0);

begin

  opa <= a when (configbits(0) = '0') else
         a_reg;
  opb <= b when (configbits(1) = '0') else
         b_reg;
  opc <= c when (configbits(2) = '0') else
         c_reg;

  sum_in <= opc when (configbits(3) = '0') else
            acc;

  product <= unsigned(opa) * unsigned(opb);

  -- The sign extension was not tested
  product_extended <= "0000" & product when (configbits(4) = '0') else
                      product(product'high) & product(product'high) &
                      product(product'high) & product(product'high) &
                      product;

  sum <= product_extended + unsigned(sum_in);

  q <= std_logic_vector(sum) when (configbits(5) = '0') else
       acc;

  process_001 : process (userclk) is
  begin

    if (userclk'event and userclk = '1') then
      a_reg <= a;
      b_reg <= b;
      c_reg <= c;
      if (clr = '1') then
        acc <= (others => '0');
      else
        acc <= std_logic_vector(sum);
      end if;
    end if;

  end process process_001;

end architecture behavioral;
