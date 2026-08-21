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

The bitbang adapter offers a quick asynchronous serial configuration port interface that is ideal for configuring the fabric via a microcontroller. Two pins carry the whole protocol, because every `s_clk` period transports one configuration data bit on its rising edge and one control bit on its falling edge.

:::{wavedrom} ./figs/bitbang1.json
:align: center
:alt: Timing diagram of one bitbang word. Each rising edge of s_clk shifts a bit into the 32-bit serial_data register and each falling edge shifts a bit into the 16-bit serial_control register, and the word is released to the configuration port once serial_control holds 0xFAB1.
:caption: Transfer of one word, carrying `0xDEADBEEF` on the rising-edge lane and sixteen zeros followed by `0xFAB1` on the falling-edge lane. The diagram is drawn against `s_clk`, so the single-`clk` `strobe` pulse appears far wider than it is.
:::

- **Signals:** `s_clk` and `s_data` are the two serial inputs, `data[31:0]`, `strobe` and `active` the outputs, and `clk` and `reset_n` the fabric-side clock and reset.
- **Sampling:** `s_clk` and `s_data` are asynchronous to `clk` and pass through a four-stage synchroniser, so each register update lags its `s_clk` edge by several `clk` cycles. The edge detector compares two consecutive synchroniser taps, so each `s_clk` phase has to span at least one full `clk` period to be seen at all.
- **Protocol:** a rising edge of `s_clk` shifts `s_data` into the 32-bit `serial_data` register and a falling edge shifts it into the 16-bit `serial_control` register. Both registers shift MSB first.
- **Word assembly:** reaching `0xFAB1` in `serial_control` copies `serial_data` into the `data` output register and pulses `strobe` high for one `clk` cycle. One word therefore spans 32 `s_clk` periods, of which the last 16 falling edges spell out `0xFAB1`. `serial_control` holds `0xFAB1` until the next falling edge shifts it out, but `strobe` still pulses only once.
- **Activity flag:** `0xFAB1` also raises `active` and `0xFAB0` clears it. While `active` is high the fabric takes its configuration word and strobe from the bitbang adapter rather than the parallel port, and the rising edge of `active` returns the configuration state machine to its unsynced state.

The next figure shows how the synchroniser chain generates the two shift enables. The control shift register is enabled when the older tap is high and the newer one low, and the data shift register when the pattern is reversed.

:::{figure} ./figs/bitbang2.*
:align: center
:alt: Schematic of the four-stage s_clk synchroniser, whose last two taps feed two AND gates producing control_shift_enable and data_shift_enable.
:::
