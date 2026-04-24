library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_latch is
  port (
    d  : in    std_logic;
    e  : in    std_logic;
    q  : out   std_logic;
    qn : out   std_logic
  );
end entity config_latch;

architecture from_verilog of config_latch is

begin

  process_001 : process (e, d) is
  begin

    if (e = '1') then
      q  <= d;
      qn <= not d;
    end if;

  end process process_001;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux161 is
  port (
    a0  : in    std_logic;
    a1  : in    std_logic;
    a10 : in    std_logic;
    a11 : in    std_logic;
    a12 : in    std_logic;
    a13 : in    std_logic;
    a14 : in    std_logic;
    a15 : in    std_logic;
    a2  : in    std_logic;
    a3  : in    std_logic;
    a4  : in    std_logic;
    a5  : in    std_logic;
    a6  : in    std_logic;
    a7  : in    std_logic;
    a8  : in    std_logic;
    a9  : in    std_logic;
    s0  : in    std_logic;
    s0n : in    std_logic;
    s1  : in    std_logic;
    s1n : in    std_logic;
    s2  : in    std_logic;
    s2n : in    std_logic;
    s3  : in    std_logic;
    s3n : in    std_logic;
    x   : out   std_logic
  );
end entity cus_mux161;

architecture from_verilog of cus_mux161 is

  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;
  signal cus_mux41_out2 : std_logic;
  signal cus_mux41_out3 : std_logic;

  component cus_mux41 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux41;

  signal x_readable : std_logic;

begin

  cus_mux41_inst0 : component cus_mux41
    port map (
      a0  => a0,
      a1  => a1,
      a2  => a2,
      a3  => a3,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out0
    );

  cus_mux41_inst1 : component cus_mux41
    port map (
      a0  => a4,
      a1  => a5,
      a2  => a6,
      a3  => a7,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out1
    );

  cus_mux41_inst2 : component cus_mux41
    port map (
      a0  => a8,
      a1  => a9,
      a2  => a10,
      a3  => a11,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out2
    );

  cus_mux41_inst3 : component cus_mux41
    port map (
      a0  => a12,
      a1  => a13,
      a2  => a14,
      a3  => a15,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out3
    );

  x <= x_readable;

  cus_mux41_inst4 : component cus_mux41
    port map (
      a0  => cus_mux41_out0,
      a1  => cus_mux41_out1,
      a2  => cus_mux41_out2,
      a3  => cus_mux41_out3,
      s0  => s2,
      s0n => s2n,
      s1  => s3,
      s1n => s3n,
      x   => x_readable
    );

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux41 is
  port (
    a0  : in    std_logic;
    a1  : in    std_logic;
    a2  : in    std_logic;
    a3  : in    std_logic;
    s0  : in    std_logic;
    s0n : in    std_logic;
    s1  : in    std_logic;
    s1n : in    std_logic;
    x   : out   std_logic
  );
end entity cus_mux41;

architecture from_verilog of cus_mux41 is

  signal b0 : std_logic;
  signal b1 : std_logic;

begin

  b0 <= a1 when s0 = '1' else
        a0;
  b1 <= a3 when s0 = '1' else
        a2;
  x  <= b1 when s1 = '1' else
        b0;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux81 is
  port (
    a0  : in    std_logic;
    a1  : in    std_logic;
    a2  : in    std_logic;
    a3  : in    std_logic;
    a4  : in    std_logic;
    a5  : in    std_logic;
    a6  : in    std_logic;
    a7  : in    std_logic;
    s0  : in    std_logic;
    s0n : in    std_logic;
    s1  : in    std_logic;
    s1n : in    std_logic;
    s2  : in    std_logic;
    s2n : in    std_logic;
    x   : out   std_logic
  );
end entity cus_mux81;

architecture from_verilog of cus_mux81 is

  signal cus_mux41_out0 : std_logic;
  signal cus_mux41_out1 : std_logic;

  component cus_mux41 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux41;

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      s  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

  signal x_readable : std_logic;

begin

  cus_mux41_inst0 : component cus_mux41
    port map (
      a0  => a0,
      a1  => a1,
      a2  => a2,
      a3  => a3,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out0
    );

  cus_mux41_inst1 : component cus_mux41
    port map (
      a0  => a4,
      a1  => a5,
      a2  => a6,
      a3  => a7,
      s0  => s0,
      s0n => s0n,
      s1  => s1,
      s1n => s1n,
      x   => cus_mux41_out1
    );

  x <= x_readable;

  cus_mux21_inst : component cus_mux21
    port map (
      a0 => cus_mux41_out0,
      a1 => cus_mux41_out1,
      s  => s2,
      x  => x_readable
    );

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity cus_mux21 is
  port (
    a0 : in    std_logic;
    a1 : in    std_logic;
    s  : in    std_logic;
    x  : out   std_logic
  );
end entity cus_mux21;

architecture from_verilog of cus_mux21 is

begin

  x <= a0 when s = '0' else
       a1 when s = '1' else
       'U';

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module my_buf (./models_pack.v:144)

entity my_buf is
  port (
    a : in    std_logic;
    x : out   std_logic
  );
end entity my_buf;

-- Generated from Verilog module my_buf (./models_pack.v:144)

architecture from_verilog of my_buf is

begin

  x <= a;

end architecture from_verilog;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity clk_buf is
  port (
    a : in    std_logic;
    x : out   std_logic
  );
end entity clk_buf;

-- Generated from Verilog module clk_buf (fabulous_tb.v:83)

architecture behavior of clk_buf is

begin

  x <= a;

end architecture behavior;

library ieee;
  use ieee.std_logic_1164.all;

package my_package is

  component config_latch is
    port (
      d  : in    std_logic;
      e  : in    std_logic;
      q  : out   std_logic;
      qn : out   std_logic
    );
  end component config_latch;

  component cus_mux161 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a10 : in    std_logic;
      a11 : in    std_logic;
      a12 : in    std_logic;
      a13 : in    std_logic;
      a14 : in    std_logic;
      a15 : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      a4  : in    std_logic;
      a5  : in    std_logic;
      a6  : in    std_logic;
      a7  : in    std_logic;
      a8  : in    std_logic;
      a9  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      s2  : in    std_logic;
      s2n : in    std_logic;
      s3  : in    std_logic;
      s3n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux161;

  component cus_mux41 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux41;

  component cus_mux81 is
    port (
      a0  : in    std_logic;
      a1  : in    std_logic;
      a2  : in    std_logic;
      a3  : in    std_logic;
      a4  : in    std_logic;
      a5  : in    std_logic;
      a6  : in    std_logic;
      a7  : in    std_logic;
      s0  : in    std_logic;
      s0n : in    std_logic;
      s1  : in    std_logic;
      s1n : in    std_logic;
      s2  : in    std_logic;
      s2n : in    std_logic;
      x   : out   std_logic
    );
  end component cus_mux81;

  component cus_mux21 is
    port (
      a0 : in    std_logic;
      a1 : in    std_logic;
      s  : in    std_logic;
      x  : out   std_logic
    );
  end component cus_mux21;

  component my_buf is
    port (
      a : in    std_logic;
      x : out   std_logic
    );
  end component my_buf;

  component clk_buf is
    port (
      a : in    std_logic;
      x : out   std_logic
    );
  end component clk_buf;

end package my_package;
