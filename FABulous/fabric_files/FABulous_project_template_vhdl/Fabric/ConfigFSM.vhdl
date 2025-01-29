-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module ConfigFSM (ConfigFSM.v:1)
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
    FSM_Reset : in std_logic;
    FrameAddressRegister : out std_logic_vector(31 downto 0);
    LongFrameStrobe : out std_logic;
    RowSelect : out std_logic_vector(4 downto 0);
    WriteData : in std_logic_vector(31 downto 0);
    WriteStrobe : in std_logic;
    resetn : in std_logic
  );
end entity;

-- Generated from Verilog module ConfigFSM (ConfigFSM.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20
architecture from_verilog of ConfigFSM is
  signal FrameAddressRegister_Reg : std_logic_vector(31 downto 0);
  signal LongFrameStrobe_Reg : std_logic;
  signal RowSelect_Reg : std_logic_vector(4 downto 0);
  signal FrameShiftState : unsigned(4 downto 0);  -- Declared at ConfigFSM.v:20
  signal FrameStrobe : std_logic;  -- Declared at ConfigFSM.v:18
  signal oldFrameStrobe : std_logic;  -- Declared at ConfigFSM.v:83
  signal old_reset : std_logic;  -- Declared at ConfigFSM.v:24
  signal state : std_logic_vector(1 downto 0);  -- Declared at ConfigFSM.v:23

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

  -- Generated from always process in ConfigFSM (ConfigFSM.v:25)
  P_FSM: process (resetn, CLK) is
  begin
    if falling_edge(resetn) or rising_edge(CLK) then
      if (not resetn) = '1' then
        old_reset <= '0';
        state <= "00";
        FrameShiftState <= "00000";
        FrameAddressRegister_Reg <= X"00000000";
        FrameStrobe <= '0';
      else
        old_reset <= FSM_Reset;
        FrameStrobe <= '0';
        if (old_reset = '0') and (FSM_Reset = '1') then
          state <= "00";
          FrameShiftState <= "00000";
        else
          case state is
            when "00" =>
              if WriteStrobe = '1' then
                if WriteData = X"FAB0FAB1" then
                  state <= "01";
                end if;
              end if;
            when "01" =>
              if WriteStrobe = '1' then
                if WriteData(desync_flag) = '1' then
                  state <= "00";
                else
                  FrameAddressRegister_Reg <= WriteData;
                  FrameShiftState <= to_unsigned(NumberOfRows,FrameShiftState'length);
                  state <= "10";
                end if;
              end if;
            when "10" =>
              if WriteStrobe = '1' then
                FrameShiftState <= FrameShiftState - "00001";
                if Resize(FrameShiftState, 32) = X"00000001" then
                  FrameStrobe <= '1';
                  state <= "01";
                end if;
              end if;
            when others =>
              null;
          end case;
        end if;
      end if;
    end if;
  end process;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:75)
  process (WriteStrobe, FrameShiftState) is
  begin
    if WriteStrobe = '1' then
      RowSelect_Reg <= std_logic_vector(FrameShiftState);
    else
      RowSelect_Reg <= "11111";
    end if;
  end process;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:84)
  P_StrobeREG: process (resetn, CLK) is
  begin
    if falling_edge(resetn) or rising_edge(CLK) then
      if (not resetn) = '1' then
        oldFrameStrobe <= '0';
        LongFrameStrobe_Reg <= '0';
      else
        oldFrameStrobe <= FrameStrobe;
        LongFrameStrobe_Reg <= Boolean_To_Logic((FrameStrobe = '1') or (oldFrameStrobe = '1'));
      end if;
    end if;
  end process;
end architecture;
