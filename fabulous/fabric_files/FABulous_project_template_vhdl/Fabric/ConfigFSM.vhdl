library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

entity ConfigFSM is
  generic (
    NumberOfRows    : integer := 16;
    RowSelectWidth  : integer := 5;
    FrameBitsPerRow : integer := 32;
    desync_flag     : integer := 20
  );
  port (
    CLK                    : in    std_logic;
    reset_n                : in    std_logic;
    write_data             : in    std_logic_vector(31 downto 0);
    write_strobe           : in    std_logic;
    fsm_reset              : in    std_logic;
    frame_address_register : out   std_logic_vector(FrameBitsPerRow - 1 downto 0);
    long_frame_strobe      : out   std_logic;
    row_select             : out   std_logic_vector(RowSelectWidth - 1 downto 0)
  );
end entity ConfigFSM;

architecture from_verilog of ConfigFSM is

  constant UNSYNCED            : std_logic_vector(1 downto 0)  := "00";
  constant SYNC_HEADER         : std_logic_vector(1 downto 0)  := "01";
  constant WRITE_FRAME_DATA    : std_logic_vector(1 downto 0)  := "10";
  constant SYNC_HEADER_PATTERN : std_logic_vector(31 downto 0) := x"FAB0FAB1";

  signal frame_address_register_reg : std_logic_vector(FrameBitsPerRow - 1 downto 0);
  signal long_frame_strobe_reg      : std_logic;
  signal frame_strobe               : std_logic;
  signal row_index                  : unsigned(4 downto 0);
  signal state                      : std_logic_vector(1 downto 0);
  signal old_reset                  : std_logic;
  signal old_frame_strobe           : std_logic;

begin

  frame_address_register <= frame_address_register_reg;
  long_frame_strobe      <= long_frame_strobe_reg;

  p_fsm : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      old_reset                  <= '0';
      state                      <= UNSYNCED;
      row_index                  <= "00000";
      frame_address_register_reg <= (others => '0');
      frame_strobe               <= '0';
    elsif rising_edge(CLK) then
      old_reset    <= fsm_reset;
      frame_strobe <= '0';
      -- Configuration activates only after detecting the 32-bit sync pattern 0xFAB0_FAB1.
      -- This allows the same bitfile to be used for UART or parallel config, with arbitrary
      -- metadata in the header, provided the header is 4-byte padded.
      if ((old_reset = '0') and (fsm_reset = '1')) then
        state     <= UNSYNCED;
        row_index <= "00000";
      else

        case state is

          when UNSYNCED =>

            if (write_strobe = '1') then
              -- fire only after seeing pattern 0xFAB0_FAB1
              if (write_data = SYNC_HEADER_PATTERN) then
                state <= SYNC_HEADER;
              end if;
            end if;

          when SYNC_HEADER =>

            if (write_strobe = '1') then
              if (write_data(desync_flag) = '1') then
                state <= UNSYNCED;
              else
                frame_address_register_reg <= write_data;
                -- Deliberate narrowing, as in the Verilog
                row_index <= to_unsigned(NumberOfRows mod 32, 5);
                state     <= WRITE_FRAME_DATA;
              end if;
            end if;

          when WRITE_FRAME_DATA =>

            if (write_strobe = '1') then
              row_index <= row_index - 1;
              -- on last frame
              if (row_index = 1) then
                frame_strobe <= '1';
                state        <= SYNC_HEADER;
              end if;
            end if;

          when others =>

            state <= UNSYNCED;

        end case;

      end if;
    end if;

  end process p_fsm;

  p_row_select : process (write_strobe, row_index) is
  begin

    if (write_strobe = '1') then
      row_select <= std_logic_vector(resize(row_index, RowSelectWidth));
    else
      -- Invalidate the row selection when not writing
      row_select <= (others => '1');
    end if;

  end process p_row_select;

  p_strobereg : process (reset_n, CLK) is
  begin

    if (reset_n = '0') then
      old_frame_strobe      <= '0';
      long_frame_strobe_reg <= '0';
    elsif rising_edge(CLK) then
      old_frame_strobe      <= frame_strobe;
      long_frame_strobe_reg <= frame_strobe or old_frame_strobe;
    end if;

  end process p_strobereg;

end architecture from_verilog;
