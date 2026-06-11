-- SPDX-FileCopyrightText: © 2026 FABulous Contributors
-- SPDX-License-Identifier: Apache-2.0

library ieee;
use ieee.std_logic_1164.all;

entity shift_register is
    port (
        rst  : in  std_logic;
        ena  : in  std_logic;
        din  : in  std_logic;
        dout : out std_logic_vector(7 downto 0)
    );
end entity shift_register;

architecture rtl of shift_register is

    signal sr  : std_logic_vector(7 downto 0);
    signal clk : std_logic;

    component Global_Clock is
        port (
            CLK : out std_logic
        );
    end component;

begin

    clk_i : Global_Clock port map (CLK => clk);

    process (clk) is
    begin
        if rising_edge(clk) then
            if rst = '1' then
                sr <= (others => '0');
            elsif ena = '1' then
                sr <= sr(6 downto 0) & din;
            end if;
        end if;
    end process;

    dout <= sr;

end architecture rtl;
