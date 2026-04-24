-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (devel) (s20221226-518-g94d9d1951)

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

entity config_uart is
  generic (
    comrate : integer := 217;
    mode    : integer := 0
  );
  port (
    clk         : in    std_logic;
    comactive   : out   std_logic;
    command     : out   unsigned(7 downto 0);
    receiveled  : out   std_logic;
    rx          : in    std_logic;
    writedata   : out   unsigned(31 downto 0);
    writestrobe : out   std_logic;
    resetn      : in    std_logic
  );
end entity config_uart;

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

architecture from_verilog of config_uart is

  function ascii2hex (
    ascii : unsigned(7 downto 0)
  )
    return unsigned;

  signal receiveled_reg    : std_logic;
  signal writedata_reg     : unsigned(31 downto 0);
  signal writestrobe_reg   : std_logic;
  signal bytewritestrobe   : std_logic;             -- Declared at config_UART.v:98
  signal crcreg            : unsigned(19 downto 0); -- Declared at config_UART.v:104
  signal comcount          : unsigned(11 downto 0); -- Declared at config_UART.v:63
  signal comstate          : unsigned(3 downto 0);  -- Declared at config_UART.v:68
  signal comtick           : std_logic;             -- Declared at config_UART.v:64
  signal command_reg       : unsigned(7 downto 0);  -- Declared at config_UART.v:78
  signal data_reg          : unsigned(7 downto 0);  -- Declared at config_UART.v:79
  signal getwordstate      : unsigned(1 downto 0);  -- Declared at config_UART.v:94
  signal hexdata           : unsigned(7 downto 0);  -- Declared at config_UART.v:60
  signal hexvalue          : unsigned(4 downto 0);  -- Declared at config_UART.v:59
  signal hexwritestrobe    : std_logic;             -- Declared at config_UART.v:61
  signal highreg           : unsigned(3 downto 0);  -- Declared at config_UART.v:58
  signal id_reg            : unsigned(23 downto 0); -- Declared at config_UART.v:74
  signal localwritestrobe  : std_logic;             -- Declared at config_UART.v:96
  signal presentstate      : unsigned(2 downto 0);  -- Declared at config_UART.v:89
  signal receivestate      : std_logic;             -- Declared at config_UART.v:57
  signal receivedbyte      : unsigned(7 downto 0);  -- Declared at config_UART.v:81
  signal receivedword      : unsigned(7 downto 0);  -- Declared at config_UART.v:69
  signal rxlocal           : std_logic;             -- Declared at config_UART.v:70
  signal start_reg         : unsigned(31 downto 0); -- Declared at config_UART.v:75
  signal timetosend        : std_logic;             -- Declared at config_UART.v:83
  signal timetosendcounter : unsigned(14 downto 0); -- Declared at config_UART.v:84
  signal tmp_ivl_10        : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_13        : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_15        : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_18        : unsigned(31 downto 0); -- Temporary created at config_UART.v:437
  signal tmp_ivl_2         : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_21        : unsigned(28 downto 0); -- Temporary created at config_UART.v:437
  signal tmp_ivl_22        : unsigned(31 downto 0); -- Temporary created at config_UART.v:88
  signal tmp_ivl_24        : std_logic;             -- Temporary created at config_UART.v:437
  signal tmp_ivl_26        : std_logic;             -- Temporary created at config_UART.v:437
  signal tmp_ivl_28        : std_logic;             -- Temporary created at config_UART.v:437
  signal tmp_ivl_4         : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_7         : std_logic;             -- Temporary created at config_UART.v:434
  signal tmp_ivl_8         : std_logic;             -- Temporary created at config_UART.v:434
  signal b_counter         : unsigned(19 downto 0); -- Declared at config_UART.v:104
  signal blink             : unsigned(22 downto 0); -- Declared at config_UART.v:106

  -- Generated from function ASCII2HEX at config_UART.v:23

  function ascii2hex (
    ascii : unsigned(7 downto 0)
  )
    return unsigned is

    variable ascii2hex_result : unsigned(4 downto 0);

  begin

    case ascii is

      when X"30" =>

        ascii2hex_result := "00000";

      when X"31" =>

        ascii2hex_result := "00001";

      when X"32" =>

        ascii2hex_result := "00010";

      when X"33" =>

        ascii2hex_result := "00011";

      when X"34" =>

        ascii2hex_result := "00100";

      when X"35" =>

        ascii2hex_result := "00101";

      when X"36" =>

        ascii2hex_result := "00110";

      when X"37" =>

        ascii2hex_result := "00111";

      when X"38" =>

        ascii2hex_result := "01000";

      when X"39" =>

        ascii2hex_result := "01001";

      when X"41" =>

        ascii2hex_result := "01010";

      when X"61" =>

        ascii2hex_result := "01010";

      when X"42" =>

        ascii2hex_result := "01011";

      when X"62" =>

        ascii2hex_result := "01011";

      when X"43" =>

        ascii2hex_result := "01100";

      when X"63" =>

        ascii2hex_result := "01100";

      when X"44" =>

        ascii2hex_result := "01101";

      when X"64" =>

        ascii2hex_result := "01101";

      when X"45" =>

        ascii2hex_result := "01110";

      when X"65" =>

        ascii2hex_result := "01110";

      when X"46" =>

        ascii2hex_result := "01111";

      when X"66" =>

        ascii2hex_result := "01111";

      when others =>

        ascii2hex_result := "10000";

    end case;

    return ascii2hex_result;

  end function ascii2hex;

begin

  receiveled   <= receiveled_reg;
  writedata    <= writedata_reg;
  writestrobe  <= writestrobe_reg;
  command      <= command_reg;
  tmp_ivl_10   <= tmp_ivl_7 xnor tmp_ivl_8;
  tmp_ivl_13   <= tmp_ivl_4 and tmp_ivl_10;
  tmp_ivl_15   <= tmp_ivl_2 or tmp_ivl_13;
  tmp_ivl_7    <= command_reg(7);
  receivedbyte <= data_reg when tmp_ivl_15 = '1' else
                  hexdata;
  tmp_ivl_18   <= tmp_ivl_21 & presentstate;
  tmp_ivl_24   <= '1' when tmp_ivl_18 = tmp_ivl_22 else
                  '0';
  comactive    <= tmp_ivl_26 when tmp_ivl_24 = '1' else
                  tmp_ivl_28;
  tmp_ivl_2    <= '0';
  tmp_ivl_21   <= "00000000000000000000000000000";
  tmp_ivl_22   <= x"00000006";
  tmp_ivl_26   <= '1';
  tmp_ivl_28   <= '0';
  tmp_ivl_4    <= '1';
  tmp_ivl_8    <= '0';

  -- Generated from always process in L_hexmode (config_UART.v:293)
  process_001 : process (clk, resetn) is
  begin

    if ((not resetn) = '1') then
      receivestate   <= '1';
      hexdata        <= x"00";
      highreg        <= x"0";
      hexwritestrobe <= '0';
    elsif rising_edge(clk) then
      if (Resize(presentstate, 32) /= x"00000006") then
        receivestate <= '1';
      else
        if (((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) and (hexvalue(4) = '0')) then
          if ((unsigned'("0000000000000000000000000000000") & receivestate) = x"00000001") then
            receivestate <= '0';
          end if;
        else
          receivestate <= '1';
        end if;
      end if;
      if (((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) and (hexvalue(4) = '0')) then
        if ((unsigned'("0000000000000000000000000000000") & receivestate) = x"00000001") then
          highreg        <= hexvalue(0 + 3 downto 0);
          hexwritestrobe <= '0';
        else
          hexdata        <= highreg & hexvalue(0 + 3 downto 0);
          hexwritestrobe <= '1';
        end if;
      else
        hexwritestrobe <= '0';
      end if;
    end if;

  end process process_001;

  -- Generated from always process in config_UART (config_UART.v:108)
  p_sync : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        rxlocal <= '1';
      else
        rxlocal <= rx;
      end if;
    end if;

  end process p_sync;

  -- Generated from always process in config_UART (config_UART.v:116)
  p_com_en : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        comcount <= x"000";
        comtick  <= '0';
      else
        if (Resize(comstate, 32) = x"00000000") then
          comcount <= x"06C";
          comtick  <= '0';
        else
          if (Resize(comcount, 32) = x"00000000") then
            comcount <= x"0D9";
            comtick  <= '1';
          else
            comcount <= comcount - x"001";
            comtick  <= '0';
          end if;
        end if;
      end if;
    end if;

  end process p_com_en;

  -- Generated from always process in config_UART (config_UART.v:135)
  p_com : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        comstate     <= x"0";
        receivedword <= x"00";
        id_reg       <= x"000000";
        start_reg    <= x"00000000";
        command_reg  <= x"00";
      else

        case comstate is

          when X"0" =>

            if (rxlocal = '0') then
              comstate     <= x"1";
              receivedword <= x"00";
            end if;

          when X"1" =>

            if (comtick = '1') then
              comstate <= x"2";
            end if;

          when X"2" =>

            if (comtick = '1') then
              comstate        <= x"3";
              receivedword(0) <= rxlocal;
            end if;

          when X"3" =>

            if (comtick = '1') then
              comstate        <= x"4";
              receivedword(1) <= rxlocal;
            end if;

          when X"4" =>

            if (comtick = '1') then
              comstate        <= x"5";
              receivedword(2) <= rxlocal;
            end if;

          when X"5" =>

            if (comtick = '1') then
              comstate        <= x"6";
              receivedword(3) <= rxlocal;
            end if;

          when X"6" =>

            if (comtick = '1') then
              comstate        <= x"7";
              receivedword(4) <= rxlocal;
            end if;

          when X"7" =>

            if (comtick = '1') then
              comstate        <= "1000";
              receivedword(5) <= rxlocal;
            end if;

          when X"8" =>

            if (comtick = '1') then
              comstate        <= "1001";
              receivedword(6) <= rxlocal;
            end if;

          when X"9" =>

            if (comtick = '1') then
              comstate        <= "1010";
              receivedword(7) <= rxlocal;
            end if;

          when X"a" =>

            if (comtick = '1') then
              comstate <= x"0";
            end if;

          when others =>

            null;

        end case;

        if ((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) then

          case presentstate is

            when "001" =>

              id_reg(16 + 7 downto 16) <= receivedword;

            when "010" =>

              id_reg(8 + 7 downto 8) <= receivedword;

            when "011" =>

              id_reg(0 + 7 downto 0) <= receivedword;

            when "100" =>

              command_reg <= receivedword;

            when "110" =>

              data_reg <= receivedword;

            when others =>

              null;

          end case;

        end if;
      end if;
    end if;

  end process p_com;

  -- Generated from always process in config_UART (config_UART.v:229)
  p_fsm : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        presentstate <= "000";
      else

        case presentstate is

          when "000" =>

            if ((Resize(comstate, 32) = x"00000000") and (rxlocal = '0')) then
              presentstate <= "001";
            end if;

          when "001" =>

            if (timetosend = '1') then
              presentstate <= "000";
            else
              if ((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) then
                presentstate <= "010";
              end if;
            end if;

          when "010" =>

            if (timetosend = '1') then
              presentstate <= "000";
            else
              if ((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) then
                presentstate <= "011";
              end if;
            end if;

          when "011" =>

            if (timetosend = '1') then
              presentstate <= "000";
            else
              if ((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) then
                presentstate <= "100";
              end if;
            end if;

          when "100" =>

            if (timetosend = '1') then
              presentstate <= "000";
            else
              if ((Resize(comstate, 32) = x"0000000A") and (comtick = '1')) then
                presentstate <= "101";
              end if;
            end if;

          when "101" =>

            if (
                (id_reg = x"00AAFF") and
                (
                  (command_reg(0 + 6 downto 0) = "0000001") or
                  (command_reg(0 + 6 downto 0) = "0000010")
                )
              ) then
              presentstate <= "110";
            else
              presentstate <= "000";
            end if;

          when "110" =>

            if (timetosend = '1') then
              presentstate <= "000";
            end if;

          when others =>

            null;

        end case;

      end if;
    end if;

  end process p_fsm;

  -- Generated from always process in config_UART (config_UART.v:326)
  p_checksum : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        crcreg    <= x"4FB00";
        b_counter <= x"4FB00";
        blink     <= "00000000000000000000000";
      else
        if (Resize(presentstate, 32) = x"00000004") then
          crcreg    <= x"00000";
          b_counter <= x"00000";
        else
          if (False or (True and (command_reg(7) = '1'))) then
            if (
              (Resize(comstate, 32) = x"0000000A") and
              (comtick = '1') and
              (hexvalue(4) = '0') and
              (Resize(presentstate, 32) = x"00000006") and
              (
                (unsigned'("0000000000000000000000000000000") & receivestate) =
                x"00000000"
              )
            ) then
              crcreg    <= crcreg + Resize((highreg & hexvalue(0 + 3 downto 0)), 20);
              b_counter <= b_counter + x"00001";
            end if;
          else
            if (
              (Resize(comstate, 32) = x"0000000A") and
              (comtick = '1') and
              (Resize(presentstate, 32) = x"00000006")
            ) then
              crcreg    <= crcreg + Resize(receivedword, 20);
              b_counter <= b_counter + x"00001";
            end if;
          end if;
        end if;
        if (Resize(presentstate, 32) = x"00000006") then
          receiveled_reg <= '1';
        else
          if ((Resize(presentstate, 32) = x"00000000") and (crcreg /= x"4FB00")) then
            receiveled_reg <= blink(22);
          else
            receiveled_reg <= '0';
          end if;
        end if;
        blink <= blink - "00000000000000000000001";
      end if;
    end if;

  end process p_checksum;

  -- Generated from always process in config_UART (config_UART.v:362)
  p_bus : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        localwritestrobe <= '0';
        bytewritestrobe  <= '0';
      else
        if (Resize(presentstate, 32) = x"00000005") then
          localwritestrobe <= '0';
        else
          if (
            (Resize(presentstate, 32) = x"00000006") and
            (Resize(comstate, 32) = x"0000000A") and
            (comtick = '1')
          ) then
            localwritestrobe <= '1';
          else
            localwritestrobe <= '0';
          end if;
        end if;
        if (False or (True and (command_reg(7) = '0'))) then
          bytewritestrobe <= localwritestrobe;
        else
          bytewritestrobe <= hexwritestrobe;
        end if;
      end if;
    end if;

  end process p_bus;

  -- Generated from always process in config_UART (config_UART.v:386)
  p_wordmode : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        getwordstate    <= "00";
        writedata_reg   <= x"00000000";
        writestrobe_reg <= '0';
      else
        if (Resize(presentstate, 32) = x"00000005") then
          getwordstate  <= "00";
          writedata_reg <= x"00000000";
        else

          case getwordstate is

            when "00" =>

              if (bytewritestrobe = '1') then
                writedata_reg(24 + 7 downto 24) <= receivedbyte;
                getwordstate                    <= "01";
              end if;

            when "01" =>

              if (bytewritestrobe = '1') then
                writedata_reg(16 + 7 downto 16) <= receivedbyte;
                getwordstate                    <= "10";
              end if;

            when "10" =>

              if (bytewritestrobe = '1') then
                writedata_reg(8 + 7 downto 8) <= receivedbyte;
                getwordstate                  <= "11";
              end if;

            when "11" =>

              if (bytewritestrobe = '1') then
                writedata_reg(0 + 7 downto 0) <= receivedbyte;
                getwordstate                  <= "00";
              end if;

            when others =>

              null;

          end case;

        end if;
        if ((bytewritestrobe = '1') and (Resize(getwordstate, 32) = x"00000003")) then
          writestrobe_reg <= '1';
        else
          writestrobe_reg <= '0';
        end if;
      end if;
    end if;

  end process p_wordmode;

  -- Generated from always process in config_UART (config_UART.v:439)
  p_timeout : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        timetosendcounter <= "100000110001000";
        timetosendcounter <= "000000000000000";
      else
        if ((Resize(presentstate, 32) = x"00000000") or (Resize(comstate, 32) = x"0000000A")) then
          timetosendcounter <= "100000110001000";
          timetosend        <= '0';
        else
          if (Resize(timetosendcounter, 32) > x"00000000") then
            timetosendcounter <= timetosendcounter - "000000000000001";
            timetosend        <= '0';
          else
            timetosendcounter <= timetosendcounter;
            timetosend        <= '1';
          end if;
        end if;
      end if;
    end if;

  end process p_timeout;

end architecture from_verilog;
