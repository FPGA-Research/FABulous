-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 12.0 (stable) ()

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module config_UART (config_UART.v:3)
--   ComRate = 217
--   DELAY_AFTER_START_BIT = 1
--   EVAL_COMMAND = 5
--   GET_BIT_0 = 2
--   GET_BIT_1 = 3
--   GET_BIT_2 = 4
--   GET_BIT_3 = 5
--   GET_BIT_4 = 6
--   GET_BIT_5 = 7
--   GET_BIT_6 = 8
--   GET_BIT_7 = 9
--   GET_COMMAND = 4
--   GET_DATA = 6
--   GET_ID_00 = 1
--   GET_ID_AA = 2
--   GET_ID_FF = 3
--   GET_STOP_BIT = 10
--   HIGH_NIBBLE = 1
--   IDLE = 0
--   LOW_NIBBLE = 0
--   MODE_AUTO = 0
--   MODE_BIN = 2
--   MODE_HEX = 1
--   Mode = 0
--   RX_TIMEOUT_VALUE = 16665
--   TEST_FILE_CHECKSUM = 326400
--   WAIT_FOR_START_BIT = 0
--   WORD_0 = 0
--   WORD_1 = 1
--   WORD_2 = 2
--   WORD_3 = 3

entity config_UART is
  port (
    CLK         : in    std_logic;
    ComActive   : out   std_logic;
    Command     : out   unsigned(7 downto 0);
    ReceiveLED  : out   std_logic;
    Rx          : in    std_logic;
    WriteData   : out   unsigned(31 downto 0);
    WriteStrobe : out   std_logic;
    reset_n     : in    std_logic
  );
end entity config_UART;

-- Generated from Verilog module config_UART (config_UART.v:3)
--   ComRate = 217
--   DELAY_AFTER_START_BIT = 1
--   EVAL_COMMAND = 5
--   GET_BIT_0 = 2
--   GET_BIT_1 = 3
--   GET_BIT_2 = 4
--   GET_BIT_3 = 5
--   GET_BIT_4 = 6
--   GET_BIT_5 = 7
--   GET_BIT_6 = 8
--   GET_BIT_7 = 9
--   GET_COMMAND = 4
--   GET_DATA = 6
--   GET_ID_00 = 1
--   GET_ID_AA = 2
--   GET_ID_FF = 3
--   GET_STOP_BIT = 10
--   HIGH_NIBBLE = 1
--   IDLE = 0
--   LOW_NIBBLE = 0
--   MODE_AUTO = 0
--   MODE_BIN = 2
--   MODE_HEX = 1
--   Mode = 0
--   RX_TIMEOUT_VALUE = 16665
--   TEST_FILE_CHECKSUM = 326400
--   WAIT_FOR_START_BIT = 0
--   WORD_0 = 0
--   WORD_1 = 1
--   WORD_2 = 2
--   WORD_3 = 3

architecture from_verilog of config_UART is

  function ASCII2HEX (
    ASCII : unsigned(7 downto 0)
  )
  return unsigned;

  signal ReceiveLED_Reg     : std_logic;
  signal WriteData_Reg      : unsigned(31 downto 0);
  signal WriteStrobe_Reg    : std_logic;
  signal tmp_ivl_10         : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_13         : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_15         : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_18         : unsigned(2 downto 0);  -- Temporary created at config_UART.v:133
  signal tmp_ivl_2          : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_20         : std_logic;             -- Temporary created at config_UART.v:603
  signal tmp_ivl_22         : std_logic;             -- Temporary created at config_UART.v:603
  signal tmp_ivl_24         : std_logic;             -- Temporary created at config_UART.v:603
  signal tmp_ivl_4          : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_7          : std_logic;             -- Temporary created at config_UART.v:601
  signal tmp_ivl_8          : std_logic;             -- Temporary created at config_UART.v:601
  signal blink              : unsigned(22 downto 0); -- Declared at config_UART.v:146
  signal byte_write_strobe  : std_logic;             -- Declared at config_UART.v:142
  signal com_count          : unsigned(11 downto 0); -- Declared at config_UART.v:97
  signal com_state          : unsigned(3 downto 0);  -- Declared at config_UART.v:113
  signal com_tick           : std_logic;             -- Declared at config_UART.v:98
  signal command_reg        : unsigned(7 downto 0);  -- Declared at config_UART.v:118
  signal crc_reg            : unsigned(19 downto 0); -- Declared at config_UART.v:144
  signal data_reg           : unsigned(7 downto 0);  -- Declared at config_UART.v:119
  signal get_word_state     : unsigned(1 downto 0);  -- Declared at config_UART.v:138
  signal hex_data           : unsigned(7 downto 0);  -- Declared at config_UART.v:94
  signal hex_value          : unsigned(4 downto 0);  -- Declared at config_UART.v:93
  signal hex_write_strobe   : std_logic;             -- Declared at config_UART.v:95
  signal high_reg           : unsigned(3 downto 0);  -- Declared at config_UART.v:92
  signal id_reg             : unsigned(23 downto 0); -- Declared at config_UART.v:117
  signal local_write_strobe : std_logic;             -- Declared at config_UART.v:140
  signal present_state      : unsigned(2 downto 0);  -- Declared at config_UART.v:135
  signal received_byte      : unsigned(7 downto 0);  -- Declared at config_UART.v:121
  signal received_state     : std_logic;             -- Declared at config_UART.v:91
  signal received_word      : unsigned(7 downto 0);  -- Declared at config_UART.v:114
  signal rx_local           : std_logic;             -- Declared at config_UART.v:115
  signal rx_timeout         : std_logic;             -- Declared at config_UART.v:123
  signal rx_timeout_counter : unsigned(14 downto 0); -- Declared at config_UART.v:124

  -- Generated from function ASCII2HEX at config_UART.v:34

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

  end function ASCII2HEX;

begin

  ReceiveLED    <= ReceiveLED_Reg;
  WriteData     <= WriteData_Reg;
  WriteStrobe   <= WriteStrobe_Reg;
  Command       <= command_reg;
  tmp_ivl_10    <= tmp_ivl_7 xnor tmp_ivl_8;
  tmp_ivl_13    <= tmp_ivl_4 and tmp_ivl_10;
  tmp_ivl_15    <= tmp_ivl_2 or tmp_ivl_13;
  tmp_ivl_7     <= command_reg(7);
  received_byte <= data_reg when tmp_ivl_15 = '1' else
                   hex_data;
  tmp_ivl_20    <= '1' when present_state = tmp_ivl_18 else
                   '0';
  ComActive     <= tmp_ivl_22 when tmp_ivl_20 = '1' else
                   tmp_ivl_24;
  tmp_ivl_18    <= "110";
  tmp_ivl_2     <= '0';
  tmp_ivl_22    <= '1';
  tmp_ivl_24    <= '0';
  tmp_ivl_4     <= '1';
  tmp_ivl_8     <= '0';

  -- Generated from always process in gen_L_hexmode (config_UART.v:400)
  process (CLK, reset_n) is
  begin

    if ((not reset_n) = '1') then
      received_state   <= '1';
      hex_data         <= x"00";
      high_reg         <= x"0";
      hex_write_strobe <= '0';
    elsif rising_edge(CLK) then
      if (present_state /= "110") then
        received_state <= '1';
      else
        if (((com_state = x"A") and (com_tick = '1')) and (hex_value(4) = '0')) then
          if (received_state = '1') then
            received_state <= '0';
          end if;
        else
          received_state <= '1';
        end if;
      end if;
      if (((com_state = x"A") and (com_tick = '1')) and (hex_value(4) = '0')) then
        if (received_state = '1') then
          high_reg         <= hex_value(0 + 3 downto 0);
          hex_write_strobe <= '0';
        else
          hex_data         <= high_reg & hex_value(0 + 3 downto 0);
          hex_write_strobe <= '1';
        end if;
      else
        hex_write_strobe <= '0';
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:148)
  p_sync : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        rx_local <= '1';
      else
        rx_local <= Rx;
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:156)
  p_com_en : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        com_count <= x"000";
        com_tick  <= '0';
      else
        if (com_state = x"0") then
          com_count <= x"06C";
          com_tick  <= '0';
        else
          if (Resize(com_count, 32) = x"00000000") then
            com_count <= x"0D9";
            com_tick  <= '1';
          else
            com_count <= com_count - x"001";
            com_tick  <= '0';
          end if;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:183)
  p_com : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        com_state     <= x"0";
        received_word <= x"00";
        id_reg        <= x"000000";
        command_reg   <= x"00";
      else

        case com_state is

          when X"0" =>

            if (rx_local = '0') then
              com_state     <= x"1";
              received_word <= x"00";
            end if;

          when X"1" =>

            if (com_tick = '1') then
              com_state <= x"2";
            end if;

          when X"2" =>

            if (com_tick = '1') then
              com_state        <= x"3";
              received_word(0) <= rx_local;
            end if;

          when X"3" =>

            if (com_tick = '1') then
              com_state        <= x"4";
              received_word(1) <= rx_local;
            end if;

          when X"4" =>

            if (com_tick = '1') then
              com_state        <= x"5";
              received_word(2) <= rx_local;
            end if;

          when X"5" =>

            if (com_tick = '1') then
              com_state        <= x"6";
              received_word(3) <= rx_local;
            end if;

          when X"6" =>

            if (com_tick = '1') then
              com_state        <= x"7";
              received_word(4) <= rx_local;
            end if;

          when X"7" =>

            if (com_tick = '1') then
              com_state        <= x"8";
              received_word(5) <= rx_local;
            end if;

          when X"8" =>

            if (com_tick = '1') then
              com_state        <= x"9";
              received_word(6) <= rx_local;
            end if;

          when X"9" =>

            if (com_tick = '1') then
              com_state        <= x"A";
              received_word(7) <= rx_local;
            end if;

          when X"a" =>

            if (com_tick = '1') then
              com_state <= x"0";
            end if;

          when others =>

            com_state <= x"0";

        end case;

        if ((com_state = x"A") and (com_tick = '1')) then

          case present_state is

            when "001" =>

              id_reg(16 + 7 downto 16) <= received_word;

            when "010" =>

              id_reg(8 + 7 downto 8) <= received_word;

            when "011" =>

              id_reg(0 + 7 downto 0) <= received_word;

            when "100" =>

              command_reg <= received_word;

            when "110" =>

              data_reg <= received_word;

            when others =>

              null;

          end case;

        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:308)
  p_fsm : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        present_state <= "000";
      else

        case present_state is

          when "000" =>

            if ((com_state = x"0") and (rx_local = '0')) then
              present_state <= "001";
            end if;

          when "001" =>

            if (rx_timeout = '1') then
              present_state <= "000";
            else
              if ((com_state = x"A") and (com_tick = '1')) then
                present_state <= "010";
              end if;
            end if;

          when "010" =>

            if (rx_timeout = '1') then
              present_state <= "000";
            else
              if ((com_state = x"A") and (com_tick = '1')) then
                present_state <= "011";
              end if;
            end if;

          when "011" =>

            if (rx_timeout = '1') then
              present_state <= "000";
            else
              if ((com_state = x"A") and (com_tick = '1')) then
                present_state <= "100";
              end if;
            end if;

          when "100" =>

            if (rx_timeout = '1') then
              present_state <= "000";
            else
              if ((com_state = x"A") and (com_tick = '1')) then
                present_state <= "101";
              end if;
            end if;

          when "101" =>

            if ((id_reg = x"00AAFF") and ((command_reg(0 + 6 downto 0) = "0000001") or (command_reg(0 + 6 downto 0) = "0000010"))) then
              present_state <= "110";
            else
              present_state <= "000";
            end if;

          when "110" =>

            if (rx_timeout = '1') then
              present_state <= "000";
            end if;

          when others =>

            present_state <= "000";

        end case;

      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:447)
  p_checksum : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        crc_reg <= x"4FB00";
        blink   <= "00000000000000000000000";
      else
        if (present_state = "100") then
          crc_reg <= x"00000";
        else
          if (False or (True and (command_reg(7) = '1'))) then
            if (((((com_state = x"A") and (com_tick = '1')) and (hex_value(4) = '0')) and (present_state = "110")) and (received_state = '0')) then
              crc_reg <= crc_reg + (x"000" & high_reg & hex_value(0 + 3 downto 0));
            end if;
          else
            if (((com_state = x"A") and (com_tick = '1')) and (present_state = "110")) then
              crc_reg <= crc_reg + (x"000" & received_word);
            end if;
          end if;
        end if;
        if (present_state = "110") then
          ReceiveLED_Reg <= '1';
        else
          if ((present_state = "000") and (crc_reg /= x"4FB00")) then
            ReceiveLED_Reg <= blink(22);
          else
            ReceiveLED_Reg <= '0';
          end if;
        end if;
        blink <= blink - "00000000000000000000001";
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:497)
  p_bus : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        local_write_strobe <= '0';
        byte_write_strobe  <= '0';
      else
        if (present_state = "101") then
          local_write_strobe <= '0';
        else
          if (((present_state = "110") and (com_state = x"A")) and (com_tick = '1')) then
            local_write_strobe <= '1';
          else
            local_write_strobe <= '0';
          end if;
        end if;
        if (False or (True and (command_reg(7) = '0'))) then
          byte_write_strobe <= local_write_strobe;
        else
          byte_write_strobe <= hex_write_strobe;
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:533)
  p_wordmode : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        get_word_state  <= "00";
        WriteData_Reg   <= x"00000000";
        WriteStrobe_Reg <= '0';
      else
        if (present_state = "101") then
          get_word_state <= "00";
          WriteData_Reg  <= x"00000000";
        else

          case get_word_state is

            when "00" =>

              if (byte_write_strobe = '1') then
                WriteData_Reg(24 + 7 downto 24) <= received_byte;
                get_word_state                  <= "01";
              end if;

            when "01" =>

              if (byte_write_strobe = '1') then
                WriteData_Reg(16 + 7 downto 16) <= received_byte;
                get_word_state                  <= "10";
              end if;

            when "10" =>

              if (byte_write_strobe = '1') then
                WriteData_Reg(8 + 7 downto 8) <= received_byte;
                get_word_state                <= "11";
              end if;

            when "11" =>

              if (byte_write_strobe = '1') then
                WriteData_Reg(0 + 7 downto 0) <= received_byte;
                get_word_state                <= "00";
              end if;

            when others =>

              get_word_state <= "00";

          end case;

        end if;
        if ((byte_write_strobe = '1') and (get_word_state = "11")) then
          WriteStrobe_Reg <= '1';
        else
          WriteStrobe_Reg <= '0';
        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in config_UART (config_UART.v:605)
  p_timeout : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        rx_timeout_counter <= "100000100011001";
        rx_timeout         <= '0';
      else
        if ((present_state = "000") or (com_state = x"A")) then
          rx_timeout_counter <= "100000100011001";
          rx_timeout         <= '0';
        else
          if (Resize(rx_timeout_counter, 32) > x"00000000") then
            rx_timeout_counter <= rx_timeout_counter - "000000000000001";
            rx_timeout         <= '0';
          else
            rx_timeout <= '1';
          end if;
        end if;
      end if;
    end if;

  end process;

end architecture from_verilog;
