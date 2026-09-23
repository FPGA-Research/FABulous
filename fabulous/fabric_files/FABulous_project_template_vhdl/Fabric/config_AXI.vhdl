-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 12.0 (stable) ()

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module config_AXI (config_AXI.v:3)

entity config_AXI is
  port (
    active        : out   std_logic;
    clk           : in    std_logic;
    data          : out   unsigned(31 downto 0);
    reset_n       : in    std_logic;
    s_axi_araddr  : in    unsigned(31 downto 0);
    s_axi_arready : buffer std_logic;
    s_axi_arvalid : in    std_logic;
    s_axi_awaddr  : in    unsigned(31 downto 0);
    s_axi_awready : buffer std_logic;
    s_axi_awvalid : in    std_logic;
    s_axi_bready  : in    std_logic;
    s_axi_bresp   : out   unsigned(1 downto 0);
    s_axi_bvalid  : buffer std_logic;
    s_axi_rdata   : out   unsigned(31 downto 0);
    s_axi_rready  : in    std_logic;
    s_axi_rresp   : out   unsigned(1 downto 0);
    s_axi_rvalid  : buffer std_logic;
    s_axi_wdata   : in    unsigned(31 downto 0);
    s_axi_wready  : buffer std_logic;
    s_axi_wstrb   : in    unsigned(3 downto 0);
    s_axi_wvalid  : in    std_logic;
    strobe        : out   std_logic
  );
end entity config_AXI;

-- Generated from Verilog module config_AXI (config_AXI.v:3)

architecture from_verilog of config_AXI is

  signal data_Reg         : unsigned(31 downto 0);
  signal strobe_Reg       : std_logic;
  signal tmp_ivl_16       : std_logic; -- Temporary created at config_AXI.v:129
  signal ar_done          : std_logic; -- Declared at config_AXI.v:92
  signal aw_done          : std_logic; -- Declared at config_AXI.v:42
  signal b_done           : std_logic; -- Declared at config_AXI.v:75
  signal local_strobe     : std_logic; -- Declared at config_AXI.v:111
  signal old_local_strobe : std_logic; -- Declared at config_AXI.v:112
  signal w_done           : std_logic; -- Declared at config_AXI.v:58

begin

  data          <= data_Reg;
  strobe        <= strobe_Reg;
  s_axi_bvalid  <= b_done;
  s_axi_rvalid  <= ar_done;
  tmp_ivl_16    <= aw_done or w_done;
  active        <= tmp_ivl_16 or b_done;
  s_axi_awready <= not aw_done;
  s_axi_wready  <= not w_done;
  s_axi_arready <= not ar_done;
  s_axi_bresp   <= "00";
  s_axi_rdata   <= x"00000000";
  s_axi_rresp   <= "00";

  -- Generated from always process in config_AXI (config_AXI.v:44)
  process (clk) is
  begin

    if rising_edge(clk) then
      if ((not reset_n) = '1') then
        aw_done <= '0';
      else
        if ((s_axi_awready = '1') and (s_axi_awvalid = '1')) then
          aw_done <= '1';
        else
          if ((s_axi_bready = '1') and (s_axi_bvalid = '1')) then
            aw_done <= '0';
          end if;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_AXI (config_AXI.v:60)
  process (clk) is
  begin

    if rising_edge(clk) then
      if ((not reset_n) = '1') then
        w_done <= '0';
      else
        if ((s_axi_wready = '1') and (s_axi_wvalid = '1')) then
          w_done   <= '1';
          data_Reg <= s_axi_wdata;
        else
          if ((s_axi_bready = '1') and (s_axi_bvalid = '1')) then
            w_done <= '0';
          end if;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_AXI (config_AXI.v:77)
  process (clk) is
  begin

    if rising_edge(clk) then
      if ((not reset_n) = '1') then
        b_done <= '0';
      else
        if ((s_axi_bready = '1') and (s_axi_bvalid = '1')) then
          b_done <= '0';
        else
          if ((aw_done = '1') and (w_done = '1')) then
            b_done <= '1';
          end if;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_AXI (config_AXI.v:97)
  process (clk) is
  begin

    if rising_edge(clk) then
      if ((not reset_n) = '1') then
        ar_done <= '0';
      else
        if ((s_axi_arvalid = '1') and (s_axi_arready = '1')) then
          ar_done <= '1';
        else
          if ((s_axi_rvalid = '1') and (s_axi_rready = '1')) then
            ar_done <= '0';
          end if;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_AXI (config_AXI.v:113)
  process (clk) is
  begin

    if rising_edge(clk) then
      if ((not reset_n) = '1') then
        local_strobe     <= '0';
        old_local_strobe <= '0';
        strobe_Reg       <= '0';
      else
        local_strobe <= '0';
        if ((aw_done = '1') and (w_done = '1')) then
          local_strobe <= '1';
        end if;
        old_local_strobe <= local_strobe;
        strobe_Reg       <= local_strobe and (not old_local_strobe);
      end if;
    end if;

  end process;

end architecture from_verilog;
