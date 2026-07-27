(fabric-configuration)=
# Fabric configuration

FABulous fabrics offer a 32-bit wide configuration port which can either be driven directly by e.g. a CPU or bus or by the two currently implemented configuration adapters, allowing the transmission over UART and a custom bitbang protocol.

## Parallel Port

Configuration data is written directly into the fabric through a 32-bit
parallel port, rather than shifted in bit-serially. This is the main configuration interface which is also used by the UART and bitbang configuration adapters.

- **Signals:** `SelfWriteData` (32-bit data bus), `SelfWriteStrobe` (write strobe)
- **Bus width:** 32 bits - each transfer loads 4 bytes of the bitstream
- **Timing:** Data must be valid on the bus for at least one clock cycle before `SelfWriteStrobe` is asserted, and held stable while the strobe is high.

## Configuration Adapters

To allow configuration from outside of a chip, currently two configuration adapters are implemented, allowing to upload a bitstream using a UART or a custom bitstream protocol.

###  UART

The configuration is sent to the fabric bit-by-bit over a UART link on `Rx` (since the adapter does not transmit anything, it's technically just a "UAR"),
decoded, and assembled into 32-bit words that feed the configuration port.

- **Signals:** `Rx` (UART input), `WriteData` (32-bit, output to the parallel
  config port), `WriteStrobe`, `Command` (decoded command byte), `ComActive`,
  `ReceiveLED`
- **Frame format:** standard UART frame — 1 start bit, 8 data bits, 1 stop bit
- **Baud rate:** set by `ComRate = f_CLK / Baudrate` (default `217`, e.g. 25 MHz / 115200 baud)
- **Encoding modes:** `auto`, `hex` (2 ASCII hex chars per byte), or `bin`
  (raw byte), selected by the `Mode` parameter or auto-detected from the
  command byte
- **Framing:** each transfer begins with a fixed ID header and a command
  byte before data bytes are accepted
- **Word assembly:** 4 received bytes are packed into one `WriteData` word,
  then `WriteStrobe` pulses once per word, as the configuration interface expects
- **Integrity check:** a running checksum is accumulated over the data and
  validated against an expected checksum value
- **Timeout:** an inactivity timeout resets the receiver to idle if no data
  arrives mid-transfer

### Bitbang

The bitbang adapter offers a quick asynchronous serial configuration port interface that is ideal for configuring the fabric via a microcontroller. The idea of the protocol is as follows:

:::{figure} ./figs/bitbang1.*
:align: center
:alt: Bitbang description
:::

### Bitbang

- **Signals:** `s_clk` and `s_data`, as well as a one-cycle strobe output (active 1).
- **Protocol:** Data is sampled on each rising edge of `s_clk`, and control is sampled on the falling edge.
- **Word assembly:** Both values get shifted in a separate register; if the control register sees the bit-pattern x"FAB0", it samples the data shift register into a hold register and issues a one-cycle strobe output (active 1).

The next figure shows the enable generation (and input sampling) for generating the enable signals for

- the control shift register and
- the data shift register.

:::{figure} ./figs/bitbang2.*
:align: center
:alt: An illustration of the signals used in the custom bitbang protocol as well as the decoding of these signals.
:::
