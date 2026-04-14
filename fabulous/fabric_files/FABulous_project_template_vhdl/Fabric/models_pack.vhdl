library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity config_latch is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end entity;

architecture from_verilog of config_latch is
begin
  process (E, D) is
  begin
    if E = '1' then
      Q <= D;
      QN <= not D;
    end if;
  end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cus_mux161 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A10 : in std_logic;
    A11 : in std_logic;
    A12 : in std_logic;
    A13 : in std_logic;
    A14 : in std_logic;
    A15 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    A4 : in std_logic;
    A5 : in std_logic;
    A6 : in std_logic;
    A7 : in std_logic;
    A8 : in std_logic;
    A9 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    S2 : in std_logic;
    S2N : in std_logic;
    S3 : in std_logic;
    S3N : in std_logic;
    X : out std_logic
  );
end entity;

architecture from_verilog of cus_mux161 is
  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;
  signal cus_mux41_out2 : std_logic;
  signal cus_mux41_out3 : std_logic;

  component cus_mux41 is
    port (
      A0 : in std_logic;
      A1 : in std_logic;
      A2 : in std_logic;
      A3 : in std_logic;
      S0 : in std_logic;
      S0N : in std_logic;
      S1 : in std_logic;
      S1N : in std_logic;
      X : out std_logic
    );
  end component;
  signal X_Readable : std_logic;
begin

  cus_mux41_inst0: cus_mux41
    port map (
      A0 => A0,
      A1 => A1,
      A2 => A2,
      A3 => A3,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out0
    );

  cus_mux41_inst1: cus_mux41
    port map (
      A0 => A4,
      A1 => A5,
      A2 => A6,
      A3 => A7,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out1
    );

  cus_mux41_inst2: cus_mux41
    port map (
      A0 => A8,
      A1 => A9,
      A2 => A10,
      A3 => A11,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out2
    );

  cus_mux41_inst3: cus_mux41
    port map (
      A0 => A12,
      A1 => A13,
      A2 => A14,
      A3 => A15,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out3
    );
  X <= X_Readable;

  cus_mux41_inst4: cus_mux41
    port map (
      A0 => cus_mux41_out0,
      A1 => cus_mux41_out1,
      A2 => cus_mux41_out2,
      A3 => cus_mux41_out3,
      S0 => S2,
      S0N => S2N,
      S1 => S3,
      S1N => S3N,
      X => X_Readable
    );
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cus_mux41 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    X : out std_logic
  );
end entity;

architecture from_verilog of cus_mux41 is
  signal B0 : std_logic;
  signal B1 : std_logic;

begin
  B0 <= A1 when S0 = '1' else A0;
  B1 <= A3 when S0 = '1' else A2;
  X <= B1 when S1 = '1' else B0;

end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cus_mux81 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    A4 : in std_logic;
    A5 : in std_logic;
    A6 : in std_logic;
    A7 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    S2 : in std_logic;
    S2N : in std_logic;
    X : out std_logic
  );
end entity;

architecture from_verilog of cus_mux81 is
  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;

  component cus_mux41 is
    port (
      A0 : in std_logic;
      A1 : in std_logic;
      A2 : in std_logic;
      A3 : in std_logic;
      S0 : in std_logic;
      S0N : in std_logic;
      S1 : in std_logic;
      S1N : in std_logic;
      X : out std_logic
    );
  end component;

  component cus_mux21 is
    port (
      A0 : in std_logic;
      A1 : in std_logic;
      S : in std_logic;
      X : out std_logic
    );
  end component;
  signal X_Readable : std_logic;
begin

  cus_mux41_inst0: cus_mux41
    port map (
      A0 => A0,
      A1 => A1,
      A2 => A2,
      A3 => A3,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out0
    );

  cus_mux41_inst1: cus_mux41
    port map (
      A0 => A4,
      A1 => A5,
      A2 => A6,
      A3 => A7,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_out1
    );
  X <= X_Readable;

  cus_mux21_inst: cus_mux21
    port map (
      A0 => cus_mux41_out0,
      A1 => cus_mux41_out1,
      S => S2,
      X => X_Readable
    );
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cus_mux21 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    S : in std_logic;
    X : out std_logic
  );
end entity;

architecture from_verilog of cus_mux21 is
begin
  X <= A0 when S = '0' else
       A1 when S = '1' else
       'U';

end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module my_buf (./models_pack.v:144)
entity my_buf is
  port (
    A : in std_logic;
    X : out std_logic
  );
end entity;

-- Generated from Verilog module my_buf (./models_pack.v:144)
architecture from_verilog of my_buf is
begin
  X <= A;
end architecture;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity clk_buf is
  port (
    A : in std_logic;
    X : out std_logic
  );
end entity;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)
architecture Behavior of clk_buf is
begin
  X <= A;
end architecture;

library ieee;
use ieee.std_logic_1164.all;

package my_package is

component config_latch is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end component;


component cus_mux161 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A10 : in std_logic;
    A11 : in std_logic;
    A12 : in std_logic;
    A13 : in std_logic;
    A14 : in std_logic;
    A15 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    A4 : in std_logic;
    A5 : in std_logic;
    A6 : in std_logic;
    A7 : in std_logic;
    A8 : in std_logic;
    A9 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    S2 : in std_logic;
    S2N : in std_logic;
    S3 : in std_logic;
    S3N : in std_logic;
    X : out std_logic
  );
end component;

component cus_mux41 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    X : out std_logic
  );
end component;

component cus_mux81 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    A2 : in std_logic;
    A3 : in std_logic;
    A4 : in std_logic;
    A5 : in std_logic;
    A6 : in std_logic;
    A7 : in std_logic;
    S0 : in std_logic;
    S0N : in std_logic;
    S1 : in std_logic;
    S1N : in std_logic;
    S2 : in std_logic;
    S2N : in std_logic;
    X : out std_logic
  );
end component;

component cus_mux21 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    S : in std_logic;
    X : out std_logic
  );
end component;

component my_buf is
  port (
    A : in std_logic;
    X : out std_logic
  );
end component;

component clk_buf is
  port (
    A : in std_logic;
    X : out std_logic
  );
end component;

end package my_package;
