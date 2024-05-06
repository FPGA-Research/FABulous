-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module BlockRAM_1KB (BlockRAM_1KB.v:1)
--   READ_ADDRESS_MSB_FROM_DATALSB = 24
--   WRITE_ADDRESS_MSB_FROM_DATALSB = 16
--   WRITE_ENABLE_FROM_DATA = 20
entity BlockRAM_1KB is
  generic (
    READ_ADDRESS_MSB_FROM_DATALSB : integer := 24;
    WRITE_ADDRESS_MSB_FROM_DATALSB : integer := 16;
    WRITE_ENABLE_FROM_DATA : integer := 20
  );
  port (
    C0 : in std_logic;
    C1 : in std_logic;
    C2 : in std_logic;
    C3 : in std_logic;
    C4 : in std_logic;
    C5 : in std_logic;
    clk : in std_logic;
    rd_addr : in std_logic_vector(7 downto 0);
    rd_data : out std_logic_vector(31 downto 0);
    wr_addr : in std_logic_vector(7 downto 0);
    wr_data : in std_logic_vector(31 downto 0)
  );
end entity; 

-- Generated from Verilog module BlockRAM_1KB (BlockRAM_1KB.v:1)
--   READ_ADDRESS_MSB_FROM_DATALSB = 24
--   WRITE_ADDRESS_MSB_FROM_DATALSB = 16
--   WRITE_ENABLE_FROM_DATA = 20
architecture from_verilog of BlockRAM_1KB is
  signal alwaysWriteEnable : std_logic;  -- Declared at BlockRAM_1KB.v:25
  signal final_dout : std_logic_vector(31 downto 0);  -- Declared at BlockRAM_1KB.v:119
  signal memWriteEnable : std_logic;  -- Declared at BlockRAM_1KB.v:31
  signal mem_dout : std_logic_vector(31 downto 0);  -- Declared at BlockRAM_1KB.v:73
  signal mem_wr_mask : std_logic_vector(3 downto 0);  -- Declared at BlockRAM_1KB.v:39
  signal muxedDataIn : std_logic_vector(31 downto 0);  -- Declared at BlockRAM_1KB.v:40
  signal optional_register_enabled_configuration : std_logic;  -- Declared at BlockRAM_1KB.v:24
  signal rd_dout_additional_register : std_logic_vector(31 downto 0);  -- Declared at BlockRAM_1KB.v:115
  signal rd_dout_muxed : std_logic_vector(31 downto 0);  -- Declared at BlockRAM_1KB.v:92
  signal rd_dout_sel : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:88
  signal rd_port_configuration : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:22
  signal wr_addr_topbits : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:42
  signal wr_port_configuration : std_logic_vector(1 downto 0);  -- Declared at BlockRAM_1KB.v:23
  
  component sram_1rw1r_32_256_8_sky130 is
    port (
      addr0 : in std_logic_vector(7 downto 0);
      addr1 : in std_logic_vector(7 downto 0);
      clk0 : in std_logic;
      clk1 : in std_logic;
      csb0 : in std_logic;
      csb1 : in std_logic;
      din0 : in std_logic_vector(31 downto 0);
      dout0 : out std_logic_vector(31 downto 0);
      dout1 : out std_logic_vector(31 downto 0);
      web0 : in std_logic;
      wmask0 : in std_logic_vector(3 downto 0)
    );
  end component;
begin
  alwaysWriteEnable <= C4;
  optional_register_enabled_configuration <= C5;
  rd_data <= final_dout;
  wr_port_configuration <= C0 & C1;
  rd_port_configuration <= C2 & C3;
  wr_addr_topbits <= wr_data(READ_ADDRESS_MSB_FROM_DATALSB + 1 downto READ_ADDRESS_MSB_FROM_DATALSB);
  
  -- Generated from instantiation at BlockRAM_1KB.v:75
  memory_cell: sram_1rw1r_32_256_8_sky130
    port map (
      addr0 => wr_addr,
      addr1 => rd_addr,
      clk0 => clk,
      clk1 => clk,
      csb0 => memWriteEnable,
      csb1 => '0',
      din0 => muxedDataIn,
      dout1 => mem_dout,
      web0 => memWriteEnable,
      wmask0 => mem_wr_mask
    );
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:32)
  process (alwaysWriteEnable, wr_data) is
  begin
    if alwaysWriteEnable = '1' then
      memWriteEnable <= '0';
    else
      memWriteEnable <= not wr_data(WRITE_ENABLE_FROM_DATA);
    end if;
  end process;
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:44)
  process (wr_port_configuration, wr_data, wr_addr_topbits) is
  begin
    muxedDataIn <= "UUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU";
    if wr_port_configuration = X"00000000" then
      mem_wr_mask <= X"f";
      muxedDataIn <= wr_data;
    else
      if wr_port_configuration = X"00000001" then
        if wr_addr_topbits = X"00000000" then
          mem_wr_mask <= X"3";
          muxedDataIn(0 + 15 downto 0) <= wr_data(0 + 15 downto 0);
        else
          mem_wr_mask <= X"c";
          muxedDataIn(16 + 15 downto 16) <= wr_data(0 + 15 downto 0);
        end if;
      else
        if wr_port_configuration = X"00000002" then
          if wr_addr_topbits = X"00000000" then
            mem_wr_mask <= X"1";
            muxedDataIn(0 + 7 downto 0) <= wr_data(0 + 7 downto 0);
          else
            if wr_addr_topbits = X"00000001" then
              mem_wr_mask <= X"2";
              muxedDataIn(8 + 7 downto 8) <= wr_data(0 + 7 downto 0);
            else
              if wr_addr_topbits = X"00000002" then
                mem_wr_mask <= X"4";
                muxedDataIn(16 + 7 downto 16) <= wr_data(0 + 7 downto 0);
              else
                mem_wr_mask <= X"8";
                muxedDataIn(24 + 7 downto 24) <= wr_data(0 + 7 downto 0);
              end if;
            end if;
          end if;
        end if;
      end if;
    end if;
  end process;
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:89)
  process (clk) is
  begin
    if rising_edge(clk) then
      rd_dout_sel <= wr_data(READ_ADDRESS_MSB_FROM_DATALSB + 1 downto READ_ADDRESS_MSB_FROM_DATALSB);
    end if;
  end process;
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:93)
  process (mem_dout, rd_port_configuration, rd_dout_sel) is
  begin
    rd_dout_muxed <= mem_dout;
    if rd_port_configuration = X"00000000" then
      rd_dout_muxed <= mem_dout;
    else
      if rd_port_configuration = X"00000001" then
        if (std_logic_vector'("0000000000000000000000000000000") & rd_dout_sel(0)) = X"00000000" then
          rd_dout_muxed(0 + 15 downto 0) <= mem_dout(0 + 15 downto 0);
        else
          rd_dout_muxed(0 + 15 downto 0) <= mem_dout(16 + 15 downto 16);
        end if;
      else
        if rd_port_configuration = X"00000002" then
          if rd_dout_sel = X"00000000" then
            rd_dout_muxed(0 + 7 downto 0) <= mem_dout(0 + 7 downto 0);
          else
            if rd_dout_sel = X"00000001" then
              rd_dout_muxed(0 + 7 downto 0) <= mem_dout(8 + 7 downto 8);
            else
              if rd_dout_sel = X"00000002" then
                rd_dout_muxed(0 + 7 downto 0) <= mem_dout(16 + 7 downto 16);
              else
                rd_dout_muxed(0 + 7 downto 0) <= mem_dout(24 + 7 downto 24);
              end if;
            end if;
          end if;
        end if;
      end if;
    end if;
  end process;
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:116)
  process (clk) is
  begin
    if rising_edge(clk) then
      rd_dout_additional_register <= rd_dout_muxed;
    end if;
  end process;
  
  -- Generated from always process in BlockRAM_1KB (BlockRAM_1KB.v:121)
  process (optional_register_enabled_configuration, rd_dout_additional_register, rd_dout_muxed) is
  begin
    if optional_register_enabled_configuration = '1' then
      final_dout <= rd_dout_additional_register;
    else
      final_dout <= rd_dout_muxed;
    end if;
  end process;
end architecture;

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
    addr0 : in std_logic_vector(7 downto 0);
    addr1 : in std_logic_vector(7 downto 0);
    clk0 : in std_logic;
    clk1 : in std_logic;
    csb0 : in std_logic;
    csb1 : in std_logic;
    din0 : in std_logic_vector(31 downto 0);
    dout0 : out std_logic_vector(31 downto 0);
    dout1 : out std_logic_vector(31 downto 0);
    web0 : in std_logic;
    wmask0 : in std_logic_vector(3 downto 0)
  );
end entity; 

-- Generated from Verilog module sram_1rw1r_32_256_8_sky130 (BlockRAM_1KB.v:132)
--   ADDR_WIDTH = 8
--   DATA_WIDTH = 32
--   DELAY = 3
--   NUM_WMASKS = 4
--   RAM_DEPTH = 256
architecture from_verilog of sram_1rw1r_32_256_8_sky130 is
begin
  dout0 <= (others => 'Z');
  dout1 <= (others => 'Z');
end architecture;

