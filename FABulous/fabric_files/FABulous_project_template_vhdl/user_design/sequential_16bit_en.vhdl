library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity top is
    port (
        clk    : in  std_logic;
        io_in  : in  std_logic_vector(27 downto 0);
        io_out : out std_logic_vector(27 downto 0);
        io_oeb : out std_logic_vector(27 downto 0)
    );
end top;

architecture Behavioral of top is
    signal rst      : std_logic;
    signal ctr      : unsigned(26 downto 0) := (others => '0');
    
begin
    rst <= io_in(0);

    process(clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                ctr <= (others => '0');
            else
                ctr <= ctr + 1;
            end if;
        end if;
    end process;

    io_out(27 downto 1) <= std_logic_vector(ctr(26 downto 0));
    io_out(0) <= '0';
    io_oeb(27 downto 1)<= (others => '1');
    io_oeb(0) <= '0';
end Behavioral;
