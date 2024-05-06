-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module config_UART (config_UART.v:1)
--   ComRate = 217
--   DelayAfterStartBit = 1
--   EvalCommand = 5
--   GetBit0 = 2
--   GetBit1 = 3
--   GetBit2 = 4
--   GetBit3 = 5
--   GetBit4 = 6
--   GetBit5 = 7
--   GetBit6 = 8
--   GetBit7 = 9
--   GetCommand = 4
--   GetData = 6
--   GetID_00 = 1
--   GetID_AA = 2
--   GetID_FF = 3
--   GetStopBit = 10
--   HighNibble = 1
--   Idle = 0
--   LowNibble = 0
--   Mode = 0
--   TestFileChecksum = 326400
--   TimeToSendValue = 16776
--   WaitForStartBit = 0
--   Word0 = 0
--   Word1 = 1
--   Word2 = 2
--   Word3 = 3
entity config_UART is
  port (
    CLK : in std_logic;
    ComActive : out std_logic;
    Command : out unsigned(7 downto 0);
    ReceiveLED : out std_logic;
    Rx : in std_logic;
    WriteData : out unsigned(31 downto 0);
    WriteStrobe : out std_logic
  );
end entity; 

-- Generated from Verilog module config_UART (config_UART.v:1)
--   ComRate = 217
--   DelayAfterStartBit = 1
--   EvalCommand = 5
--   GetBit0 = 2
--   GetBit1 = 3
--   GetBit2 = 4
--   GetBit3 = 5
--   GetBit4 = 6
--   GetBit5 = 7
--   GetBit6 = 8
--   GetBit7 = 9
--   GetCommand = 4
--   GetData = 6
--   GetID_00 = 1
--   GetID_AA = 2
--   GetID_FF = 3
--   GetStopBit = 10
--   HighNibble = 1
--   Idle = 0
--   LowNibble = 0
--   Mode = 0
--   TestFileChecksum = 326400
--   TimeToSendValue = 16776
--   WaitForStartBit = 0
--   Word0 = 0
--   Word1 = 1
--   Word2 = 2
--   Word3 = 3
architecture from_verilog of config_UART is
  function ASCII2HEX (
    ASCII : unsigned(7 downto 0)
  ) 
  return unsigned;
  
  signal ReceiveLED_Reg : std_logic;
  signal WriteData_Reg : unsigned(31 downto 0);
  signal WriteStrobe_Reg : std_logic;
  signal ByteWriteStrobe : std_logic;  -- Declared at config_UART.v:97
  signal CRCReg : unsigned(19 downto 0) := X"4fb00";  -- Declared at config_UART.v:103
  signal ComCount : unsigned(11 downto 0);  -- Declared at config_UART.v:62
  signal ComState : unsigned(3 downto 0) := X"0";  -- Declared at config_UART.v:67
  signal ComTick : std_logic;  -- Declared at config_UART.v:63
  signal Command_Reg : unsigned(7 downto 0);  -- Declared at config_UART.v:77
  signal Data_Reg : unsigned(7 downto 0);  -- Declared at config_UART.v:78
  signal GetWordState : unsigned(1 downto 0) := "00";  -- Declared at config_UART.v:93
  signal HexData : unsigned(7 downto 0);  -- Declared at config_UART.v:59
  signal HexValue : unsigned(4 downto 0);  -- Declared at config_UART.v:58
  signal HexWriteStrobe : std_logic;  -- Declared at config_UART.v:60
  signal HighReg : unsigned(3 downto 0);  -- Declared at config_UART.v:57
  signal ID_Reg : unsigned(23 downto 0);  -- Declared at config_UART.v:73
  signal LocalWriteStrobe : std_logic;  -- Declared at config_UART.v:95
  signal PresentState : unsigned(2 downto 0) := "000";  -- Declared at config_UART.v:88
  signal ReceiveState : std_logic := '1';  -- Declared at config_UART.v:56
  signal ReceivedByte : unsigned(7 downto 0);  -- Declared at config_UART.v:80
  signal ReceivedWord : unsigned(7 downto 0);  -- Declared at config_UART.v:68
  signal RxLocal : std_logic;  -- Declared at config_UART.v:69
  signal TimeToSend : std_logic;  -- Declared at config_UART.v:82
  signal TimeToSendCounter : unsigned(14 downto 0);  -- Declared at config_UART.v:83
  signal tmp_ivl_10 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_13 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_15 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_18 : unsigned(31 downto 0);  -- Temporary created at config_UART.v:399
  signal tmp_ivl_2 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_21 : unsigned(28 downto 0);  -- Temporary created at config_UART.v:399
  signal tmp_ivl_22 : unsigned(31 downto 0);  -- Temporary created at config_UART.v:87
  signal tmp_ivl_24 : std_logic;  -- Temporary created at config_UART.v:399
  signal tmp_ivl_26 : std_logic;  -- Temporary created at config_UART.v:399
  signal tmp_ivl_28 : std_logic;  -- Temporary created at config_UART.v:399
  signal tmp_ivl_4 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_7 : std_logic;  -- Temporary created at config_UART.v:396
  signal tmp_ivl_8 : std_logic;  -- Temporary created at config_UART.v:396
  signal b_counter : unsigned(19 downto 0) := X"4fb00";  -- Declared at config_UART.v:103
  signal blink : unsigned(22 downto 0) := "00000000000000000000000";  -- Declared at config_UART.v:105
  
  -- Generated from function ASCII2HEX at config_UART.v:22
  function ASCII2HEX (
    ASCII : unsigned(7 downto 0)
  ) 
  return unsigned is
    variable ASCII2HEX_Result : unsigned(4 downto 0);
  begin
    case ASCII is
      when X"30" =>
        ASCII2HEX_Result := "00000";
      when X"31" =>
        ASCII2HEX_Result := "00001";
      when X"32" =>
        ASCII2HEX_Result := "00010";
      when X"33" =>
        ASCII2HEX_Result := "00011";
      when X"34" =>
        ASCII2HEX_Result := "00100";
      when X"35" =>
        ASCII2HEX_Result := "00101";
      when X"36" =>
        ASCII2HEX_Result := "00110";
      when X"37" =>
        ASCII2HEX_Result := "00111";
      when X"38" =>
        ASCII2HEX_Result := "01000";
      when X"39" =>
        ASCII2HEX_Result := "01001";
      when X"41" =>
        ASCII2HEX_Result := "01010";
      when X"61" =>
        ASCII2HEX_Result := "01010";
      when X"42" =>
        ASCII2HEX_Result := "01011";
      when X"62" =>
        ASCII2HEX_Result := "01011";
      when X"43" =>
        ASCII2HEX_Result := "01100";
      when X"63" =>
        ASCII2HEX_Result := "01100";
      when X"44" =>
        ASCII2HEX_Result := "01101";
      when X"64" =>
        ASCII2HEX_Result := "01101";
      when X"45" =>
        ASCII2HEX_Result := "01110";
      when X"65" =>
        ASCII2HEX_Result := "01110";
      when X"46" =>
        ASCII2HEX_Result := "01111";
      when X"66" =>
        ASCII2HEX_Result := "01111";
      when others =>
        ASCII2HEX_Result := "10000";
    end case;
    return ASCII2HEX_Result;
  end function;
begin
  ReceiveLED <= ReceiveLED_Reg;
  WriteData <= WriteData_Reg;
  WriteStrobe <= WriteStrobe_Reg;
  Command <= Command_Reg;
  tmp_ivl_10 <= tmp_ivl_7 xnor tmp_ivl_8;
  tmp_ivl_13 <= tmp_ivl_4 and tmp_ivl_10;
  tmp_ivl_15 <= tmp_ivl_2 or tmp_ivl_13;
  tmp_ivl_7 <= Command_Reg(7);
  ReceivedByte <= Data_Reg when tmp_ivl_15 = '1' else HexData;
  tmp_ivl_18 <= tmp_ivl_21 & PresentState;
  tmp_ivl_24 <= '1' when tmp_ivl_18 = tmp_ivl_22 else '0';
  ComActive <= tmp_ivl_26 when tmp_ivl_24 = '1' else tmp_ivl_28;
  tmp_ivl_2 <= '0';
  tmp_ivl_21 <= "00000000000000000000000000000";
  tmp_ivl_22 <= X"00000006";
  tmp_ivl_26 <= '1';
  tmp_ivl_28 <= '0';
  tmp_ivl_4 <= '1';
  tmp_ivl_8 <= '0';
  
  -- Generated from always process in L_hexmode (config_UART.v:278)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if Resize(PresentState, 32) /= X"00000006" then
        ReceiveState <= '1';
      else
        if ((Resize(ComState, 32) = X"0000000a") and (ComTick = '1')) and (HexValue(4) = '0') then
          if (unsigned'("0000000000000000000000000000000") & ReceiveState) = X"00000001" then
            ReceiveState <= '0';
          end if;
        else
          ReceiveState <= '1';
        end if;
      end if;
      if ((Resize(ComState, 32) = X"0000000a") and (ComTick = '1')) and (HexValue(4) = '0') then
        if (unsigned'("0000000000000000000000000000000") & ReceiveState) = X"00000001" then
          HighReg <= HexValue(0 + 3 downto 0);
          HexWriteStrobe <= '0';
        else
          HexData <= HighReg & HexValue(0 + 3 downto 0);
          HexWriteStrobe <= '1';
        end if;
      else
        HexWriteStrobe <= '0';
      end if;
    end if;
  end process;
  -- Removed one empty process
  
  -- Removed one empty process
  
  
  -- Generated from always process in config_UART (config_UART.v:113)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      RxLocal <= Rx;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:118)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if Resize(ComState, 32) = X"00000000" then
        ComCount <= X"06c";
        ComTick <= '0';
      else
        if Resize(ComCount, 32) = X"00000000" then
          ComCount <= X"0d9";
          ComTick <= '1';
        else
          ComCount <= ComCount - X"001";
          ComTick <= '0';
        end if;
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:132)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      case ComState is
        when X"0" =>
          if RxLocal = '0' then
            ComState <= X"1";
            ReceivedWord <= X"00";
          end if;
        when X"1" =>
          if ComTick = '1' then
            ComState <= X"2";
          end if;
        when X"2" =>
          if ComTick = '1' then
            ComState <= X"3";
            ReceivedWord(0) <= RxLocal;
          end if;
        when X"3" =>
          if ComTick = '1' then
            ComState <= X"4";
            ReceivedWord(1) <= RxLocal;
          end if;
        when X"4" =>
          if ComTick = '1' then
            ComState <= X"5";
            ReceivedWord(2) <= RxLocal;
          end if;
        when X"5" =>
          if ComTick = '1' then
            ComState <= X"6";
            ReceivedWord(3) <= RxLocal;
          end if;
        when X"6" =>
          if ComTick = '1' then
            ComState <= X"7";
            ReceivedWord(4) <= RxLocal;
          end if;
        when X"7" =>
          if ComTick = '1' then
            ComState <= "1000";
            ReceivedWord(5) <= RxLocal;
          end if;
        when X"8" =>
          if ComTick = '1' then
            ComState <= "1001";
            ReceivedWord(6) <= RxLocal;
          end if;
        when X"9" =>
          if ComTick = '1' then
            ComState <= "1010";
            ReceivedWord(7) <= RxLocal;
          end if;
        when X"a" =>
          if ComTick = '1' then
            ComState <= X"0";
          end if;
        when others =>
          null;
      end case;
      if (Resize(ComState, 32) = X"0000000a") and (ComTick = '1') then
        case PresentState is
          when "001" =>
            ID_Reg(16 + 7 downto 16) <= ReceivedWord;
          when "010" =>
            ID_Reg(8 + 7 downto 8) <= ReceivedWord;
          when "011" =>
            ID_Reg(0 + 7 downto 0) <= ReceivedWord;
          when "100" =>
            Command_Reg <= ReceivedWord;
          when "110" =>
            Data_Reg <= ReceivedWord;
          when others =>
            null;
        end case;
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:218)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      case PresentState is
        when "000" =>
          if (Resize(ComState, 32) = X"00000000") and (RxLocal = '0') then
            PresentState <= "001";
          end if;
        when "001" =>
          if TimeToSend = '1' then
            PresentState <= "000";
          else
            if (Resize(ComState, 32) = X"0000000a") and (ComTick = '1') then
              PresentState <= "010";
            end if;
          end if;
        when "010" =>
          if TimeToSend = '1' then
            PresentState <= "000";
          else
            if (Resize(ComState, 32) = X"0000000a") and (ComTick = '1') then
              PresentState <= "011";
            end if;
          end if;
        when "011" =>
          if TimeToSend = '1' then
            PresentState <= "000";
          else
            if (Resize(ComState, 32) = X"0000000a") and (ComTick = '1') then
              PresentState <= "100";
            end if;
          end if;
        when "100" =>
          if TimeToSend = '1' then
            PresentState <= "000";
          else
            if (Resize(ComState, 32) = X"0000000a") and (ComTick = '1') then
              PresentState <= "101";
            end if;
          end if;
        when "101" =>
          if (ID_Reg = X"00aaff") and ((Command_Reg(0 + 6 downto 0) = "0000001") or (Command_Reg(0 + 6 downto 0) = "0000010")) then
            PresentState <= "110";
          else
            PresentState <= "000";
          end if;
        when "110" =>
          if TimeToSend = '1' then
            PresentState <= "000";
          end if;
        when others =>
          null;
      end case;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:304)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if Resize(PresentState, 32) = X"00000004" then
        CRCReg <= X"00000";
        b_counter <= X"00000";
      else
        if False or (True and (Command_Reg(7) = '1')) then
          if ((((Resize(ComState, 32) = X"0000000a") and (ComTick = '1')) and (HexValue(4) = '0')) and (Resize(PresentState, 32) = X"00000006")) and ((unsigned'("0000000000000000000000000000000") & ReceiveState) = X"00000000") then
            CRCReg <= CRCReg + Resize((HighReg & HexValue(0 + 3 downto 0)), 20);
            b_counter <= b_counter + X"00001";
          end if;
        else
          if ((Resize(ComState, 32) = X"0000000a") and (ComTick = '1')) and (Resize(PresentState, 32) = X"00000006") then
            CRCReg <= CRCReg + Resize(ReceivedWord, 20);
            b_counter <= b_counter + X"00001";
          end if;
        end if;
      end if;
      if Resize(PresentState, 32) = X"00000006" then
        ReceiveLED_Reg <= '1';
      else
        if (Resize(PresentState, 32) = X"00000000") and (CRCReg /= X"4fb00") then
          ReceiveLED_Reg <= blink(22);
        else
          ReceiveLED_Reg <= '0';
        end if;
      end if;
      blink <= blink - "00000000000000000000001";
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:335)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if Resize(PresentState, 32) = X"00000005" then
        LocalWriteStrobe <= '0';
      else
        if ((Resize(PresentState, 32) = X"00000006") and (Resize(ComState, 32) = X"0000000a")) and (ComTick = '1') then
          LocalWriteStrobe <= '1';
        else
          LocalWriteStrobe <= '0';
        end if;
      end if;
      if False or (True and (Command_Reg(7) = '0')) then
        ByteWriteStrobe <= LocalWriteStrobe;
      else
        ByteWriteStrobe <= HexWriteStrobe;
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:354)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if Resize(PresentState, 32) = X"00000005" then
        GetWordState <= "00";
        WriteData_Reg <= X"00000000";
      else
        case GetWordState is
          when "00" =>
            if ByteWriteStrobe = '1' then
              WriteData_Reg(24 + 7 downto 24) <= ReceivedByte;
              GetWordState <= "01";
            end if;
          when "01" =>
            if ByteWriteStrobe = '1' then
              WriteData_Reg(16 + 7 downto 16) <= ReceivedByte;
              GetWordState <= "10";
            end if;
          when "10" =>
            if ByteWriteStrobe = '1' then
              WriteData_Reg(8 + 7 downto 8) <= ReceivedByte;
              GetWordState <= "11";
            end if;
          when "11" =>
            if ByteWriteStrobe = '1' then
              WriteData_Reg(0 + 7 downto 0) <= ReceivedByte;
              GetWordState <= "00";
            end if;
          when others =>
            null;
        end case;
      end if;
      if (ByteWriteStrobe = '1') and (Resize(GetWordState, 32) = X"00000003") then
        WriteStrobe_Reg <= '1';
      else
        WriteStrobe_Reg <= '0';
      end if;
    end if;
  end process;
  
  -- Generated from always process in config_UART (config_UART.v:401)
  process (CLK) is
  begin
    if rising_edge(CLK) then
      if (Resize(PresentState, 32) = X"00000000") or (Resize(ComState, 32) = X"0000000a") then
        TimeToSendCounter <= "100000110001000";
        TimeToSend <= '0';
      else
        if Resize(TimeToSendCounter, 32) > X"00000000" then
          TimeToSendCounter <= TimeToSendCounter - "000000000000001";
          TimeToSend <= '0';
        else
          TimeToSendCounter <= TimeToSendCounter;
          TimeToSend <= '1';
        end if;
      end if;
    end if;
  end process;
end architecture;

