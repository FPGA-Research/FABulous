"""Configuration FSM model for cocotb testing.

This module provides a software model of the ConfigFSM behavior for proper
timing and protocol testing, similar to cocotbext-uart approach.
"""

from decimal import Decimal
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event, RisingEdge, Timer


class ConfigFSMModel:
    """Software model of ConfigFSM for proper timing behavior."""

    def __init__(
        self,
        clock: Any,  # noqa: ANN401
        reset: Any,  # noqa: ANN401
        write_data: Any,  # noqa: ANN401
        write_strobe: Any,  # noqa: ANN401
        fsm_reset: Any,  # noqa: ANN401
        frame_address_register: Any,  # noqa: ANN401
        long_frame_strobe: Any,  # noqa: ANN401
        row_select: Any,  # noqa: ANN401
        number_of_rows: int = 16,
        desync_flag: int = 20,
    ) -> None:
        """Initialize the ConfigFSM model.

        Args:
            clock: Clock signal
            reset: Reset signal (active low)
            write_data: 32-bit write data input
            write_strobe: Write strobe input
            fsm_reset: FSM reset input
            frame_address_register: Frame address register output
            long_frame_strobe: Long frame strobe output
            row_select: Row select output
            number_of_rows: Number of rows parameter
            desync_flag: Desync flag bit position
        """
        self.clock = clock
        self.reset = reset
        self.write_data = write_data
        self.write_strobe = write_strobe
        self.fsm_reset = fsm_reset
        self.frame_address_register = frame_address_register
        self.long_frame_strobe = long_frame_strobe
        self.row_select = row_select

        self.number_of_rows = number_of_rows
        self.desync_flag = desync_flag

        # Internal state
        self.state = 0  # 0=unsynched, 1=synched, 2=frame_data
        self.frame_shift_state = 0
        self.old_fsm_reset = False
        self.frame_strobe = False
        self.old_frame_strobe = False

        # Events for synchronization
        self.sync_event = Event()
        self.frame_complete_event = Event()

        # Start monitoring
        cocotb.start_soon(self._monitor())

    async def _monitor(self) -> None:
        """Monitor FSM behavior and update outputs."""
        while True:
            await RisingEdge(self.clock)

            # Check reset
            if not self.reset.value:
                self.state = 0
                self.frame_shift_state = 0
                self.frame_address_register = 0
                self.frame_strobe = False
                self.old_fsm_reset = False
                continue

            # Handle FSM_Reset rising edge detection
            current_fsm_reset = bool(self.fsm_reset.value)
            if not self.old_fsm_reset and current_fsm_reset:
                self.state = 0
                self.frame_shift_state = 0
            self.old_fsm_reset = current_fsm_reset

            # Clear frame strobe by default
            self.frame_strobe = False

            # FSM state machine
            if self.state == 0:  # Unsynched
                if self.write_strobe.value and int(self.write_data.value) == 0xFAB0FAB1:
                    self.state = 1
                    self.sync_event.set()
                    cocotb.log.debug("FSM: Entered synched state")

            elif self.state == 1:  # Synched - read header
                if self.write_strobe.value:
                    write_data_int = int(self.write_data.value)
                    if (write_data_int >> self.desync_flag) & 1:
                        # Desync bit set
                        self.state = 0
                        cocotb.log.debug("FSM: Desynced")
                    else:
                        # Store frame address
                        self.frame_address_register.value = write_data_int
                        self.frame_shift_state = self.number_of_rows
                        self.state = 2
                        cocotb.log.debug(
                            f"FSM: Frame address set to 0x{write_data_int:08x}"
                        )

            elif self.state == 2 and self.write_strobe.value:  # Frame data
                self.frame_shift_state -= 1
                if self.frame_shift_state == 0:
                    self.frame_strobe = True
                    self.state = 1
                    self.frame_complete_event.set()
                    cocotb.log.debug("FSM: Frame complete")

            # Update RowSelect (combinational logic)
            if self.write_strobe.value:
                self.row_select.value = self.frame_shift_state
            else:
                # All 1s for invalid (5-bit width = 0b11111 = 31)
                self.row_select = 0b11111

            # Update LongFrameStrobe (registered)
            self.long_frame_strobe.value = self.frame_strobe or self.old_frame_strobe
            self.old_frame_strobe = self.frame_strobe

    async def wait_for_sync(self, timeout_ns: int = 1000) -> None:
        """Wait for FSM to enter synched state."""
        timeout_event = Timer(Decimal(timeout_ns), units="ns")
        result = await cocotb.triggers.First(self.sync_event.wait(), timeout_event)
        if result == timeout_event:
            raise TimeoutError("Timeout waiting for FSM sync")
        self.sync_event.clear()

    async def wait_for_frame_complete(self, timeout_ns: int = 5000) -> None:
        """Wait for frame to complete."""
        timeout_event = Timer(Decimal(timeout_ns), units="ns")
        result = await cocotb.triggers.First(
            self.frame_complete_event.wait(), timeout_event
        )
        if result == timeout_event:
            raise TimeoutError("Timeout waiting for frame completion")
        self.frame_complete_event.clear()

    async def send_sync_pattern(self) -> None:
        """Send the sync pattern to enter synched state."""
        self.write_data = 0xFAB0FAB1
        self.write_strobe = 1
        await RisingEdge(self.clock)
        self.write_strobe = 0
        await self.wait_for_sync()

    async def send_frame_address(self, address: int) -> None:
        """Send frame address."""
        self.write_data.value = address
        self.write_strobe = 1
        await RisingEdge(self.clock)
        self.write_strobe = 0
        # Wait a bit for the register to update
        await Timer(Decimal(100), units="ps")

    async def send_frame_data(self, data_list: list[int]) -> None:
        """Send a sequence of frame data."""
        for data in data_list:
            self.write_data.value = data
            self.write_strobe = 1
            await RisingEdge(self.clock)
            self.write_strobe = 0
        await self.wait_for_frame_complete()


async def create_config_fsm_test_env(dut: Any) -> ConfigFSMModel:  # noqa: ANN401
    """Create a ConfigFSM test environment with proper timing model."""

    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize signals
    dut.WriteData = 0
    dut.WriteStrobe = 0
    dut.FSM_Reset = 0
    dut.resetn = 0

    # Reset sequence
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)
    dut.resetn = 1
    await RisingEdge(dut.CLK)

    # FSM Reset sequence
    dut.FSM_Reset = 1
    await RisingEdge(dut.CLK)
    dut.FSM_Reset = 0
    await RisingEdge(dut.CLK)

    # Create model instance
    return ConfigFSMModel(
        clock=dut.CLK,
        reset=dut.resetn,
        write_data=dut.WriteData,
        write_strobe=dut.WriteStrobe,
        fsm_reset=dut.FSM_Reset,
        frame_address_register=dut.FrameAddressRegister,
        long_frame_strobe=dut.LongFrameStrobe,
        row_select=dut.RowSelect,
    )
