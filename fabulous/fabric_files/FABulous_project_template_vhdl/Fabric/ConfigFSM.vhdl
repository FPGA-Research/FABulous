-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 13.0 (stable) (v13_0)

library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;

-- Generated from Verilog module ConfigFSM (ConfigFSM.v:3)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   SYNC_HEADER = 1
--   SYNC_HEADER_PATTERN = 4205902513
--   UNSYNCED = 0
--   WRITE_FRAME_DATA = 2
--   desync_flag = 20

entity ConfigFSM is
  generic (
    NumberOfRows    : integer               := 16;
    RowSelectWidth  : integer               := 5;
    FrameBitsPerRow : integer               := 32;
    desync_flag     : integer range 0 to 31 := 20
  );
  port (
    CLK                    : in    std_logic;
    frame_address_register : out   unsigned(FrameBitsPerRow - 1 downto 0);
    fsm_reset              : in    std_logic;
    long_frame_strobe      : out   std_logic;
    reset_n                : in    std_logic;
    row_select             : out   unsigned(RowSelectWidth - 1 downto 0);
    write_data             : in    unsigned(31 downto 0);
    write_strobe           : in    std_logic
  );
end entity ConfigFSM;

-- Generated from Verilog module ConfigFSM (ConfigFSM.v:3)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   SYNC_HEADER = 1
--   SYNC_HEADER_PATTERN = 4205902513
--   UNSYNCED = 0
--   WRITE_FRAME_DATA = 2
--   desync_flag = 20

architecture from_verilog of ConfigFSM is

  signal frame_address_register_Reg : unsigned(FrameBitsPerRow - 1 downto 0);
  signal long_frame_strobe_Reg      : std_logic;
  signal row_select_Reg             : unsigned(RowSelectWidth - 1 downto 0);
  signal frame_strobe               : std_logic;            -- Declared at ConfigFSM.v:19
  signal old_frame_strobe           : std_logic;            -- Declared at ConfigFSM.v:94
  signal old_reset                  : std_logic;            -- Declared at ConfigFSM.v:28
  signal row_index                  : unsigned(4 downto 0); -- Declared at ConfigFSM.v:20
  signal state                      : unsigned(1 downto 0); -- Declared at ConfigFSM.v:27

  constant SYNC_HEADER_PATTERN : unsigned(31 downto 0) := x"FAB0FAB1";

  constant UNSYNCED         : unsigned(1 downto 0) := "00";
  constant SYNC_HEADER      : unsigned(1 downto 0) := "01";
  constant WRITE_FRAME_DATA : unsigned(1 downto 0) := "10";

begin

  frame_address_register <= frame_address_register_Reg;
  long_frame_strobe      <= long_frame_strobe_Reg;
  row_select             <= row_select_Reg;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:29)
  p_fsm : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      old_reset                  <= '0';
      state                      <= UNSYNCED;
      row_index                  <= (others => '0');
      frame_address_register_Reg <= (others => '0');
      frame_strobe               <= '0';
    elsif rising_edge(CLK) then
      old_reset    <= fsm_reset;
      frame_strobe <= '0';
      if (old_reset = '0' and fsm_reset = '1') then
        state     <= UNSYNCED;
        row_index <= (others => '0');
      else

        case state is

          when UNSYNCED =>

            if (write_strobe = '1') then
              if (write_data = SYNC_HEADER_PATTERN) then
                state <= SYNC_HEADER;
              end if;
            end if;

          when SYNC_HEADER =>

            if (write_strobe = '1') then
              if (write_data(desync_flag) = '1') then
                state <= UNSYNCED;
              else
                frame_address_register_Reg <= resize(write_data, FrameBitsPerRow);
                row_index                  <= to_unsigned(NumberOfRows, row_index'length);
                state                      <= WRITE_FRAME_DATA;
              end if;
            end if;

          when WRITE_FRAME_DATA =>

            if (write_strobe = '1') then
              row_index <= row_index - 1;
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

  end process;

  -- Invalidate the row selection when not writing
  row_select_Reg <= resize(row_index, RowSelectWidth) when write_strobe = '1' else
                    (others => '1');

  -- Generated from always process in ConfigFSM (ConfigFSM.v:95)
  p_strobereg : process (CLK, reset_n) is
  begin

    if (reset_n = '0') then
      old_frame_strobe      <= '0';
      long_frame_strobe_Reg <= '0';
    elsif rising_edge(CLK) then
      old_frame_strobe      <= frame_strobe;
      long_frame_strobe_Reg <= frame_strobe or old_frame_strobe;
    end if;

  end process;

end architecture from_verilog;
