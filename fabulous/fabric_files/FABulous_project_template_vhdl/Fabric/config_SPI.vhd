-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 12.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module config_SPI (config_SPI.v:3)
entity config_SPI is
  port (
    active : out std_logic;
    clk : in std_logic;
    data : out unsigned(31 downto 0);
    mosi : in std_logic;
    reset_n : in std_logic;
    sck : in std_logic;
    ss_n : in std_logic;
    strobe : out std_logic
  );
end entity; 

-- Generated from Verilog module config_SPI (config_SPI.v:3)
architecture from_verilog of config_SPI is
  signal active_Reg : std_logic;
  signal data_Reg : unsigned(31 downto 0);
  signal strobe_Reg : std_logic;
  signal bit_counter : unsigned(5 downto 0);  -- Declared at config_SPI.v:15
  signal local_strobe : std_logic;  -- Declared at config_SPI.v:24
  signal mosi_sample : unsigned(3 downto 0);  -- Declared at config_SPI.v:18
  signal old_local_strobe : std_logic;  -- Declared at config_SPI.v:25
  signal sck_sample : unsigned(3 downto 0);  -- Declared at config_SPI.v:17
  signal serial_data : unsigned(31 downto 0);  -- Declared at config_SPI.v:21
  signal ss_n_sample : unsigned(3 downto 0);  -- Declared at config_SPI.v:19
  signal word_complete : std_logic;  -- Declared at config_SPI.v:23
begin
  active <= active_Reg;
  data <= data_Reg;
  strobe <= strobe_Reg;
  
  -- Generated from always process in config_SPI (config_SPI.v:27)
  p_input_sync: process (reset_n, clk) is
  begin
    if falling_edge(reset_n) or rising_edge(clk) then
      if (not reset_n) = '1' then
        sck_sample <= X"0";
        mosi_sample <= X"0";
        ss_n_sample <= X"0";
      else
        sck_sample <= sck_sample(0 + 2 downto 0) & sck;
        mosi_sample <= mosi_sample(0 + 2 downto 0) & mosi;
        ss_n_sample <= ss_n_sample(0 + 2 downto 0) & ss_n;
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_SPI (config_SPI.v:39)
  p_in_shift: process (reset_n, clk) is
  begin
    if falling_edge(reset_n) or rising_edge(clk) then
      if (not reset_n) = '1' then
        serial_data <= X"00000000";
        bit_counter <= "000000";
      else
        word_complete <= '0';
        if ((sck_sample(3) = '0') and (sck_sample(2) = '1')) and (ss_n_sample(3) = '0') then
          serial_data <= serial_data(0 + 30 downto 0) & mosi_sample(3);
          if bit_counter = "011111" then
            word_complete <= '1';
            bit_counter <= "000000";
          else
            bit_counter <= bit_counter + "000001";
          end if;
        end if;
        if (ss_n_sample(3) = '1') and (ss_n_sample(2) = '0') then
          bit_counter <= "000000";
        end if;
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_SPI (config_SPI.v:61)
  p_parallel_load: process (reset_n, clk) is
  begin
    if falling_edge(reset_n) or rising_edge(clk) then
      if (not reset_n) = '1' then
        local_strobe <= '0';
        data_Reg <= X"00000000";
        old_local_strobe <= '0';
        strobe_Reg <= '0';
      else
        local_strobe <= '0';
        if word_complete = '1' then
          data_Reg <= serial_data;
          local_strobe <= '1';
        end if;
        old_local_strobe <= local_strobe;
        strobe_Reg <= local_strobe and (not old_local_strobe);
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_SPI (config_SPI.v:78)
  active_FSM: process (reset_n, clk) is
  begin
    if falling_edge(reset_n) or rising_edge(clk) then
      if (not reset_n) = '1' then
        active_Reg <= '0';
      else
        if ss_n_sample(3) = '0' then
          active_Reg <= '1';
        end if;
        if ss_n_sample(3) = '1' then
          active_Reg <= '0';
        end if;
      end if;
    end if;
  end process;
end architecture;

