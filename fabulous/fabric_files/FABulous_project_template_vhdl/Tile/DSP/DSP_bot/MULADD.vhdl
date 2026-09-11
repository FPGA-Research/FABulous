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

end package attr_pack_DSP_MULADD;

library IEEE;
  use IEEE.STD_LOGIC_1164.all;
  use IEEE.NUMERIC_STD.all;
  use work.attr_pack_DSP_MULADD.all;
-- (* FABulous, BelMap, A_reg=0, B_reg=1, C_reg=2, ACC=3, signExtension=4, ACCout=5 *)

entity MULADD is
  generic (
    NoConfigBits : integer := 6
  );
  port (                                                           -- IMPORTANT: this has to be in a dedicated line
    A          : in    std_logic_vector(7 downto 0);               -- operand A
    B          : in    std_logic_vector(7 downto 0);               -- operand B
    C          : in    std_logic_vector(19 downto 0);              -- operand C
    Q          : out   std_logic_vector(19 downto 0);
    clr        : in    std_logic;                                  -- clear
    UserCLK    : in    std_logic;                                  -- (* FABulous, EXTERNAL, SHARED_PORT *)
    ConfigBits : in    std_logic_vector(NoConfigBits - 1 downto 0) -- (* FABulous, GLOBAL *)
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

  signal A_reg_data : std_logic_vector(7 downto 0);  -- port A read data register
  signal B_reg_data : std_logic_vector(7 downto 0);  -- port B read data register
  signal C_reg_data : std_logic_vector(19 downto 0); -- port B read data register

  signal OPA : std_logic_vector(7 downto 0);  -- port A
  signal OPB : std_logic_vector(7 downto 0);  -- port B
  signal OPC : std_logic_vector(19 downto 0); -- port B

  signal ACC_data : std_logic_vector(19 downto 0); -- accumulator register
  signal sum      : std_logic_vector(19 downto 0); -- port B read data register
  signal sum_in   : std_logic_vector(19 downto 0); -- port B read data register

  signal OPA_extended     : signed(8  downto 0);
  signal OPB_extended     : signed(8  downto 0);
  signal product_signed   : signed(17 downto 0);
  signal product_extended : std_logic_vector(19 downto 0);

begin

  OPA <= A when (ConfigBits(0) = '0') else
         A_reg_data;
  OPB <= B when (ConfigBits(1) = '0') else
         B_reg_data;
  OPC <= C when (ConfigBits(2) = '0') else
         C_reg_data;

  sum_in <= OPC when (ConfigBits(3) = '0') else
            ACC_data;

  OPA_extended <= signed(OPA(7) & OPA) when (ConfigBits(4) = '1') else
                  signed('0' & OPA);
  OPB_extended <= signed(OPB(7) & OPB) when (ConfigBits(4) = '1') else
                  signed('0' & OPB);

  product_signed <= OPA_extended * OPB_extended;

  product_extended <= std_logic_vector(product_signed(17) & product_signed(17) & product_signed) when (ConfigBits(4) = '1') else
                      "00" & std_logic_vector(product_signed);

  sum <= std_logic_vector(signed(product_extended) + signed(sum_in));

  Q <= sum when (ConfigBits(5) = '0') else
       ACC_data;

  process (UserCLK) is
  begin

    if (UserCLK'event and UserCLK = '1') then
      A_reg_data <= A;
      B_reg_data <= B;
      C_reg_data <= C;
      if (clr = '1') then
        ACC_data <= (others => '0');
      else
        ACC_data <= sum;
      end if;
    end if;

  end process;

end architecture Behavioral;
