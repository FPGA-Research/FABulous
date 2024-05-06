library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity LHQD1 is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end entity; 

architecture from_verilog of LHQD1 is
begin
  process (E, D) is
  begin
    if rising_edge(E) then
      Q <= D;
      QN <= not D;
    end if;
  end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity MUX16PTv2 is
  port (
    IN1 : in std_logic;
    IN10 : in std_logic;
    IN11 : in std_logic;
    IN12 : in std_logic;
    IN13 : in std_logic;
    IN14 : in std_logic;
    IN15 : in std_logic;
    IN16 : in std_logic;
    IN2 : in std_logic;
    IN3 : in std_logic;
    IN4 : in std_logic;
    IN5 : in std_logic;
    IN6 : in std_logic;
    IN7 : in std_logic;
    IN8 : in std_logic;
    IN9 : in std_logic;
    O : out std_logic;
    S1 : in std_logic;
    S2 : in std_logic;
    S3 : in std_logic;
    S4 : in std_logic
  );
end entity; 

architecture from_verilog of MUX16PTv2 is
  signal a0 : std_logic_vector(7 downto 0);
  signal a1 : std_logic_vector(3 downto 0);
  signal a2 : std_logic_vector(1 downto 0);
  -- As this MUX primitive is used for the LUT, we need accurate X/U behaviour
  function f_mux2(a : in std_logic; b : in std_logic; s : in std_logic) return std_logic is
    variable r : std_logic;
  begin
    r := a when s = '0' else
         b when s = '1' else
         a when a = b else -- case when S is undefined, but it's don't care because a and b are the same
         'U';
    return r;
  end function;
begin
  a0 <= f_mux2(IN15, IN16, S1) & f_mux2(IN13, IN14, S1) & f_mux2(IN11, IN12, S1) & f_mux2(IN9, IN10, S1) & f_mux2(IN7, IN8, S1) & f_mux2(IN5, IN6, S1) & f_mux2(IN3, IN4, S1) & f_mux2(IN1, IN2, S1);
  a1 <= f_mux2(a0(6), a0(7), S2) & f_mux2(a0(4), a0(5), S2) & f_mux2(a0(2), a0(3), S2) & f_mux2(a0(0), a0(1), S2);
  a2 <= f_mux2(a1(2), a1(3), S3) & f_mux2(a1(0), a1(1), S3);
  O <= f_mux2(a2(0), a2(1), S4) ;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity MUX4PTv4 is
  port (
    IN1 : in std_logic;
    IN2 : in std_logic;
    IN3 : in std_logic;
    IN4 : in std_logic;
    O : out std_logic;
    S1 : in std_logic;
    S2 : in std_logic
  );
end entity; 

architecture from_verilog of MUX4PTv4 is
  signal SEL : unsigned(1 downto 0); 
begin
  SEL <= S2 & S1;

  with SEL select
    O <= IN1  when "00",
         IN2  when "01",
         IN3  when "10",
         IN4  when "11",
         'U'  when others ;
  
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
  signal SEL : unsigned(1 downto 0);
  signal X_reg : std_logic;
  signal LPM_d0_ivl_1 : std_logic;
  signal LPM_d1_ivl_1 : std_logic;
begin
  SEL <= S1 & S0;

  with SEL select
    X <= A0  when "00",
         A1  when "01",
         A2  when "10",
         A3  when "11",
         'U'  when others;

end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cus_mux161_buf is
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

-- Generated from Verilog module cus_mux161_buf (./models_pack.v:418)
architecture from_verilog of cus_mux161_buf is
  signal cus_mux41_buf_out0 : std_logic;
  signal cus_mux41_buf_out1 : std_logic; 
  signal cus_mux41_buf_out2 : std_logic; 
  signal cus_mux41_buf_out3 : std_logic; 
  
  component cus_mux41_buf is
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
  cus_mux41_buf_inst0: cus_mux41_buf
    port map (
      A0 => A0,
      A1 => A1,
      A2 => A2,
      A3 => A3,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out0
    );
  
  cus_mux41_buf_inst1: cus_mux41_buf
    port map (
      A0 => A4,
      A1 => A5,
      A2 => A6,
      A3 => A7,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out1
    );

  cus_mux41_buf_inst2: cus_mux41_buf
    port map (
      A0 => A8,
      A1 => A9,
      A2 => A10,
      A3 => A11,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out2
    );
  
  cus_mux41_buf_inst3: cus_mux41_buf
    port map (
      A0 => A12,
      A1 => A13,
      A2 => A14,
      A3 => A15,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out3
    );
  X <= X_Readable;

  cus_mux41_buf_inst4: cus_mux41_buf
    port map (
      A0 => cus_mux41_buf_out0,
      A1 => cus_mux41_buf_out1,
      A2 => cus_mux41_buf_out2,
      A3 => cus_mux41_buf_out3,
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

entity cus_mux41_buf is
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

architecture from_verilog of cus_mux41_buf is
  signal SEL : unsigned(1 downto 0); 
  signal LPM_d0_ivl_1 : std_logic;
  signal LPM_d1_ivl_1 : std_logic;
begin
  SEL <= S1 & S0;
  with SEL select
    X <= A0  when "00",
         A1  when "01",
         A2  when "10",
         A3  when "11",
        'U'  when others;

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
  
  component my_mux2 is
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
  
  my_mux2_inst: my_mux2
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

entity my_mux2 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    S : in std_logic;
    X : out std_logic
  );
end entity; 

architecture from_verilog of my_mux2 is
  signal SEL : std_logic;
begin
  SEL <= S;

  with SEL select
    X <= A0  when '0',
         A1  when '1',
        'U'  when others;
  
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module cus_mux81_buf (./models_pack.v:273)
entity cus_mux81_buf is
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

-- Generated from Verilog module cus_mux81_buf (./models_pack.v:273)
architecture from_verilog of cus_mux81_buf is
  signal cus_mux41_buf_out0 : std_logic;  -- Declared at ./models_pack.v:290
  signal cus_mux41_buf_out1 : std_logic;  -- Declared at ./models_pack.v:291
  
  component cus_mux41_buf is
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
  
  component my_mux2 is
    port (
      A0 : in std_logic;
      A1 : in std_logic;
      S : in std_logic;
      X : out std_logic
    );
  end component;
  signal X_Readable : std_logic;  -- Needed to connect outputs
begin
  
  -- Generated from instantiation at ./models_pack.v:293
  cus_mux41_buf_inst0: cus_mux41_buf
    port map (
      A0 => A0,
      A1 => A1,
      A2 => A2,
      A3 => A3,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out0
    );
  
  -- Generated from instantiation at ./models_pack.v:305
  cus_mux41_buf_inst1: cus_mux41_buf
    port map (
      A0 => A4,
      A1 => A5,
      A2 => A6,
      A3 => A7,
      S0 => S0,
      S0N => S0N,
      S1 => S1,
      S1N => S1N,
      X => cus_mux41_buf_out1
    );
  X <= X_Readable;
  
  -- Generated from instantiation at ./models_pack.v:317
  my_mux2_inst: my_mux2
    port map (
      A0 => cus_mux41_buf_out0,
      A1 => cus_mux41_buf_out1,
      S => S2,
      X => X_Readable
    );
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

component LHQD1 is
  port (
    D : in std_logic;
    E : in std_logic;
    Q : out std_logic;
    QN : out std_logic
  );
end component;

component MUX16PTv2 is
  port (
    IN1 : in std_logic;
    IN10 : in std_logic;
    IN11 : in std_logic;
    IN12 : in std_logic;
    IN13 : in std_logic;
    IN14 : in std_logic;
    IN15 : in std_logic;
    IN16 : in std_logic;
    IN2 : in std_logic;
    IN3 : in std_logic;
    IN4 : in std_logic;
    IN5 : in std_logic;
    IN6 : in std_logic;
    IN7 : in std_logic;
    IN8 : in std_logic;
    IN9 : in std_logic;
    O : out std_logic;
    S1 : in std_logic;
    S2 : in std_logic;
    S3 : in std_logic;
    S4 : in std_logic
  );
end component;

component MUX4PTv4 is
  port (
    IN1 : in std_logic;
    IN2 : in std_logic;
    IN3 : in std_logic;
    IN4 : in std_logic;
    O : out std_logic;
    S1 : in std_logic;
    S2 : in std_logic
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

component cus_mux161_buf is
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

component cus_mux41_buf is
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

component my_mux2 is
  port (
    A0 : in std_logic;
    A1 : in std_logic;
    S : in std_logic;
    X : out std_logic
  );
end component; 

component cus_mux81_buf is
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