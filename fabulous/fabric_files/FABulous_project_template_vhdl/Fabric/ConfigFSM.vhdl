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

entity configfsm is
  generic (
    framebitsperrow : integer := 32;
    numberofrows    : integer := 16;
    rowselectwidth  : integer := 5;
    desync_flag     : integer := 20
  );
  port (
    clk                  : in    std_logic;
    fsm_reset            : in    std_logic;
    frameaddressregister : out   std_logic_vector(31 downto 0);
    longframestrobe      : out   std_logic;
    rowselect            : out   std_logic_vector(4 downto 0);
    writedata            : in    std_logic_vector(31 downto 0);
    writestrobe          : in    std_logic;
    resetn               : in    std_logic
  );
end entity configfsm;

-- Generated from Verilog module ConfigFSM (ConfigFSM.v:1)
--   FrameBitsPerRow = 32
--   NumberOfRows = 16
--   RowSelectWidth = 5
--   desync_flag = 20

architecture from_verilog of configfsm is

  signal frameaddressregister_reg : std_logic_vector(31 downto 0);
  signal longframestrobe_reg      : std_logic;
  signal rowselect_reg            : std_logic_vector(4 downto 0);
  signal frameshiftstate          : unsigned(4 downto 0);         -- Declared at ConfigFSM.v:20
  signal framestrobe              : std_logic;                    -- Declared at ConfigFSM.v:18
  signal oldframestrobe           : std_logic;                    -- Declared at ConfigFSM.v:83
  signal old_reset                : std_logic;                    -- Declared at ConfigFSM.v:24
  signal state                    : std_logic_vector(1 downto 0); -- Declared at ConfigFSM.v:23

  function boolean_to_logic (
    b : boolean
  ) return std_logic is
  begin

    if (b) then
      return '1';
    else
      return '0';
    end if;

  end function boolean_to_logic;

begin

  frameaddressregister <= frameaddressregister_reg;
  longframestrobe      <= longframestrobe_reg;
  rowselect            <= rowselect_reg;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:25)
  p_fsm : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        old_reset                <= '0';
        state                    <= "00";
        frameshiftstate          <= "00000";
        frameaddressregister_reg <= x"00000000";
        framestrobe              <= '0';
      else
        old_reset   <= fsm_reset;
        framestrobe <= '0';
        if ((old_reset = '0') and (fsm_reset = '1')) then
          state           <= "00";
          frameshiftstate <= "00000";
        else

          case state is

            when "00" =>

              if (writestrobe = '1') then
                if (writedata = x"FAB0FAB1") then
                  state <= "01";
                end if;
              end if;

            when "01" =>

              if (writestrobe = '1') then
                if (writedata(desync_flag) = '1') then
                  state <= "00";
                else
                  frameaddressregister_reg <= writedata;
                  frameshiftstate          <= to_unsigned(numberofrows, frameshiftstate'length);
                  state                    <= "10";
                end if;
              end if;

            when "10" =>

              if (writestrobe = '1') then
                frameshiftstate <= frameshiftstate - "00001";
                if (Resize(frameshiftstate, 32) = x"00000001") then
                  framestrobe <= '1';
                  state       <= "01";
                end if;
              end if;

            when others =>

              null;

          end case;

        end if;
      end if;
    end if;

  end process p_fsm;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:75)
  process_001 : process (writestrobe, frameshiftstate) is
  begin

    if (writestrobe = '1') then
      rowselect_reg <= std_logic_vector(frameshiftstate);
    else
      rowselect_reg <= "11111";
    end if;

  end process process_001;

  -- Generated from always process in ConfigFSM (ConfigFSM.v:84)
  p_strobereg : process (resetn, clk) is
  begin

    if (falling_edge(resetn) or rising_edge(clk)) then
      if ((not resetn) = '1') then
        oldframestrobe      <= '0';
        longframestrobe_reg <= '0';
      else
        oldframestrobe      <= framestrobe;
        longframestrobe_reg <= boolean_to_logic((framestrobe = '1') or (oldframestrobe = '1'));
      end if;
    end if;

  end process p_strobereg;

end architecture from_verilog;
