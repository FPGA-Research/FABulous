-- This VHDL was converted from Verilog using the
-- Icarus Verilog VHDL Code Generator 11.0 (stable) ()

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module top_wrapper (top_wrapper.v:3)
entity top_wrapper is
end entity; 

-- Generated from Verilog module top_wrapper (top_wrapper.v:3)
architecture from_verilog of top_wrapper is
  signal clk : std_logic;  -- Declared at top_wrapper.v:35
  signal io_in : unsigned(27 downto 0);  -- Declared at top_wrapper.v:5
  signal io_oeb : unsigned(27 downto 0);  -- Declared at top_wrapper.v:5
  signal io_out : unsigned(27 downto 0);  -- Declared at top_wrapper.v:5
  signal LPM_q_ivl_0 : std_logic;
  signal LPM_q_ivl_2 : std_logic;
  signal LPM_q_ivl_6 : std_logic;
  signal LPM_q_ivl_8 : std_logic;
  signal LPM_q_ivl_12 : std_logic;
  signal LPM_q_ivl_14 : std_logic;
  signal LPM_q_ivl_18 : std_logic;
  signal LPM_q_ivl_20 : std_logic;
  signal LPM_q_ivl_24 : std_logic;
  signal LPM_q_ivl_26 : std_logic;
  signal LPM_q_ivl_30 : std_logic;
  signal LPM_q_ivl_32 : std_logic;
  signal LPM_q_ivl_36 : std_logic;
  signal LPM_q_ivl_38 : std_logic;
  signal LPM_q_ivl_42 : std_logic;
  signal LPM_q_ivl_44 : std_logic;
  signal LPM_q_ivl_48 : std_logic;
  signal LPM_q_ivl_50 : std_logic;
  signal LPM_q_ivl_54 : std_logic;
  signal LPM_q_ivl_56 : std_logic;
  signal LPM_q_ivl_60 : std_logic;
  signal LPM_q_ivl_62 : std_logic;
  signal LPM_q_ivl_66 : std_logic;
  signal LPM_q_ivl_68 : std_logic;
  signal LPM_q_ivl_72 : std_logic;
  signal LPM_q_ivl_74 : std_logic;
  signal LPM_q_ivl_78 : std_logic;
  signal LPM_q_ivl_80 : std_logic;
  signal LPM_q_ivl_84 : std_logic;
  signal LPM_q_ivl_86 : std_logic;
  signal LPM_q_ivl_90 : std_logic;
  signal LPM_q_ivl_92 : std_logic;
  signal LPM_q_ivl_96 : std_logic;
  signal LPM_q_ivl_98 : std_logic;
  signal LPM_q_ivl_102 : std_logic;
  signal LPM_q_ivl_104 : std_logic;
  signal LPM_q_ivl_108 : std_logic;
  signal LPM_q_ivl_110 : std_logic;
  signal LPM_q_ivl_114 : std_logic;
  signal LPM_q_ivl_116 : std_logic;
  signal LPM_q_ivl_120 : std_logic;
  signal LPM_q_ivl_122 : std_logic;
  signal LPM_q_ivl_126 : std_logic;
  signal LPM_q_ivl_128 : std_logic;
  signal LPM_q_ivl_132 : std_logic;
  signal LPM_q_ivl_134 : std_logic;
  signal LPM_q_ivl_138 : std_logic;
  signal LPM_q_ivl_140 : std_logic;
  signal LPM_q_ivl_144 : std_logic;
  signal LPM_q_ivl_146 : std_logic;
  signal LPM_q_ivl_150 : std_logic;
  signal LPM_q_ivl_152 : std_logic;
  signal LPM_q_ivl_156 : std_logic;
  signal LPM_q_ivl_158 : std_logic;
  signal LPM_q_ivl_162 : std_logic;
  signal LPM_q_ivl_164 : std_logic;
  signal LPM_d0_ivl_168 : std_logic;
  signal LPM_d1_ivl_168 : std_logic;
  signal LPM_d2_ivl_168 : std_logic;
  signal LPM_d3_ivl_168 : std_logic;
  signal LPM_d4_ivl_168 : std_logic;
  signal LPM_d5_ivl_168 : std_logic;
  signal LPM_d6_ivl_168 : std_logic;
  signal LPM_d7_ivl_168 : std_logic;
  signal LPM_d8_ivl_168 : std_logic;
  signal LPM_d9_ivl_168 : std_logic;
  signal LPM_d10_ivl_168 : std_logic;
  signal LPM_d11_ivl_168 : std_logic;
  signal LPM_d12_ivl_168 : std_logic;
  signal LPM_d13_ivl_168 : std_logic;
  signal LPM_d14_ivl_168 : std_logic;
  signal LPM_d15_ivl_168 : std_logic;
  signal LPM_d16_ivl_168 : std_logic;
  signal LPM_d17_ivl_168 : std_logic;
  signal LPM_d18_ivl_168 : std_logic;
  signal LPM_d19_ivl_168 : std_logic;
  signal LPM_d20_ivl_168 : std_logic;
  signal LPM_d21_ivl_168 : std_logic;
  signal LPM_d22_ivl_168 : std_logic;
  signal LPM_d23_ivl_168 : std_logic;
  signal LPM_d24_ivl_168 : std_logic;
  signal LPM_d25_ivl_168 : std_logic;
  signal LPM_d26_ivl_168 : std_logic;
  signal LPM_d27_ivl_168 : std_logic;
  
  component IO_1_bidirectional_frame_config_pass is
    port (
      I : in std_logic;
      I_top : out std_logic;
      O : out std_logic;
      O_top : in std_logic;
      Q : out std_logic;
      T : in std_logic;
      T_top : out std_logic;
      UserCLK : in std_logic
    );
  end component;
  
  component top is
    port (
      clk : in std_logic;
      io_in : in unsigned(27 downto 0);
      io_oeb : out unsigned(27 downto 0);
      io_out : out unsigned(27 downto 0)
    );
  end component;
begin
  LPM_q_ivl_0 <= io_out(27);
  LPM_q_ivl_2 <= io_oeb(27);
  LPM_q_ivl_6 <= io_out(26);
  LPM_q_ivl_8 <= io_oeb(26);
  LPM_q_ivl_12 <= io_out(25);
  LPM_q_ivl_14 <= io_oeb(25);
  LPM_q_ivl_18 <= io_out(24);
  LPM_q_ivl_20 <= io_oeb(24);
  LPM_q_ivl_24 <= io_out(23);
  LPM_q_ivl_26 <= io_oeb(23);
  LPM_q_ivl_30 <= io_out(22);
  LPM_q_ivl_32 <= io_oeb(22);
  LPM_q_ivl_36 <= io_out(21);
  LPM_q_ivl_38 <= io_oeb(21);
  LPM_q_ivl_42 <= io_out(20);
  LPM_q_ivl_44 <= io_oeb(20);
  LPM_q_ivl_48 <= io_out(19);
  LPM_q_ivl_50 <= io_oeb(19);
  LPM_q_ivl_54 <= io_out(18);
  LPM_q_ivl_56 <= io_oeb(18);
  LPM_q_ivl_60 <= io_out(17);
  LPM_q_ivl_62 <= io_oeb(17);
  LPM_q_ivl_66 <= io_out(16);
  LPM_q_ivl_68 <= io_oeb(16);
  LPM_q_ivl_72 <= io_out(15);
  LPM_q_ivl_74 <= io_oeb(15);
  LPM_q_ivl_78 <= io_out(14);
  LPM_q_ivl_80 <= io_oeb(14);
  LPM_q_ivl_84 <= io_out(13);
  LPM_q_ivl_86 <= io_oeb(13);
  LPM_q_ivl_90 <= io_out(12);
  LPM_q_ivl_92 <= io_oeb(12);
  LPM_q_ivl_96 <= io_out(11);
  LPM_q_ivl_98 <= io_oeb(11);
  LPM_q_ivl_102 <= io_out(10);
  LPM_q_ivl_104 <= io_oeb(10);
  LPM_q_ivl_108 <= io_out(9);
  LPM_q_ivl_110 <= io_oeb(9);
  LPM_q_ivl_114 <= io_out(8);
  LPM_q_ivl_116 <= io_oeb(8);
  LPM_q_ivl_120 <= io_out(7);
  LPM_q_ivl_122 <= io_oeb(7);
  LPM_q_ivl_126 <= io_out(6);
  LPM_q_ivl_128 <= io_oeb(6);
  LPM_q_ivl_132 <= io_out(5);
  LPM_q_ivl_134 <= io_oeb(5);
  LPM_q_ivl_138 <= io_out(4);
  LPM_q_ivl_140 <= io_oeb(4);
  LPM_q_ivl_144 <= io_out(3);
  LPM_q_ivl_146 <= io_oeb(3);
  LPM_q_ivl_150 <= io_out(2);
  LPM_q_ivl_152 <= io_oeb(2);
  LPM_q_ivl_156 <= io_out(1);
  LPM_q_ivl_158 <= io_oeb(1);
  LPM_q_ivl_162 <= io_out(0);
  LPM_q_ivl_164 <= io_oeb(0);
  io_in <= LPM_d27_ivl_168 & LPM_d26_ivl_168 & LPM_d25_ivl_168 & LPM_d24_ivl_168 & LPM_d23_ivl_168 & LPM_d22_ivl_168 & LPM_d21_ivl_168 & LPM_d20_ivl_168 & LPM_d19_ivl_168 & LPM_d18_ivl_168 & LPM_d17_ivl_168 & LPM_d16_ivl_168 & LPM_d15_ivl_168 & LPM_d14_ivl_168 & LPM_d13_ivl_168 & LPM_d12_ivl_168 & LPM_d11_ivl_168 & LPM_d10_ivl_168 & LPM_d9_ivl_168 & LPM_d8_ivl_168 & LPM_d7_ivl_168 & LPM_d6_ivl_168 & LPM_d5_ivl_168 & LPM_d4_ivl_168 & LPM_d3_ivl_168 & LPM_d2_ivl_168 & LPM_d1_ivl_168 & LPM_d0_ivl_168;
  
  -- Generated from instantiation at top_wrapper.v:33
  io0_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_162,
      O => LPM_d0_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_164,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:23
  io10_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_102,
      O => LPM_d10_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_104,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:22
  io11_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_96,
      O => LPM_d11_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_98,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:21
  io12_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_90,
      O => LPM_d12_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_92,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:20
  io13_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_84,
      O => LPM_d13_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_86,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:19
  io14_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_78,
      O => LPM_d14_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_80,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:18
  io15_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_72,
      O => LPM_d15_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_74,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:17
  io16_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_66,
      O => LPM_d16_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_68,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:16
  io17_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_60,
      O => LPM_d17_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_62,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:15
  io18_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_54,
      O => LPM_d18_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_56,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:14
  io19_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_48,
      O => LPM_d19_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_50,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:32
  io1_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_156,
      O => LPM_d1_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_158,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:13
  io20_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_42,
      O => LPM_d20_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_44,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:12
  io21_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_36,
      O => LPM_d21_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_38,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:11
  io22_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_30,
      O => LPM_d22_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_32,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:10
  io23_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_24,
      O => LPM_d23_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_26,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:9
  io24_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_18,
      O => LPM_d24_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_20,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:8
  io25_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_12,
      O => LPM_d25_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_14,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:7
  io26_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_6,
      O => LPM_d26_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_8,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:6
  io27_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_0,
      O => LPM_d27_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_2,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:31
  io2_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_150,
      O => LPM_d2_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_152,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:30
  io3_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_144,
      O => LPM_d3_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_146,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:29
  io4_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_138,
      O => LPM_d4_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_140,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:28
  io5_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_132,
      O => LPM_d5_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_134,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:27
  io6_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_126,
      O => LPM_d6_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_128,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:26
  io7_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_120,
      O => LPM_d7_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_122,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:25
  io8_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_114,
      O => LPM_d8_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_116,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:24
  io9_i: IO_1_bidirectional_frame_config_pass
    port map (
      I => LPM_q_ivl_108,
      O => LPM_d9_ivl_168,
      O_top => 'Z',
      T => LPM_q_ivl_110,
      UserCLK => 'Z'
    );
  
  -- Generated from instantiation at top_wrapper.v:38
  top_i: top
    port map (
      clk => clk,
      io_in => io_in,
      io_oeb => io_oeb,
      io_out => io_out
    );
  clk <= 'Z';
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Generated from Verilog module IO_1_bidirectional_frame_config_pass (../../../fabric_files/generic/IO_1_bidirectional_frame_config_pass.v:4)
entity IO_1_bidirectional_frame_config_pass is
  port (
    I : in std_logic;
    I_top : out std_logic;
    O : out std_logic;
    O_top : in std_logic;
    Q : out std_logic;
    T : in std_logic;
    T_top : out std_logic;
    UserCLK : in std_logic
  );
end entity; 

-- Generated from Verilog module IO_1_bidirectional_frame_config_pass (../../../fabric_files/generic/IO_1_bidirectional_frame_config_pass.v:4)
architecture from_verilog of IO_1_bidirectional_frame_config_pass is
  signal Q_Reg : std_logic;
begin
  Q <= Q_Reg;
  O <= O_top;
  I_top <= I;
  T_top <= not T;
  
  -- Generated from always process in IO_1_bidirectional_frame_config_pass (../../../fabric_files/generic/IO_1_bidirectional_frame_config_pass.v:30)
  process (UserCLK) is
  begin
    if rising_edge(UserCLK) then
      Q_Reg <= O_top;
    end if;
  end process;
end architecture;


