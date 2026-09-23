-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 12.0 (stable) ()

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
  port (
    CLK                    : in    std_logic;
    frame_address_register : out   unsigned(31 downto 0);
    fsm_reset              : in    std_logic;
    long_frame_strobe      : out   std_logic;
    reset_n                : in    std_logic;
    row_select             : out   unsigned(4 downto 0);
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

  signal frame_address_register_Reg : unsigned(31 downto 0);
  signal long_frame_strobe_Reg      : std_logic;
  signal row_select_Reg             : unsigned(4 downto 0);
  signal frame_strobe               : std_logic;            -- Declared at ConfigFSM.v:19
  signal old_frame_strobe           : std_logic;            -- Declared at ConfigFSM.v:94
  signal old_reset                  : std_logic;            -- Declared at ConfigFSM.v:28
  signal row_index                  : unsigned(4 downto 0); -- Declared at ConfigFSM.v:20
  signal state                      : unsigned(1 downto 0); -- Declared at ConfigFSM.v:27

  function Boolean_To_Logic (
    B : Boolean
  ) return std_logic is
  begin

    if (B) then
      return '1';
    else
      return '0';
    end if;

  end function Boolean_To_Logic;

begin

  frame_address_register <= frame_address_register_Reg;
  long_frame_strobe      <= long_frame_strobe_Reg;
  row_select             <= row_select_Reg;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:29)
  p_fsm : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        old_reset                  <= '0';
        state                      <= "00";
        row_index                  <= "00000";
        frame_address_register_Reg <= x"00000000";
        frame_strobe               <= '0';
      else
        old_reset    <= fsm_reset;
        frame_strobe <= '0';
        if ((old_reset = '0') and (fsm_reset = '1')) then
          state     <= "00";
          row_index <= "00000";
        else

          case state is

            when "00" =>

              if (write_strobe = '1') then
                if (write_data = x"FAB0FAB1") then
                  state <= "01";
                end if;
              end if;

            when "01" =>

              if (write_strobe = '1') then
                if (write_data(20) = '1') then
                  state <= "00";
                else
                  frame_address_register_Reg <= write_data;
                  row_index                  <= "10000";
                  state                      <= "10";
                end if;
              end if;

            when "10" =>

              if (write_strobe = '1') then
                row_index <= row_index - "00001";
                if (Resize(row_index, 32) = x"00000001") then
                  frame_strobe <= '1';
                  state        <= "01";
                end if;
              end if;

            when others =>

              state <= "00";

          end case;

        end if;
      end if;
    end if;

  end process;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:86)
  process (write_strobe, row_index) is
  begin

    if (write_strobe = '1') then
      row_select_Reg <= row_index;
    else
      row_select_Reg <= "11111";
    end if;

  end process;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:95)
  p_strobereg : process (reset_n, CLK) is
  begin

    if (falling_edge(reset_n) or rising_edge(CLK)) then
      if ((not reset_n) = '1') then
        old_frame_strobe      <= '0';
        long_frame_strobe_Reg <= '0';
      else
        old_frame_strobe      <= frame_strobe;
        long_frame_strobe_Reg <= Boolean_To_Logic((frame_strobe = '1') or (old_frame_strobe = '1'));
      end if;
    end if;

  end process;

end architecture from_verilog;
