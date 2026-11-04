library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity fsm_test is
  port (
    clk  : in  std_logic;
    rst  : in  std_logic;
    din  : in  std_logic;
    dout : out std_logic
  );
end fsm_test;

architecture rtl of fsm_test is
  type state_t is (S0, S1);
  signal state : state_t;
begin
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= S0; dout <= '0';
      else
        case state is
          when S0 => dout <= '0'; if din = '1' then state <= S1; end if;
          when S1 => dout <= '1'; if din = '0' then state <= S0; end if;
        end case;
      end if;
    end if;
  end process;
end rtl;
