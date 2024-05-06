-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module ConfigFSM (ConfigFSM_template.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20
entity ConfigFSM is
  generic (
    FrameBitsPerRow : integer := 32;
    NumberOfRows : integer := 16;
    RowSelectWidth : integer := 5;
    desync_flag : integer := 20
  );
  port (
    CLK : in std_logic;
    FrameAddressRegister : out std_logic_vector(31 downto 0);
    LongFrameStrobe : out std_logic;
    Reset : in std_logic;
    RowSelect : out std_logic_vector(4 downto 0);
    WriteData : in std_logic_vector(31 downto 0);
    WriteStrobe : in std_logic
  );
end entity; 

-- Generated from Verilog module ConfigFSM (ConfigFSM_template.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20
architecture from_verilog of ConfigFSM is
  signal FrameAddressRegister_Reg : std_logic_vector(31 downto 0);
  signal LongFrameStrobe_Reg : std_logic := '0';
  signal RowSelect_Reg : std_logic_vector(4 downto 0);
  signal FrameShiftState : unsigned(4 downto 0) := "00000";  -- Declared at ConfigFSM_template.v:19
  signal FrameStrobe : std_logic := '0';  -- Declared at ConfigFSM_template.v:17
  signal oldFrameStrobe : std_logic := '0';  -- Declared at ConfigFSM_template.v:74
  signal old_reset : std_logic := '0';  -- Declared at ConfigFSM_template.v:23
  signal state : std_logic_vector(1 downto 0) := "00";  -- Declared at ConfigFSM_template.v:22
  
  function Boolean_To_Logic(B : Boolean) return std_logic is
  begin
    if B then
      return '1';
    else
      return '0';
    end if;
  end function;
begin
  FrameAddressRegister <= FrameAddressRegister_Reg;
  LongFrameStrobe <= LongFrameStrobe_Reg;
  RowSelect <= RowSelect_Reg;
  
  -- Generated from always process in ConfigFSM (ConfigFSM_template.v:24)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      old_reset <= Reset;
      FrameStrobe <= '0';
      if (old_reset = '0') and (Reset = '1') then
        state <= "00";
        FrameShiftState <= "00000";
      else
        case state is
          when "00" =>
            if WriteStrobe = '1' then
              if WriteData = X"fab0fab1" then
                state <= "01";
              end if;
            end if;
          when "01" =>
            if WriteStrobe = '1' then
              if WriteData(20) = '1' then
                state <= "00";
              else
                FrameAddressRegister_Reg <= WriteData;
                FrameShiftState <= to_unsigned(NumberOfRows, FrameShiftState'length);
                state <= "10";
              end if;
            end if;
          when "10" =>
            if WriteStrobe = '1' then
              FrameShiftState <= FrameShiftState - "00001";
              if FrameShiftState = X"00000001" then
                FrameStrobe <= '1';
                state <= "01";
              end if;
            end if;
          when others =>
            null;
        end case;
      end if;
    end if;
  end process;
  
  -- Generated from always process in ConfigFSM (ConfigFSM_template.v:66)
  process (WriteStrobe, FrameShiftState) is
  begin
    if WriteStrobe = '1' then
      RowSelect_Reg <= std_logic_vector(FrameShiftState);
    else
      RowSelect_Reg <= "11111";
    end if;
  end process;
  
  -- Generated from always process in ConfigFSM (ConfigFSM_template.v:75)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      oldFrameStrobe <= FrameStrobe;
      LongFrameStrobe_Reg <= Boolean_To_Logic((FrameStrobe = '1') or (oldFrameStrobe = '1'));
    end if;
  end process;
end architecture;

