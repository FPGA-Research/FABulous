-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module BlockRAM_1KB (BlockRAM_1KB.v:1)
--   READ_ADDRESS_MSB_FROM_DATALSB = 24
--   WRITE_ADDRESS_MSB_FROM_DATALSB = 16
--   WRITE_ENABLE_FROM_DATA = 20

entity blockram_1kb is
  generic (
    read_address_msb_from_datalsb  : integer := 24;
    write_address_msb_from_datalsb : integer := 16;
    write_enable_from_data         : integer := 20
  );
  port (
    c0      : in    std_logic;
    c1      : in    std_logic;
    c2      : in    std_logic;
    c3      : in    std_logic;
    c4      : in    std_logic;
    c5      : in    std_logic;
    clk     : in    std_logic;
    rd_addr : in    std_logic_vector(7 downto 0);
    rd_data : out   std_logic_vector(31 downto 0);
    wr_addr : in    std_logic_vector(7 downto 0);
    wr_data : in    std_logic_vector(31 downto 0)
  );
end entity blockram_1kb;

-- Generated from Verilog module BlockRAM_1KB (BlockRAM_1KB.v:1)
--   READ_ADDRESS_MSB_FROM_DATALSB = 24
--   WRITE_ADDRESS_MSB_FROM_DATALSB = 16
--   WRITE_ENABLE_FROM_DATA = 20

architecture from_verilog of blockram_1kb is

  signal alwayswriteenable                       : std_logic;                     -- Declared at BlockRAM_1KB.v:25
  signal final_dout                              : std_logic_vector(31 downto 0); -- Declared at BlockRAM_1KB.v:119
  signal memwriteenable                          : std_logic;                     -- Declared at BlockRAM_1KB.v:31
  signal mem_dout                                : std_logic_vector(31 downto 0); -- Declared at BlockRAM_1KB.v:73
  signal mem_wr_mask                             : std_logic_vector(3 downto 0);  -- Declared at BlockRAM_1KB.v:39
  signal muxeddatain                             : std_logic_vector(31 downto 0); -- Declared at BlockRAM_1KB.v:40
  signal optional_register_enabled_configuration : std_logic;                     -- Declared at BlockRAM_1KB.v:24
  signal rd_dout_additional_register             : std_logic_vector(31 downto 0); -- Declared at BlockRAM_1KB.v:115
  signal rd_dout_muxed                           : std_logic_vector(31 downto 0); -- Declared at BlockRAM_1KB.v:92
  signal rd_dout_sel                             : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:88
  signal rd_port_configuration                   : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:22
  signal wr_addr_topbits                         : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:42
  signal wr_port_configuration                   : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:23

  constant write_address_top_lsb : integer := read_address_msb_from_datalsb;
  constant write_address_top_msb : integer := read_address_msb_from_datalsb + 1;

  component sram_1rw1r_32_256_8_sky130 is
    port (
      addr0  : in    std_logic_vector(7 downto 0);
      addr1  : in    std_logic_vector(7 downto 0);
      clk0   : in    std_logic;
      clk1   : in    std_logic;
      csb0   : in    std_logic;
      csb1   : in    std_logic;
      din0   : in    std_logic_vector(31 downto 0);
      dout0  : out   std_logic_vector(31 downto 0);
      dout1  : out   std_logic_vector(31 downto 0);
      web0   : in    std_logic;
      wmask0 : in    std_logic_vector(3 downto 0)
    );
  end component sram_1rw1r_32_256_8_sky130;

begin

  alwayswriteenable                       <= c4;
  optional_register_enabled_configuration <= c5;
  rd_data                                 <= final_dout;
  wr_port_configuration                   <= c0 & c1;
  rd_port_configuration                   <= c2 & c3;
  wr_addr_topbits                         <= wr_data(write_address_top_msb downto write_address_top_lsb);

  -- Generated from instantiation at BlockRAM_1KB.v:75
  memory_cell : component sram_1rw1r_32_256_8_sky130
    port map (
      addr0  => wr_addr,
      addr1  => rd_addr,
      clk0   => clk,
      clk1   => clk,
      csb0   => memwriteenable,
      csb1   => '0',
      din0   => muxeddatain,
      dout1  => mem_dout,
      web0   => memwriteenable,
      wmask0 => mem_wr_mask
    );

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:32)
  process_001 : process (alwayswriteenable, wr_data) is
  begin

    if (alwayswriteenable = '1') then
      memwriteenable <= '0';
    else
      memwriteenable <= not wr_data(write_enable_from_data);
    end if;

  end process process_001;

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:44)
  process_002 : process (wr_port_configuration, wr_data, wr_addr_topbits) is
  begin

    muxeddatain <= "UUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU";

    if (wr_port_configuration = "00") then
      mem_wr_mask <= x"F";
      muxeddatain <= wr_data;
    else
      if (wr_port_configuration = "01") then
        if (wr_addr_topbits = "00") then
          mem_wr_mask                  <= x"3";
          muxeddatain(0 + 15 downto 0) <= wr_data(0 + 15 downto 0);
        else
          mem_wr_mask                    <= x"C";
          muxeddatain(16 + 15 downto 16) <= wr_data(0 + 15 downto 0);
        end if;
      else
        if (wr_port_configuration = "10") then
          if (wr_addr_topbits = "00") then
            mem_wr_mask                 <= x"1";
            muxeddatain(0 + 7 downto 0) <= wr_data(0 + 7 downto 0);
          else
            if (wr_addr_topbits = "01") then
              mem_wr_mask                 <= x"2";
              muxeddatain(8 + 7 downto 8) <= wr_data(0 + 7 downto 0);
            else
              if (wr_addr_topbits = "10") then
                mem_wr_mask                   <= x"4";
                muxeddatain(16 + 7 downto 16) <= wr_data(0 + 7 downto 0);
              else
                mem_wr_mask                   <= x"8";
                muxeddatain(24 + 7 downto 24) <= wr_data(0 + 7 downto 0);
              end if;
            end if;
          end if;
        end if;
      end if;
    end if;

  end process process_002;

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:89)
  process_003 : process (clk) is
  begin

    if rising_edge(clk) then
      rd_dout_sel <= wr_data(24 + 1 downto 24);
    end if;

  end process process_003;

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:93)
  process_004 : process (mem_dout, rd_port_configuration, rd_dout_sel) is
  begin

    rd_dout_muxed <= mem_dout;

    if (rd_port_configuration = "00") then
      rd_dout_muxed <= mem_dout;
    else
      if (rd_port_configuration = "01") then
        if ((rd_dout_sel(0)) = '0') then
          rd_dout_muxed(15 downto 0) <= mem_dout(15 downto 0);
        else
          rd_dout_muxed(0 + 15 downto 0) <= mem_dout(16 + 15 downto 16);
        end if;
      else
        if (rd_port_configuration = "10") then
          if (rd_dout_sel = "00") then
            rd_dout_muxed(0 + 7 downto 0) <= mem_dout(0 + 7 downto 0);
          else
            if (rd_dout_sel = "01") then
              rd_dout_muxed(0 + 7 downto 0) <= mem_dout(8 + 7 downto 8);
            else
              if (rd_dout_sel = "10") then
                rd_dout_muxed(0 + 7 downto 0) <= mem_dout(16 + 7 downto 16);
              else
                rd_dout_muxed(0 + 7 downto 0) <= mem_dout(24 + 7 downto 24);
              end if;
            end if;
          end if;
        end if;
      end if;
    end if;

  end process process_004;

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:116)
  process_005 : process (clk) is
  begin

    if rising_edge(clk) then
      rd_dout_additional_register <= rd_dout_muxed;
    end if;

  end process process_005;

  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:121)
  process_006 : process (optional_register_enabled_configuration, rd_dout_additional_register, rd_dout_muxed) is
  begin

    if (optional_register_enabled_configuration = '1') then
      final_dout <= rd_dout_additional_register;
    else
      final_dout <= rd_dout_muxed;
    end if;

  end process process_006;

end architecture from_verilog;

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module sram_1rw1r_32_256_8_sky130 (BlockRAM_1KB.v:132)
--   ADDR_WIDTH = 8
--   DATA_WIDTH = 32
--   DELAY = 3
--   NUM_WMASKS = 4
--   RAM_DEPTH = 256

entity sram_1rw1r_32_256_8_sky130 is
  port (
    addr0  : in    std_logic_vector(7 downto 0);
    addr1  : in    std_logic_vector(7 downto 0);
    clk0   : in    std_logic;
    clk1   : in    std_logic;
    csb0   : in    std_logic;
    csb1   : in    std_logic;
    din0   : in    std_logic_vector(31 downto 0);
    dout0  : out   std_logic_vector(31 downto 0);
    dout1  : out   std_logic_vector(31 downto 0);
    web0   : in    std_logic;
    wmask0 : in    std_logic_vector(3 downto 0)
  );
end entity sram_1rw1r_32_256_8_sky130;

-- Generated from Verilog module sram_1rw1r_32_256_8_sky130 (BlockRAM_1KB.v:132)
--   ADDR_WIDTH = 8
--   DATA_WIDTH = 32
--   DELAY = 3
--   NUM_WMASKS = 4
--   RAM_DEPTH = 256

architecture from_verilog of sram_1rw1r_32_256_8_sky130 is

begin

  dout0 <= (others => '0');
  dout1 <= (others => '0');

end architecture from_verilog;
