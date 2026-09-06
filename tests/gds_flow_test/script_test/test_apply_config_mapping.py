"""Tests for apply_config_mapping: moving latch pins onto frame port nets."""

from fabulous.fabric_generator.gds_generator.script.apply_config_mapping import apply


class FakeNet:
    """A net that knows which block ports sit on it."""

    def __init__(self, name: str, bterms: list[str]) -> None:
        self._name = name
        self._bterms = bterms

    def getName(self) -> str:  # noqa: D102, N802
        return self._name

    def getBTerms(self) -> list[object]:  # noqa: D102, N802
        return [FakeBTerm(name) for name in self._bterms]


class FakeBTerm:
    """A block port on a net."""

    def __init__(self, name: str) -> None:
        self._name = name

    def getName(self) -> str:  # noqa: D102, N802
        return self._name


class FakeITerm:
    """An instance pin that records the net it is connected to."""

    def __init__(self, block: "FakeBlock", key: tuple[str, str]) -> None:
        self._block = block
        self._key = key

    def getNet(self) -> FakeNet | None:  # noqa: D102, N802
        name = self._block.pins[self._key]
        return None if name is None else self._block.nets[name]

    def disconnect(self) -> None:  # noqa: D102
        self._block.pins[self._key] = None

    def connect(self, net: FakeNet) -> None:  # noqa: D102
        self._block.pins[self._key] = net.getName()


class FakeInst:
    """An instance that finds its pins by name."""

    def __init__(self, block: "FakeBlock", name: str) -> None:
        self._block = block
        self._name = name

    def findITerm(self, pin: str) -> FakeITerm | None:  # noqa: D102, N802
        if (self._name, pin) not in self._block.pins:
            return None
        return FakeITerm(self._block, (self._name, pin))


class FakeBlock:
    """A block holding named nets and the net every instance pin sits on."""

    def __init__(
        self, nets: dict[str, list[str]], pins: dict[tuple[str, str], str | None]
    ) -> None:
        self.nets = {name: FakeNet(name, bterms) for name, bterms in nets.items()}
        self.pins = dict(pins)

    def findInst(self, name: str) -> FakeInst | None:  # noqa: D102, N802
        if not any(instance == name for instance, _ in self.pins):
            return None
        return FakeInst(self, name)

    def findNet(self, name: str) -> FakeNet | None:  # noqa: D102, N802
        return self.nets.get(name)

    def net_of(self, instance: str, pin: str) -> str | None:
        """Return the name of the net the pin sits on."""
        return self.pins[(instance, pin)]


def test_apply_moves_only_pins_whose_net_differs() -> None:
    block = FakeBlock(
        nets={
            "FrameData[0]": ["FrameData[0]"],
            "FrameData[1]": ["FrameData[1]"],
            "FrameStrobe[0]": ["FrameStrobe[0]"],
        },
        pins={("lat", "D"): "FrameData[0]", ("lat", "GATE"): "FrameStrobe[0]"},
    )

    moved, errors = apply(
        block, {"lat": {"D": "FrameData[1]", "GATE": "FrameStrobe[0]"}}
    )

    assert (moved, errors) == (1, [])
    assert block.net_of("lat", "D") == "FrameData[1]"
    assert block.net_of("lat", "GATE") == "FrameStrobe[0]"


def test_apply_reports_a_pin_that_is_not_on_a_frame_port_net() -> None:
    block = FakeBlock(
        nets={"FrameData[1]": ["FrameData[1]"], "buf_out": []},
        pins={("lat", "D"): "buf_out"},
    )

    moved, errors = apply(block, {"lat": {"D": "FrameData[1]"}})

    assert moved == 0
    assert errors == ["lat/D sits on net buf_out, not directly on a frame port net"]


def test_apply_reports_a_frame_net_without_its_port() -> None:
    block = FakeBlock(
        nets={"FrameData[0]": [], "FrameData[1]": ["FrameData[1]"]},
        pins={("lat", "D"): "FrameData[0]"},
    )

    moved, errors = apply(block, {"lat": {"D": "FrameData[1]"}})

    assert moved == 0
    assert errors == [
        "lat/D sits on net FrameData[0], not directly on a frame port net"
    ]


def test_apply_reports_a_missing_instance_pin_and_target() -> None:
    block = FakeBlock(
        nets={"FrameData[0]": ["FrameData[0]"]},
        pins={("lat", "D"): "FrameData[0]"},
    )

    moved, errors = apply(
        block,
        {
            "ghost": {"D": "FrameData[0]"},
            "lat": {"GATE": "FrameData[0]", "D": "FrameData[9]"},
        },
    )

    assert moved == 0
    assert errors == [
        "instance ghost is not in the block",
        "lat has no pin GATE",
        "target net FrameData[9] is not in the block",
    ]
