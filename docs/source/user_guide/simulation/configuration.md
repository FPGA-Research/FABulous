(fabric-configuration)=
# Fabric configuration

FABulous fabrics can be loaded with a bitstream through one of three
configuration methods. For how to run a simulation, see
[Simulation setup](simulation.md).

:::{note}
The FABulous testbench currently drives configuration only through the
**parallel port (Mode 1)**. Serial (Mode 0) and Bitbang are supported by the
fabric RTL but are not yet exercised by the generated testbench.
:::

## Parallel (Mode 1) — default in testbench

Configuration data is written directly into the fabric through a 32-bit
parallel port, rather than shifted in bit-serially. This is the fastest of
the three methods and is the only one currently exercised by the FABulous
testbench.

- **Signals:** `SelfWriteData` (32-bit data bus), `SelfWriteStrobe` (write strobe)
- **Bus width:** 32 bits — each transfer loads 4 bytes of the bitstream
- **Timing:** for each word, data is held for 2 clock cycles, then
  `SelfWriteStrobe` is pulsed high for one clock cycle to latch it in,
  followed by 2 more idle cycles before the next word
- **Transfer count:** `MAX_BITBYTES / 4` word writes to load the full bitstream

## Serial (Mode 0)

Configuration is sent to the fabric byte-by-byte over a UART link on `Rx`,
decoded, and assembled into 32-bit words that feed the same write interface
used by Parallel mode.

- **Signals:** `Rx` (UART input), `WriteData` (32-bit, shared with parallel
  write path), `WriteStrobe`, `Command` (decoded command byte), `ComActive`,
  `ReceiveLED`
- **Frame format:** standard UART frame — 1 start bit, 8 data bits, 1 stop bit
- **Baud rate:** set by `ComRate = f_CLK / Baudrate` (default `217`, e.g. 25 MHz / 115200 baud)
- **Encoding modes:** `auto`, `hex` (2 ASCII hex chars per byte), or `bin`
  (raw byte), selected by the `Mode` parameter or auto-detected from the
  command byte
- **Framing:** each transfer begins with a fixed ID header and a command
  byte before data bytes are accepted
- **Word assembly:** 4 received bytes are packed into one `WriteData` word,
  then `WriteStrobe` pulses once per word — matching the Parallel-mode timing
- **Integrity check:** a running checksum is accumulated over the data and
  validated against an expected checksum value
- **Timeout:** an inactivity timeout resets the receiver to idle if no data
  arrives mid-transfer

## Bitbang configuration port (To be supported in the testbench)

We have produced a quick asynchronous serial configuration port interface that is ideal for microcontroller configuration. It uses the original CPU interface that we have in our TSMC chip. The idea of the protocol is as follows:

:::{figure} ./figs/bitbang1.*
:align: center
:alt: Bitbang description
:::

We drive s_clk and s_data. On each rising edge of s_clock, we sample data and on the falling edge, we sample control.

Both values get shifted in a separate register. If the control register sees the bit-pattern x"FAB0" it samples the data shift register into a hold register and issues a one-cycle strobe output (active 1).

The next figure shows the enable generation (and input sampling) for generating the enable signals for

- the control shift register and
- the data shift register.

:::{figure} ./figs/bitbang2.*
:align: center
:alt: An illustration of the signals used in the custom bitbang protocol as well as the decoding of these signals.
:::
