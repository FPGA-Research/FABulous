-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 12.0 (stable) ()

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module bitbang (bitbang.v:3)
--   OFF_PATTERN = 64176
--   ON_PATTERN = 64177

entity bitbang is
  port (
    active  : out   std_logic;
    clk     : in    std_logic;
    data    : out   unsigned(31 downto 0);
    reset_n : in    std_logic;
    s_clk   : in    std_logic;
    s_data  : in    std_logic;
    strobe  : out   std_logic
  );
end entity bitbang;

-- Generated from Verilog module bitbang (bitbang.v:3)
--   OFF_PATTERN = 64176
--   ON_PATTERN = 64177

architecture from_verilog of bitbang is

  signal active_Reg       : std_logic;
  signal data_Reg         : unsigned(31 downto 0);
  signal strobe_Reg       : std_logic;
  signal local_strobe     : std_logic;             -- Declared at bitbang.v:23
  signal old_local_strobe : std_logic;             -- Declared at bitbang.v:24
  signal s_clk_sample     : unsigned(3 downto 0);  -- Declared at bitbang.v:18
  signal s_data_sample    : unsigned(3 downto 0);  -- Declared at bitbang.v:17
  signal serial_control   : unsigned(15 downto 0); -- Declared at bitbang.v:21
  signal serial_data      : unsigned(31 downto 0); -- Declared at bitbang.v:20

begin

  active <= active_Reg;
  data   <= data_Reg;
  strobe <= strobe_Reg;

  -- Generated from always process in bitbang (bitbang.v:26)
  p_input_sync : process (reset_n, clk) is
  begin

    if (falling_edge(reset_n) or rising_edge(clk)) then
      if ((not reset_n) = '1') then
        s_data_sample <= x"0";
        s_clk_sample  <= x"0";
      else
        s_data_sample <= s_data_sample(0 + 2 downto 0) & s_data;
        s_clk_sample  <= s_clk_sample(0 + 2 downto 0) & s_clk;
      end if;
    end if;

  end process;

  -- Generated from always process in bitbang (bitbang.v:36)
  p_in_shift : process (reset_n, clk) is
  begin

    if (falling_edge(reset_n) or rising_edge(clk)) then
      if ((not reset_n) = '1') then
        serial_data    <= x"00000000";
        serial_control <= x"0000";
      else
        if ((s_clk_sample(3) = '0') and (s_clk_sample(2) = '1')) then
          serial_data <= serial_data(0 + 30 downto 0) & s_data_sample(3);
        end if;
        if ((s_clk_sample(3) = '1') and (s_clk_sample(2) = '0')) then
          serial_control <= serial_control(0 + 14 downto 0) & s_data_sample(3);
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in bitbang (bitbang.v:52)
  p_parallel_load : process (reset_n, clk) is
  begin

    if (falling_edge(reset_n) or rising_edge(clk)) then
      if ((not reset_n) = '1') then
        local_strobe     <= '0';
        data_Reg         <= x"00000000";
        old_local_strobe <= '0';
        strobe_Reg       <= '0';
      else
        local_strobe <= '0';
        if (serial_control = x"FAB1") then
          data_Reg     <= serial_data;
          local_strobe <= '1';
        end if;
        old_local_strobe <= local_strobe;
        strobe_Reg       <= local_strobe and (not old_local_strobe);
      end if;
    end if;

  end process;

  -- Generated from always process in bitbang (bitbang.v:70)
  active_fsm : process (reset_n, clk) is
  begin

    if (falling_edge(reset_n) or rising_edge(clk)) then
      if ((not reset_n) = '1') then
        active_Reg <= '0';
      else
        if (serial_control = x"FAB1") then
          active_Reg <= '1';
        end if;
        if (serial_control = x"FAB0") then
          active_Reg <= '0';
        end if;
      end if;
    end if;

  end process;

end architecture from_verilog;
