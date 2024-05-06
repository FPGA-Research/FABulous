--------------------------------------------------
-- AND gate (ESD book figure 2.3)		
-- two descriptions provided
--------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;

--------------------------------------------------

entity AND_ent is
port(	
    x: in std_logic;
	y: in std_logic;
	F: out std_logic
);
end AND_ent;  

--------------------------------------------------

architecture behav1 of AND_ent is
begin

    process(x, y)
    begin
        -- compare to truth table
        if ((x='1') and (y='1')) then
	    F <= '1';
	else
	    F <= '0';
	end if;
    end process;

end behav1;

architecture behav2 of AND_ent is
begin

    F <= x and y;
end behav2;

--------------------------------------------------