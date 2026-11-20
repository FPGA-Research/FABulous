-- Converted from Verilog (config_UART.v) with Icarus Verilog's VHDL generator,
-- then hand-fixed to restore generics, named constants, the Mode generate
-- block and a synthesizable asynchronous-reset style.

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_UART is
  generic (
    Mode    : integer range 0 to 2    := 0;  -- 0=auto, 1=hex, 2=bin
    ComRate : integer range 1 to 4095 := 217 -- f_CLK / baud (12-bit in the Verilog)
  );
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

architecture from_verilog of config_UART is

  constant MODE_AUTO : integer := 0;
  constant MODE_HEX  : integer := 1;
  constant MODE_BIN  : integer := 2;

  constant RX_TIMEOUT_VALUE   : unsigned(14 downto 0) := to_unsigned(16665, 15);
  constant TEST_FILE_CHECKSUM : unsigned(19 downto 0) := x"4FB00";

  constant HIGH_NIBBLE : std_logic := '1';
  constant LOW_NIBBLE  : std_logic := '0';

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

      when X"41" | X"61" =>

        ASCII2HEX_Result := "01010"; -- A / a

      when X"42" | X"62" =>

        ASCII2HEX_Result := "01011"; -- B / b

      when X"43" | X"63" =>

        ASCII2HEX_Result := "01100"; -- C / c

      when X"44" | X"64" =>

        ASCII2HEX_Result := "01101"; -- D / d

      when X"45" | X"65" =>

        ASCII2HEX_Result := "01110"; -- E / e

      when X"46" | X"66" =>

        ASCII2HEX_Result := "01111"; -- F / f

      when others =>

        -- The MSB encodes an unknown code -> error
        ASCII2HEX_Result := "10000";

    end case;

    return ASCII2HEX_Result;

  end function ASCII2HEX;

  signal ReceiveLED_Reg     : std_logic;
  signal WriteData_Reg      : unsigned(31 downto 0);
  signal WriteStrobe_Reg    : std_logic;
  signal blink              : unsigned(22 downto 0);
  signal byte_write_strobe  : std_logic;
  signal com_count          : unsigned(11 downto 0);
  signal com_state          : unsigned(3 downto 0);
  signal com_tick           : std_logic;
  signal command_reg        : unsigned(7 downto 0);
  signal crc_reg            : unsigned(19 downto 0);
  signal data_reg           : unsigned(7 downto 0);
  signal get_word_state     : unsigned(1 downto 0);
  signal hex_data           : unsigned(7 downto 0);
  signal hex_value          : unsigned(4 downto 0);
  signal hex_write_strobe   : std_logic;
  signal high_reg           : unsigned(3 downto 0);
  signal id_reg             : unsigned(23 downto 0);
  signal local_write_strobe : std_logic;
  signal present_state      : unsigned(2 downto 0);
  signal received_byte      : unsigned(7 downto 0);
  signal received_state     : std_logic;
  signal received_word      : unsigned(7 downto 0);
  signal rx_local           : std_logic;
  signal rx_timeout         : std_logic;
  signal rx_timeout_counter : unsigned(14 downto 0);

begin

  ReceiveLED    <= ReceiveLED_Reg;
  WriteData     <= WriteData_Reg;
  WriteStrobe   <= WriteStrobe_Reg;
  Command       <= command_reg;
  received_byte <= data_reg when (Mode = MODE_BIN or (Mode = MODE_AUTO and command_reg(7) = '0')) else
                   hex_data;
  ComActive     <= '1' when present_state = "110" else
                   '0';

  -- Hex-mode logic, only present for Mode = AUTO or HEX (as in the Verilog)

  gen_l_hexmode : if (Mode = MODE_AUTO or Mode = MODE_HEX) generate
  begin

    hex_value <= ASCII2HEX(received_word);

    p_hexmode : process (CLK, reset_n) is
    begin

      if (reset_n = '0') then
        received_state   <= HIGH_NIBBLE;
        hex_data         <= x"00";
        high_reg         <= x"0";
        hex_write_strobe <= '0';
      elsif rising_edge(CLK) then
        if (present_state /= "110") then
          received_state <= HIGH_NIBBLE;
        elsif (com_state = x"A" and com_tick = '1' and hex_value(4) = '0') then
          if (received_state = HIGH_NIBBLE) then
            received_state <= LOW_NIBBLE;
          end if;
        else
          received_state <= HIGH_NIBBLE;
        end if;

        if (com_state = x"A" and com_tick = '1' and hex_value(4) = '0') then
          if (received_state = HIGH_NIBBLE) then
            high_reg         <= hex_value(3 downto 0);
            hex_write_strobe <= '0';
          else
            hex_data         <= high_reg & hex_value(3 downto 0);
            hex_write_strobe <= '1';
          end if;
        else
          hex_write_strobe <= '0';
        end if;
      end if;

    end process p_hexmode;

  end generate gen_l_hexmode;

  -- In the Verilog these nets are simply undriven when Mode = BIN.
  -- VHDL needs tie-offs so nothing floats.

  gen_l_nohex : if not (Mode = MODE_AUTO or Mode = MODE_HEX) generate
  begin
    hex_value        <= "10000";
    hex_data         <= x"00";
    high_reg         <= x"0";
    hex_write_strobe <= '0';
    received_state   <= HIGH_NIBBLE;
  end generate gen_l_nohex;

  -- Input synchronizer
  p_sync : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      rx_local <= '1';
    elsif rising_edge(CLK) then
      rx_local <= Rx;
    end if;

  end process p_sync;

  -- Baud tick generator
  p_com_en : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      com_count <= x"000";
      com_tick  <= '0';
    elsif rising_edge(CLK) then
      if (com_state = x"0") then
        com_count <= to_unsigned(ComRate / 2, com_count'length);
        com_tick  <= '0';
      elsif (com_count = 0) then
        com_count <= to_unsigned(ComRate, com_count'length);
        com_tick  <= '1';
      else
        com_count <= com_count - 1;
        com_tick  <= '0';
      end if;
    end if;

  end process p_com_en;

  -- UART receiver
  p_com : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      com_state     <= x"0";
      received_word <= x"00";
      id_reg        <= x"000000";
      command_reg   <= x"00";
    elsif rising_edge(CLK) then

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

        when X"A" =>

          if (com_tick = '1') then
            com_state <= x"0";
          end if;

        when others =>

          com_state <= x"0";

      end case;

      if (com_state = x"A" and com_tick = '1') then

        case present_state is

          when "001" =>

            id_reg(23 downto 16) <= received_word;

          when "010" =>

            id_reg(15 downto 8) <= received_word;

          when "011" =>

            id_reg(7 downto 0) <= received_word;

          when "100" =>

            command_reg <= received_word;

          when "110" =>

            data_reg <= received_word;

          when others =>

            null;

        end case;

      end if;
    end if;

  end process p_com;

  -- Protocol FSM
  p_fsm : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      present_state <= "000";
    elsif rising_edge(CLK) then

      case present_state is

        when "000" =>                                                                            -- IDLE

          if (com_state = x"0" and rx_local = '0') then
            present_state <= "001";
          end if;

        when "001" =>                                                                            -- GET_ID_00

          if (rx_timeout = '1') then
            present_state <= "000";
          elsif (com_state = x"A" and com_tick = '1') then
            present_state <= "010";
          end if;

        when "010" =>                                                                            -- GET_ID_AA

          if (rx_timeout = '1') then
            present_state <= "000";
          elsif (com_state = x"A" and com_tick = '1') then
            present_state <= "011";
          end if;

        when "011" =>                                                                            -- GET_ID_FF

          if (rx_timeout = '1') then
            present_state <= "000";
          elsif (com_state = x"A" and com_tick = '1') then
            present_state <= "100";
          end if;

        when "100" =>                                                                            -- GET_COMMAND

          if (rx_timeout = '1') then
            present_state <= "000";
          elsif (com_state = x"A" and com_tick = '1') then
            present_state <= "101";
          end if;

        when "101" =>                                                                            -- EVAL_COMMAND

          if (id_reg = x"00AAFF" and
              (command_reg(6 downto 0) = "0000001" or command_reg(6 downto 0) = "0000010")) then
            present_state <= "110";
          else
            present_state <= "000";
          end if;

        when "110" =>                                                                            -- GET_DATA

          if (rx_timeout = '1') then
            present_state <= "000";
          end if;

        when others =>

          present_state <= "000";

      end case;

    end if;

  end process p_fsm;

  -- Checksum and status LED
  p_checksum : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      crc_reg <= TEST_FILE_CHECKSUM;
      blink   <= (others => '0');
    elsif rising_edge(CLK) then
      if (present_state = "100") then
        crc_reg <= (others => '0');                                               -- init before data arrives
      elsif (Mode = MODE_HEX or (Mode = MODE_AUTO and command_reg(7) = '1')) then
        -- "hex" mode, or "auto" mode with hex detected in the command register
        if (com_state = x"A" and com_tick = '1' and hex_value(4) = '0'
            and present_state = "110" and received_state = LOW_NIBBLE) then
          crc_reg <= crc_reg + (x"000" & high_reg & hex_value(3 downto 0));
        end if;
      else
        -- "binary" mode
        if (com_state = x"A" and com_tick = '1' and present_state = "110") then
          crc_reg <= crc_reg + (x"000" & received_word);
        end if;
      end if;

      if (present_state = "110") then
        ReceiveLED_Reg <= '1';                                                    -- receive in progress
      elsif (present_state = "000" and crc_reg /= TEST_FILE_CHECKSUM) then
        ReceiveLED_Reg <= blink(22);
      else
        ReceiveLED_Reg <= '0';                                                    -- receive was OK
      end if;

      blink <= blink - 1;
    end if;

  end process p_checksum;

  -- Byte strobe
  p_bus : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      local_write_strobe <= '0';
      byte_write_strobe  <= '0';
    elsif rising_edge(CLK) then
      if (present_state = "101") then
        local_write_strobe <= '0';
      elsif (present_state = "110" and com_state = x"A" and com_tick = '1') then
        local_write_strobe <= '1';
      else
        local_write_strobe <= '0';
      end if;

      if (Mode = MODE_BIN or (Mode = MODE_AUTO and command_reg(7) = '0')) then
        -- Extra register stage keeps data valid and the strobe glitch-free
        byte_write_strobe <= local_write_strobe;
      else
        byte_write_strobe <= hex_write_strobe;
      end if;
    end if;

  end process p_bus;

  -- Assemble 32-bit words from bytes
  p_wordmode : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      get_word_state  <= "00";
      WriteData_Reg   <= x"00000000";
      WriteStrobe_Reg <= '0';
    elsif rising_edge(CLK) then
      if (present_state = "101") then
        get_word_state <= "00";
        WriteData_Reg  <= x"00000000";
      else

        case get_word_state is

          when "00" =>

            if (byte_write_strobe = '1') then
              WriteData_Reg(31 downto 24) <= received_byte;
              get_word_state              <= "01";
            end if;

          when "01" =>

            if (byte_write_strobe = '1') then
              WriteData_Reg(23 downto 16) <= received_byte;
              get_word_state              <= "10";
            end if;

          when "10" =>

            if (byte_write_strobe = '1') then
              WriteData_Reg(15 downto 8) <= received_byte;
              get_word_state             <= "11";
            end if;

          when "11" =>

            if (byte_write_strobe = '1') then
              WriteData_Reg(7 downto 0) <= received_byte;
              get_word_state            <= "00";
            end if;

          when others =>

            get_word_state <= "00";

        end case;

      end if;

      if (byte_write_strobe = '1' and get_word_state = "11") then
        WriteStrobe_Reg <= '1';
      else
        WriteStrobe_Reg <= '0';
      end if;
    end if;

  end process p_wordmode;

  -- Receive timeout
  p_timeout : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      rx_timeout_counter <= RX_TIMEOUT_VALUE;
      rx_timeout         <= '0';
    elsif rising_edge(CLK) then
      if (present_state = "000" or com_state = x"A") then
        rx_timeout_counter <= RX_TIMEOUT_VALUE;
        rx_timeout         <= '0';
      elsif (rx_timeout_counter > 0) then
        rx_timeout_counter <= rx_timeout_counter - 1;
        rx_timeout         <= '0';
      else
        rx_timeout <= '1';                    -- force FSM back to IDLE
      end if;
    end if;

  end process p_timeout;

end architecture from_verilog;
