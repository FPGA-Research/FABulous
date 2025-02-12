library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sequential_16bit_en is
    port (
        clk    : in  std_logic;
        io_in  : in  std_logic_vector(27 downto 0);
        io_out : out std_logic_vector(27 downto 0);
        io_oeb : out std_logic_vector(27 downto 0)
    );
end sequential_16bit_en;

architecture Behavioral of sequential_16bit_en is
    signal rst      : std_logic;
    signal en       : std_logic;
    signal ctr      : unsigned(15 downto 0) := (others => '0');

begin
    rst <= io_in(0);
    en <= io_in(1);

    process(clk)
    begin
        if rising_edge(clk) then
          if en = '1' then
            if rst = '1' then
                ctr <= (others => '0');
            else
                ctr <= ctr + 1;
            end if;
          else
            ctr <= ctr;
          end if;

        end if;
    end process;

    io_out(27 downto 0) <= std_logic_vector(B"0000_0000_0000" & ctr(15 downto 0));
    io_oeb(27 downto 0)<= (others => '1');
end Behavioral;
