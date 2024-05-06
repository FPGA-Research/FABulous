library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fab_tb is
end fab_tb; 

architecture Behavior of fab_tb is

  component eFPGA_top is
    generic (
      FrameBitsPerRow : integer := 32;
      FrameSelectWidth : integer := 5;
      MaxFramesPerCol : integer := 20;
      NumberOfCols : integer := 10;
      NumberOfRows : integer := 14;
      RowSelectWidth : integer := 5;
      desync_flag : integer := 20;
      include_eFPGA : integer := 1
    );
      port (
        I_top : out std_logic_vector( NumberOfRows * 2 - 1 downto 0);
        T_top : out std_logic_vector(NumberOfRows * 2 - 1 downto 0);
        O_top : in std_logic_vector( NumberOfRows * 2 - 1 downto 0);
        A_config_C : out std_logic_vector( NumberOfRows * 4 - 1 downto 0);
        B_config_C : out std_logic_vector( NumberOfRows * 4 - 1 downto 0);

        CLK : in std_logic;
        ComActive : out std_logic;
        ReceiveLED : out std_logic;
        Rx : in std_logic;
        s_clk : in std_logic;
        s_data : in std_logic;
        SelfWriteData : in std_logic_vector(31 downto 0);
        SelfWriteStrobe : in std_logic
        
    );
    end component; 

  component top is 
    port (
      clk : in std_logic;
      io_out: out unsigned(27 downto 0);
      io_oeb: out unsigned(27 downto 0);
      io_in: in unsigned(27 downto 0)
    );
  end component;

  constant MAX_BITBYTES:integer := 16384;


  signal I_top : std_logic_vector( 27 downto 0);
  signal T_top : std_logic_vector(27 downto 0);
  signal O_top : std_logic_vector( 27 downto 0) := X"0000000";
  signal A_cfg: std_logic_vector(55 downto 0);
  signal B_cfg: std_logic_vector(55 downto 0);
  
  signal I_top_gold : unsigned(27 downto 0);  
  signal T_top_gold : unsigned(27 downto 0);  
  
  signal CLK : std_logic := '0';  
  signal SelfWriteStrobe : std_logic := '0'; 
  signal SelfWriteData : std_logic_vector(31 downto 0) := X"00000000";  
  signal ComActive : std_logic;  
  signal Rx : std_logic := '1'; 
  signal s_clk : std_logic := '0'; 
  signal s_data : std_logic := '0';  
  signal ReceiveLED : std_logic;  
  
  type bitstream_Type is array (MAX_BITBYTES downto 0) of std_logic_vector(7 downto 0);
  signal bitstream : bitstream_Type;

  signal O_top_unsigned : unsigned(27 downto 0);

  impure function readmemh(filename : string) return bitstream_Type is
    use std.textio.all;
    variable bs : bitstream_Type;
    file read_file: text open READ_MODE is "bitstream.hex";
    variable counter : integer := 0;
    variable L: LINE;
    variable temp: std_logic_vector(7 downto 0);
    variable good_v : boolean;
    begin
      while not endfile(read_file) loop
        readline (read_file, L);
        hread (L, temp, good_v);
        bs(counter) := temp;
        counter := counter + 1;
      end loop;
    return bs;
  end function;

begin
  O_top_unsigned <= unsigned(O_top);

  init_eFPGA: eFPGA_top
    generic map (
      FrameBitsPerRow => 32,
      FrameSelectWidth => 5,
      MaxFramesPerCol => 20,
      NumberOfCols => 10,
      NumberOfRows => 14,
      RowSelectWidth => 5,
      desync_flag => 20,
      include_eFPGA => 1
    )
    port map (
      I_top => I_top,
      T_top => T_top,
      O_top => O_top,
      A_config_C => A_cfg,
      B_config_C => B_cfg,

      CLK => CLK,
      SelfWriteStrobe => SelfWriteStrobe,
      SelfWriteData => SelfWriteData,
      
      Rx => Rx,
      ComActive => ComActive,
      ReceiveLED => ReceiveLED,
      s_clk => s_clk,
      s_data => s_data
      
    );

    init_top: top 
      port map (
        clk => CLK,
        io_out => I_top_gold,
        io_oeb => T_top_gold,
        io_in => O_top_unsigned
      );
  

  process is
  begin
    wait for 5000 ps;
    CLK <= not CLK;
  end process;
  
  process is
    variable i : integer := 0; 
  begin
    while i < MAX_BITBYTES loop
      bitstream(i) <= X"00";
      i := i + 1;
    end loop;

    i := 0;
    bitstream <= readmemh("bitstream.hex");
    report "Bitstream loaded into memory array";
    wait for 10000 ps;
    for Verilog_Repeat in 1 to 10 loop
      wait until rising_edge(CLK);
    end loop;
    
    wait for 2500 ps;
      
    while i < MAX_BITBYTES loop
      SelfWriteData <= bitstream(i) & bitstream(i+1) &  bitstream(i+2) & bitstream(i+3);
      -- wait 2 clock cycles
      wait until rising_edge(CLK);
      wait until rising_edge(CLK);

      -- report integer'image(i) & " " & to_hstring(SelfWriteData); 
      SelfWriteStrobe <= '1';
      wait until rising_edge(CLK);
      SelfWriteStrobe <= '0';

      -- wait another 2 clock cycles
      wait until rising_edge(CLK);
      wait until rising_edge(CLK);

      i := i + 4;
    end loop;

    -- wait 100 clock cycles
    for Verilog_Repeat in 1 to 100 loop
      wait until rising_edge(CLK);
    end loop;
    report "Configuration completed";

    O_top <= X"0000001";
    wait until rising_edge(CLK);

    -- wait 5 clock cycles
    for Verilog_Repeat in 1 to 5 loop
      wait until rising_edge(CLK);
    end loop;

    O_top <= X"0000000";
    wait until rising_edge(CLK);

    for Verilog_Repeat in 0 to 100 loop
      wait until falling_edge(CLK);
      report "fabric = " & integer'image(To_Integer(unsigned(I_top))) & " gold = " & integer'image(To_Integer(unsigned(I_top_gold)));
      if To_integer(unsigned(I_top)) /= To_integer(unsigned(I_top_gold)) then
        report "Error: Miss match between fabric output and golden " severity error; 
      end if;
    end loop;
    report "SIMULATION FINISHED";

  end process;
end architecture;

