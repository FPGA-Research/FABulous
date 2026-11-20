library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity config_UART is
  generic (
    -- The default mode is "auto", which switches between "hex" and "binary" mode,
    -- but takes a bit more logic.
    -- Mode "bin" is the faster binary mode, but might not work on all machines/boards.
    -- Mode "auto" uses the MSB in the command byte (the 8th byte in the comload header)
    -- to set the mode.
    -- [0:auto|1:hex|2:bin]
    Mode : integer := 0;
    -- ComRate = f_CLK / Baudrate (e.g., 25 MHz/115200 Baud = 217)
    ComRate : integer := 217
  );
  port (
    CLK         : in    std_logic;
    reset_n     : in    std_logic;
    Rx          : in    std_logic;
    WriteData   : out   unsigned(31 downto 0);
    ComActive   : out   std_logic;
    WriteStrobe : out   std_logic;
    Command     : out   unsigned(7 downto 0);
    ReceiveLED  : out   std_logic
  );
end entity config_UART;

architecture from_verilog of config_UART is

  -- 25e6/1500 ~= 16666, original minus one
  constant RX_TIMEOUT_VALUE   : unsigned(14 downto 0) := to_unsigned(16665, 15);
  constant TEST_FILE_CHECKSUM : unsigned(19 downto 0) := x"4FB00";

  constant MODE_AUTO : integer := 0;
  constant MODE_HEX  : integer := 1;
  constant MODE_BIN  : integer := 2;

  constant HIGH_NIBBLE : std_logic := '1';
  constant LOW_NIBBLE  : std_logic := '0';

  constant WAIT_FOR_START_BIT    : unsigned(3 downto 0) := "0000";
  constant DELAY_AFTER_START_BIT : unsigned(3 downto 0) := "0001";
  constant GET_BIT_0             : unsigned(3 downto 0) := "0010";
  constant GET_BIT_1             : unsigned(3 downto 0) := "0011";
  constant GET_BIT_2             : unsigned(3 downto 0) := "0100";
  constant GET_BIT_3             : unsigned(3 downto 0) := "0101";
  constant GET_BIT_4             : unsigned(3 downto 0) := "0110";
  constant GET_BIT_5             : unsigned(3 downto 0) := "0111";
  constant GET_BIT_6             : unsigned(3 downto 0) := "1000";
  constant GET_BIT_7             : unsigned(3 downto 0) := "1001";
  constant GET_STOP_BIT          : unsigned(3 downto 0) := "1010";

  constant IDLE         : unsigned(2 downto 0) := "000";
  constant GET_ID_00    : unsigned(2 downto 0) := "001";
  constant GET_ID_AA    : unsigned(2 downto 0) := "010";
  constant GET_ID_FF    : unsigned(2 downto 0) := "011";
  constant GET_COMMAND  : unsigned(2 downto 0) := "100";
  constant EVAL_COMMAND : unsigned(2 downto 0) := "101";
  constant GET_DATA     : unsigned(2 downto 0) := "110";

  constant WORD_0 : unsigned(1 downto 0) := "00";
  constant WORD_1 : unsigned(1 downto 0) := "01";
  constant WORD_2 : unsigned(1 downto 0) := "10";
  constant WORD_3 : unsigned(1 downto 0) := "11";

  signal received_state     : std_logic;
  signal high_reg           : unsigned(3 downto 0);
  signal hex_value          : unsigned(4 downto 0); -- A 0 at the MSB indicates a valid value on bits [3..0]
  signal hex_data           : unsigned(7 downto 0); -- The received byte in "hex" mode
  signal hex_write_strobe   : std_logic;            -- We received two hex nibbles and have a result byte
  signal com_count          : unsigned(11 downto 0);
  signal com_tick           : std_logic;
  signal com_state          : unsigned(3 downto 0);
  signal received_word      : unsigned(7 downto 0);
  signal rx_local           : std_logic;
  signal id_reg             : unsigned(23 downto 0);
  signal command_reg        : unsigned(7 downto 0);
  signal data_reg           : unsigned(7 downto 0);
  signal received_byte      : unsigned(7 downto 0);
  signal rx_timeout         : std_logic;
  signal rx_timeout_counter : unsigned(14 downto 0);
  signal present_state      : unsigned(2 downto 0);
  signal get_word_state     : unsigned(1 downto 0);
  signal local_write_strobe : std_logic;
  signal byte_write_strobe  : std_logic;
  signal crc_reg            : unsigned(19 downto 0);
  signal blink              : unsigned(22 downto 0);

  function ASCII2HEX (
    ASCII : unsigned(7 downto 0)
  )
  return unsigned is
  begin

    case ASCII is

      when x"30" =>

        return "00000"; -- 0

      when x"31" =>

        return "00001";

      when x"32" =>

        return "00010";

      when x"33" =>

        return "00011";

      when x"34" =>

        return "00100";

      when x"35" =>

        return "00101";

      when x"36" =>

        return "00110";

      when x"37" =>

        return "00111";

      when x"38" =>

        return "01000";

      when x"39" =>

        return "01001";

      when x"41" =>

        return "01010"; -- A

      when x"61" =>

        return "01010"; -- a

      when x"42" =>

        return "01011"; -- B

      when x"62" =>

        return "01011"; -- b

      when x"43" =>

        return "01100"; -- C

      when x"63" =>

        return "01100"; -- c

      when x"44" =>

        return "01101"; -- D

      when x"64" =>

        return "01101"; -- d

      when x"45" =>

        return "01110"; -- E

      when x"65" =>

        return "01110"; -- e

      when x"46" =>

        return "01111"; -- F

      when x"66" =>

        return "01111"; -- f

      when others =>

        -- The MSB encodes if there was an unknown code -> error
        return "10000";

    end case;

  end function ASCII2HEX;

begin

  p_sync : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      rx_local <= '1';
    elsif rising_edge(CLK) then
      rx_local <= Rx;
    end if;

  end process p_sync;

  p_com_en : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      com_count <= (others => '0');
      com_tick  <= '0';
    elsif rising_edge(CLK) then
      if (com_state = WAIT_FOR_START_BIT) then
        com_count <= to_unsigned(ComRate / 2, 12);
        com_tick  <= '0';
      elsif (com_count = 0) then
        com_count <= to_unsigned(ComRate, 12);
        com_tick  <= '1';
      else
        com_count <= com_count - 1;
        com_tick  <= '0';
      end if;
    end if;

  end process p_com_en;

  -- data_reg has no reset value, as in the Verilog.
  p_com : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      com_state     <= WAIT_FOR_START_BIT;
      received_word <= (others => '0');
      id_reg        <= (others => '0');
      command_reg   <= (others => '0');
    elsif rising_edge(CLK) then

      case com_state is

        when WAIT_FOR_START_BIT =>

          if (rx_local = '0') then
            com_state     <= DELAY_AFTER_START_BIT;
            received_word <= (others => '0');
          end if;

        when DELAY_AFTER_START_BIT =>

          if (com_tick = '1') then
            com_state <= GET_BIT_0;
          end if;

        when GET_BIT_0 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_1;
            received_word(0) <= rx_local;
          end if;

        when GET_BIT_1 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_2;
            received_word(1) <= rx_local;
          end if;

        when GET_BIT_2 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_3;
            received_word(2) <= rx_local;
          end if;

        when GET_BIT_3 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_4;
            received_word(3) <= rx_local;
          end if;

        when GET_BIT_4 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_5;
            received_word(4) <= rx_local;
          end if;

        when GET_BIT_5 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_6;
            received_word(5) <= rx_local;
          end if;

        when GET_BIT_6 =>

          if (com_tick = '1') then
            com_state        <= GET_BIT_7;
            received_word(6) <= rx_local;
          end if;

        when GET_BIT_7 =>

          if (com_tick = '1') then
            com_state        <= GET_STOP_BIT;
            received_word(7) <= rx_local;
          end if;

        when GET_STOP_BIT =>

          if (com_tick = '1') then
            com_state <= WAIT_FOR_START_BIT;
          end if;

        when others =>

          com_state <= WAIT_FOR_START_BIT;

      end case;

      if (com_state = GET_STOP_BIT and com_tick = '1') then

        case present_state is

          when GET_ID_00 =>

            id_reg(23 downto 16) <= received_word;

          when GET_ID_AA =>

            id_reg(15 downto 8) <= received_word;

          when GET_ID_FF =>

            id_reg(7 downto 0) <= received_word;

          when GET_COMMAND =>

            command_reg <= received_word;

          when GET_DATA =>

            data_reg <= received_word;

          when others =>

            null;

        end case;

      end if;
    end if;

  end process p_com;

  p_fsm : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      present_state <= IDLE;
    elsif rising_edge(CLK) then

      case present_state is

        when IDLE =>

          if (com_state = WAIT_FOR_START_BIT and rx_local = '0') then
            present_state <= GET_ID_00;
          end if;

        when GET_ID_00 =>

          if (rx_timeout = '1') then
            present_state <= IDLE;
          elsif (com_state = GET_STOP_BIT and com_tick = '1') then
            present_state <= GET_ID_AA;
          end if;

        when GET_ID_AA =>

          if (rx_timeout = '1') then
            present_state <= IDLE;
          elsif (com_state = GET_STOP_BIT and com_tick = '1') then
            present_state <= GET_ID_FF;
          end if;

        when GET_ID_FF =>

          if (rx_timeout = '1') then
            present_state <= IDLE;
          elsif (com_state = GET_STOP_BIT and com_tick = '1') then
            present_state <= GET_COMMAND;
          end if;

        when GET_COMMAND =>

          if (rx_timeout = '1') then
            present_state <= IDLE;
          elsif (com_state = GET_STOP_BIT and com_tick = '1') then
            present_state <= EVAL_COMMAND;
          end if;

        when EVAL_COMMAND =>

          if (id_reg = x"00AAFF" and
              (command_reg(6 downto 0) = "0000001" or command_reg(6 downto 0) = "0000010")) then
            present_state <= GET_DATA;
          else
            present_state <= IDLE;
          end if;

        when GET_DATA =>

          if (rx_timeout = '1') then
            present_state <= IDLE;
          end if;

        when others =>

          present_state <= IDLE;

      end case;

    end if;

  end process p_fsm;

  Command <= command_reg;

  gen_l_hexmode : if Mode = MODE_AUTO or Mode = MODE_HEX generate

    hex_value <= ASCII2HEX(received_word);

    p_hexmode : process (reset_n, CLK) is
    begin

      if (reset_n = '0') then
        received_state   <= HIGH_NIBBLE;
        hex_data         <= (others => '0');
        high_reg         <= (others => '0');
        hex_write_strobe <= '0';
      elsif rising_edge(CLK) then
        if (present_state /= GET_DATA) then
          received_state <= HIGH_NIBBLE;
        elsif (com_state = GET_STOP_BIT and com_tick = '1' and hex_value(4) = '0') then
          if (received_state = HIGH_NIBBLE) then
            received_state <= LOW_NIBBLE;
          end if;
        else
          received_state <= HIGH_NIBBLE;
        end if;
        if (com_state = GET_STOP_BIT and com_tick = '1' and hex_value(4) = '0') then
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

  -- ReceiveLED has no reset value, as in the Verilog.
  p_checksum : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      crc_reg <= TEST_FILE_CHECKSUM;
      blink   <= (others => '0');
    elsif rising_edge(CLK) then
      if (present_state = GET_COMMAND) then
        -- Init before data arrives
        crc_reg <= (others => '0');
      elsif (Mode = 1 or (Mode = 0 and command_reg(7) = '1')) then
        -- "hex" mode or "auto" mode with detected "hex" mode in the command register
        if (com_state = GET_STOP_BIT and com_tick = '1' and hex_value(4) = '0'
            and present_state = GET_DATA and received_state = LOW_NIBBLE) then
          crc_reg <= crc_reg + resize(high_reg & hex_value(3 downto 0), 20);
        end if;
      else
        -- "binary" mode
        if (com_state = GET_STOP_BIT and com_tick = '1' and present_state = GET_DATA) then
          crc_reg <= crc_reg + resize(received_word, 20);
        end if;
      end if;

      if (present_state = GET_DATA) then
        -- Receive process in progress
        ReceiveLED <= '1';
      elsif (present_state = IDLE and crc_reg /= TEST_FILE_CHECKSUM) then
        ReceiveLED <= blink(22);
      else
        -- Receive process was OK
        ReceiveLED <= '0';
      end if;

      blink <= blink - 1;
    end if;

  end process p_checksum;

  p_bus : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      local_write_strobe <= '0';
      byte_write_strobe  <= '0';
    elsif rising_edge(CLK) then
      if (present_state = EVAL_COMMAND) then
        local_write_strobe <= '0';
      elsif (present_state = GET_DATA and com_state = GET_STOP_BIT and com_tick = '1') then
        local_write_strobe <= '1';
      else
        local_write_strobe <= '0';
      end if;

      if (Mode = MODE_BIN or (Mode = MODE_AUTO and command_reg(7) = '0')) then
        -- "binary" mode or "auto" mode with detected binary mode in the command register.
        -- Extra register stage ensures data is valid and prevents glitches on the strobe output.
        byte_write_strobe <= local_write_strobe;
      else
        byte_write_strobe <= hex_write_strobe;
      end if;
    end if;

  end process p_bus;

  p_wordmode : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      get_word_state <= WORD_0;
      WriteData      <= (others => '0');
      WriteStrobe    <= '0';
    elsif rising_edge(CLK) then
      if (present_state = EVAL_COMMAND) then
        get_word_state <= WORD_0;
        WriteData      <= (others => '0');
      else

        case get_word_state is

          when WORD_0 =>

            if (byte_write_strobe = '1') then
              WriteData(31 downto 24) <= received_byte;
              get_word_state          <= WORD_1;
            end if;

          when WORD_1 =>

            if (byte_write_strobe = '1') then
              WriteData(23 downto 16) <= received_byte;
              get_word_state          <= WORD_2;
            end if;

          when WORD_2 =>

            if (byte_write_strobe = '1') then
              WriteData(15 downto 8) <= received_byte;
              get_word_state         <= WORD_3;
            end if;

          when WORD_3 =>

            if (byte_write_strobe = '1') then
              WriteData(7 downto 0) <= received_byte;
              get_word_state        <= WORD_0;
            end if;

          when others =>

            get_word_state <= WORD_0;

        end case;

      end if;

      if (byte_write_strobe = '1' and get_word_state = WORD_3) then
        WriteStrobe <= '1';
      else
        WriteStrobe <= '0';
      end if;
    end if;

  end process p_wordmode;

  -- "binary" mode or "auto" mode with detected "binary" mode in the command register
  received_byte <= data_reg when (Mode = 2 or (Mode = 0 and command_reg(7) = '0')) else
                   hex_data;
  ComActive     <= '1' when present_state = GET_DATA else
                   '0';

  p_timeout : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      rx_timeout_counter <= RX_TIMEOUT_VALUE;
      rx_timeout         <= '0';
    elsif rising_edge(CLK) then
      if (present_state = IDLE or com_state = GET_STOP_BIT) then
        -- Init timeout
        rx_timeout_counter <= RX_TIMEOUT_VALUE;
        rx_timeout         <= '0';
      elsif (rx_timeout_counter > 0) then
        rx_timeout_counter <= rx_timeout_counter - 1;
        rx_timeout         <= '0';
      else
        rx_timeout <= '1'; -- Force FSM to go back to IDLE when inactive
      end if;
    end if;

  end process p_timeout;

end architecture from_verilog;
