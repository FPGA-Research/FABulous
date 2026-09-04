library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_latch is
  port (
    D  : in    std_logic;
    E  : in    std_logic;
    Q  : out   std_logic;
    QN : out   std_logic
  );
end entity config_latch;

architecture from_verilog of config_latch is

begin

  process (E, D) is
  begin

    if (E = '1') then
      Q  <= D;
      QN <= not D;
    end if;

  end process;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux161 is
  port (
    A0  : in    std_logic;
    A1  : in    std_logic;
    A10 : in    std_logic;
    A11 : in    std_logic;
    A12 : in    std_logic;
    A13 : in    std_logic;
    A14 : in    std_logic;
    A15 : in    std_logic;
    A2  : in    std_logic;
    A3  : in    std_logic;
    A4  : in    std_logic;
    A5  : in    std_logic;
    A6  : in    std_logic;
    A7  : in    std_logic;
    A8  : in    std_logic;
    A9  : in    std_logic;
    S0  : in    std_logic;
    S0N : in    std_logic;
    S1  : in    std_logic;
    S1N : in    std_logic;
    S2  : in    std_logic;
    S2N : in    std_logic;
    S3  : in    std_logic;
    S3N : in    std_logic;
    X   : out   std_logic
  );
end entity cus_mux161;

architecture from_verilog of cus_mux161 is

  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;
  signal cus_mux41_out2 : std_logic;
  signal cus_mux41_out3 : std_logic;

  component cus_mux41 is
    port (
      A0  : in    std_logic;
      A1  : in    std_logic;
      A2  : in    std_logic;
      A3  : in    std_logic;
      S0  : in    std_logic;
      S0N : in    std_logic;
      S1  : in    std_logic;
      S1N : in    std_logic;
      X   : out   std_logic
    );
  end component cus_mux41;

  signal X_Readable : std_logic;

begin

  cus_mux41_inst0 : component cus_mux41
    port map (
      A0  => A0,
      A1  => A1,
      A2  => A2,
      A3  => A3,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out0
    );

  cus_mux41_inst1 : component cus_mux41
    port map (
      A0  => A4,
      A1  => A5,
      A2  => A6,
      A3  => A7,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out1
    );

  cus_mux41_inst2 : component cus_mux41
    port map (
      A0  => A8,
      A1  => A9,
      A2  => A10,
      A3  => A11,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out2
    );

  cus_mux41_inst3 : component cus_mux41
    port map (
      A0  => A12,
      A1  => A13,
      A2  => A14,
      A3  => A15,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out3
    );

  X <= X_Readable;

  cus_mux41_inst4 : component cus_mux41
    port map (
      A0  => cus_mux41_out0,
      A1  => cus_mux41_out1,
      A2  => cus_mux41_out2,
      A3  => cus_mux41_out3,
      S0  => S2,
      S0N => S2N,
      S1  => S3,
      S1N => S3N,
      X   => X_Readable
    );

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux41 is
  port (
    A0  : in    std_logic;
    A1  : in    std_logic;
    A2  : in    std_logic;
    A3  : in    std_logic;
    S0  : in    std_logic;
    S0N : in    std_logic;
    S1  : in    std_logic;
    S1N : in    std_logic;
    X   : out   std_logic
  );
end entity cus_mux41;

architecture from_verilog of cus_mux41 is

  signal B0 : std_logic;
  signal B1 : std_logic;

begin

  B0 <= A1 when S0 = '1' else
        A0;
  B1 <= A3 when S0 = '1' else
        A2;
  X  <= B1 when S1 = '1' else
        B0;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux81 is
  port (
    A0  : in    std_logic;
    A1  : in    std_logic;
    A2  : in    std_logic;
    A3  : in    std_logic;
    A4  : in    std_logic;
    A5  : in    std_logic;
    A6  : in    std_logic;
    A7  : in    std_logic;
    S0  : in    std_logic;
    S0N : in    std_logic;
    S1  : in    std_logic;
    S1N : in    std_logic;
    S2  : in    std_logic;
    S2N : in    std_logic;
    X   : out   std_logic
  );
end entity cus_mux81;

architecture from_verilog of cus_mux81 is

  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;

  component cus_mux41 is
    port (
      A0  : in    std_logic;
      A1  : in    std_logic;
      A2  : in    std_logic;
      A3  : in    std_logic;
      S0  : in    std_logic;
      S0N : in    std_logic;
      S1  : in    std_logic;
      S1N : in    std_logic;
      X   : out   std_logic
    );
  end component cus_mux41;

  component cus_mux21 is
    port (
      A0 : in    std_logic;
      A1 : in    std_logic;
      S  : in    std_logic;
      X  : out   std_logic
    );
  end component cus_mux21;

  signal X_Readable : std_logic;

begin

  cus_mux41_inst0 : component cus_mux41
    port map (
      A0  => A0,
      A1  => A1,
      A2  => A2,
      A3  => A3,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out0
    );

  cus_mux41_inst1 : component cus_mux41
    port map (
      A0  => A4,
      A1  => A5,
      A2  => A6,
      A3  => A7,
      S0  => S0,
      S0N => S0N,
      S1  => S1,
      S1N => S1N,
      X   => cus_mux41_out1
    );

  X <= X_Readable;

  cus_mux21_inst : component cus_mux21
    port map (
      A0 => cus_mux41_out0,
      A1 => cus_mux41_out1,
      S  => S2,
      X  => X_Readable
    );

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux21 is
  port (
    A0 : in    std_logic;
    A1 : in    std_logic;
    S  : in    std_logic;
    X  : out   std_logic
  );
end entity cus_mux21;

architecture from_verilog of cus_mux21 is

begin

  X <= A0 when S = '0' else
       A1 when S = '1' else
       'U';

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module my_buf (./models_pack.v:144)

entity my_buf is
  port (
    A : in    std_logic;
    X : out   std_logic
  );
end entity my_buf;

-- Generated from Verilog module my_buf (./models_pack.v:144)

architecture from_verilog of my_buf is

begin

  X <= A;

end architecture from_verilog;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity clk_buf is
  port (
    A : in    std_logic;
    X : out   std_logic
  );
end entity clk_buf;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)

architecture Behavior of clk_buf is

begin

  X <= A;

end architecture Behavior;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Sky130 SRAM 1RW1R 32x256x8 simulation model
--   ADDR_WIDTH = 8
--   DATA_WIDTH = 32
--   DELAY = 3
--   NUM_WMASKS = 4
--   RAM_DEPTH = 256

entity sram_1rw1r_32_256_8_sky130 is
  port (
    addr0  : in    unsigned(7 downto 0);
    addr1  : in    unsigned(7 downto 0);
    clk0   : in    std_logic;
    clk1   : in    std_logic;
    csb0   : in    std_logic;
    csb1   : in    std_logic;
    din0   : in    unsigned(31 downto 0);
    dout0  : out   unsigned(31 downto 0);
    dout1  : out   unsigned(31 downto 0);
    web0   : in    std_logic;
    wmask0 : in    unsigned(3 downto 0)
  );
end entity sram_1rw1r_32_256_8_sky130;

architecture from_verilog of sram_1rw1r_32_256_8_sky130 is

  type mem_type is array (255 downto 0) of unsigned(31 downto 0);

  signal dout0_reg  : unsigned(31 downto 0);
  signal dout1_reg  : unsigned(31 downto 0);
  signal addr0_reg  : unsigned(7 downto 0);
  signal addr1_reg  : unsigned(7 downto 0);
  signal csb0_reg   : std_logic;
  signal csb1_reg   : std_logic;
  signal din0_reg   : unsigned(31 downto 0);
  signal mem        : mem_type;
  signal web0_reg   : std_logic;
  signal wmask0_reg : unsigned(3 downto 0);

begin

  dout0 <= dout0_reg;
  dout1 <= dout1_reg;

  process (clk0) is
  begin

    if rising_edge(clk0) then
      csb0_reg   <= csb0;
      web0_reg   <= web0;
      wmask0_reg <= wmask0;
      addr0_reg  <= addr0;
      din0_reg   <= din0;
      dout0_reg  <= (others => 'U');
    end if;

  end process;

  process (clk1) is
  begin

    if rising_edge(clk1) then
      csb1_reg  <= csb1;
      addr1_reg <= addr1;
      dout1_reg <= (others => 'U');
    end if;

  end process;

  mem_write0 : process (clk0) is
  begin

    if falling_edge(clk0) then
      if (((not csb0_reg) = '1') and ((not web0_reg) = '1')) then
        if (wmask0_reg(0) = '1') then
          mem(0) <= resize(din0_reg(0 + 7 downto 0), 32);
        end if;
        if (wmask0_reg(1) = '1') then
          mem(8) <= resize(din0_reg(8 + 7 downto 8), 32);
        end if;
        if (wmask0_reg(2) = '1') then
          mem(16) <= resize(din0_reg(16 + 7 downto 16), 32);
        end if;
        if (wmask0_reg(3) = '1') then
          mem(24) <= resize(din0_reg(24 + 7 downto 24), 32);
        end if;
      end if;
    end if;

  end process mem_write0;

  mem_read0 : process (clk0) is
  begin

    if falling_edge(clk0) then
      if (((not csb0_reg) = '1') and (web0_reg = '1')) then
        dout0_reg <= mem(to_integer(resize(addr0_reg, 10))) after 3 ms;
      end if;
    end if;

  end process mem_read0;

  mem_read1 : process (clk1) is
  begin

    if falling_edge(clk1) then
      if ((not csb1_reg) = '1') then
        dout1_reg <= mem(to_integer(resize(addr1_reg, 10))) after 3 ms;
      end if;
    end if;

  end process mem_read1;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

package my_package is

  component config_latch is
    port (
      D  : in    std_logic;
      E  : in    std_logic;
      Q  : out   std_logic;
      QN : out   std_logic
    );
  end component config_latch;

  component cus_mux161 is
    port (
      A0  : in    std_logic;
      A1  : in    std_logic;
      A10 : in    std_logic;
      A11 : in    std_logic;
      A12 : in    std_logic;
      A13 : in    std_logic;
      A14 : in    std_logic;
      A15 : in    std_logic;
      A2  : in    std_logic;
      A3  : in    std_logic;
      A4  : in    std_logic;
      A5  : in    std_logic;
      A6  : in    std_logic;
      A7  : in    std_logic;
      A8  : in    std_logic;
      A9  : in    std_logic;
      S0  : in    std_logic;
      S0N : in    std_logic;
      S1  : in    std_logic;
      S1N : in    std_logic;
      S2  : in    std_logic;
      S2N : in    std_logic;
      S3  : in    std_logic;
      S3N : in    std_logic;
      X   : out   std_logic
    );
  end component cus_mux161;

  component cus_mux41 is
    port (
      A0  : in    std_logic;
      A1  : in    std_logic;
      A2  : in    std_logic;
      A3  : in    std_logic;
      S0  : in    std_logic;
      S0N : in    std_logic;
      S1  : in    std_logic;
      S1N : in    std_logic;
      X   : out   std_logic
    );
  end component cus_mux41;

  component cus_mux81 is
    port (
      A0  : in    std_logic;
      A1  : in    std_logic;
      A2  : in    std_logic;
      A3  : in    std_logic;
      A4  : in    std_logic;
      A5  : in    std_logic;
      A6  : in    std_logic;
      A7  : in    std_logic;
      S0  : in    std_logic;
      S0N : in    std_logic;
      S1  : in    std_logic;
      S1N : in    std_logic;
      S2  : in    std_logic;
      S2N : in    std_logic;
      X   : out   std_logic
    );
  end component cus_mux81;

  component cus_mux21 is
    port (
      A0 : in    std_logic;
      A1 : in    std_logic;
      S  : in    std_logic;
      X  : out   std_logic
    );
  end component cus_mux21;

  component my_buf is
    port (
      A : in    std_logic;
      X : out   std_logic
    );
  end component my_buf;

  component clk_buf is
    port (
      A : in    std_logic;
      X : out   std_logic
    );
  end component clk_buf;

  component sram_1rw1r_32_256_8_sky130 is
    port (
      addr0  : in    unsigned(7 downto 0);
      addr1  : in    unsigned(7 downto 0);
      clk0   : in    std_logic;
      clk1   : in    std_logic;
      csb0   : in    std_logic;
      csb1   : in    std_logic;
      din0   : in    unsigned(31 downto 0);
      dout0  : out   unsigned(31 downto 0);
      dout1  : out   unsigned(31 downto 0);
      web0   : in    std_logic;
      wmask0 : in    unsigned(3 downto 0)
    );
  end component sram_1rw1r_32_256_8_sky130;

end package my_package;
