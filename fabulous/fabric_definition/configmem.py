"""Configuration memory of a frame-based tile.

The tile stores its configuration bits in latches on a grid of `FrameData` lines
crossing `FrameStrobe` lines. Which logical bit each crosspoint holds is a free
choice, recorded one frame per strobe line in the tile's `<tile>_ConfigMem.csv`.
`ConfigMem` is the in-memory form of that file and the one place the choice is
read from and written to, so the HDL generator, the bitstream specification and
any remapping of the bits agree on the encoding by construction.
"""

import csv
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Self

CONFIG_MEM_CSV_FIELDS = (
    "frame_name",
    "frame_index",
    "bits_used_in_frame",
    "used_bits_mask",
    "ConfigBits_ranges",
)

NULL_RANGE = "# NULL"
"""The `ConfigBits_ranges` entry of a frame that holds no bit."""


class Crosspoint(NamedTuple):
    """A frame grid position: `FrameData[data_bit]` crossing `FrameStrobe[frame]`."""

    frame: int
    data_bit: int


@dataclass(frozen=True, eq=True)
class ConfigMemFrame:
    """One frame of the configuration memory, one row of the `ConfigMem.csv`.

    The frame is the logical bit it holds on each of its `FrameData` lines, and
    nothing else; the CSV columns are that map in the file's form.
    `usedBitMask` reads left to right from `FrameData[width - 1]` down to
    `FrameData[0]`, and the n-th `1` binds `configBitRanges[n]`, so a frame
    cannot describe a mask and a range list that disagree.

    Attributes
    ----------
    frameName : str
        The name of the frame
    frameIndex : int
        The index of the frame
    width : int
        The number of `FrameData` lines the frame spans
    bits : dict[int, int]
        The logical configuration bit on each used `FrameData` line
    """

    frameName: str
    frameIndex: int
    width: int
    bits: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject a line outside the frame or a negative configuration bit."""
        for line, bit in self.bits.items():
            if not 0 <= line < self.width:
                raise ValueError(
                    f"{self.frameName} holds a bit on FrameData[{line}], outside "
                    f"its {self.width} lines."
                )
            if bit < 0:
                raise ValueError(
                    f"Configuration bit index {bit} in {self.frameName} is negative."
                )

    @property
    def lines(self) -> list[int]:
        """The used `FrameData` lines, highest line first, the mask read order."""
        return sorted(self.bits, reverse=True)

    @property
    def bitsUsedInFrame(self) -> int:
        """The number of bits the frame holds."""
        return len(self.bits)

    @property
    def usedBitMask(self) -> str:
        """Which `FrameData` lines are used, from the highest line down."""
        return "".join(
            "1" if self.width - 1 - k in self.bits else "0" for k in range(self.width)
        )

    @property
    def configBitRanges(self) -> list[int]:
        """The bits of the used lines, in mask order."""
        return [self.bits[line] for line in self.lines]


def _parse_ranges(text: str) -> list[int]:
    """Read a `ConfigBits_ranges` entry: `a:b`, `x;y;z`, one integer or NULL."""
    text = text.replace(" ", "").replace("\t", "")
    if ":" in text:
        left, right = (int(v) for v in text.split(":"))
        if right < left:
            return list(range(left, right - 1, -1))
        return list(range(left, right + 1))
    if ";" in text:
        return [int(item) for item in text.split(";")]
    if text.isdigit():
        return [int(text)]
    if "NULL" in text:
        return []
    raise ValueError(
        f"Range {text} is not a valid format. It should be in the form "
        "[int]:[int] or [int]. If there are multiple ranges it should be "
        "separated by ';'."
    )


def _format_ranges(bits: list[int]) -> str:
    """Write bits as `hi:lo` for a descending run, else `;`-separated."""
    if not bits:
        return NULL_RANGE
    if len(bits) > 1 and bits == list(range(bits[0], bits[0] - len(bits), -1)):
        return f"{bits[0]}:{bits[-1]}"
    return ";".join(str(bit) for bit in bits)


@dataclass(frozen=True)
class ConfigMem:
    """The configuration memory of a tile, one frame per `FrameStrobe` line.

    `frames` holds every frame in index order, empty frames included, so the
    memory describes its own grid of `len(frames)` strobe lines by
    `frame_bits_per_row` data lines without the fabric parameters. `validate`
    checks it against them where they are known.

    Attributes
    ----------
    frames : tuple[ConfigMemFrame, ...]
        Every frame in index order.
    frame_bits_per_row : int
        Width of every frame, the number of `FrameData` lines.
    source : Path | None
        The file the memory was read from, named in validation errors.
    """

    frames: tuple[ConfigMemFrame, ...]
    frame_bits_per_row: int
    source: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        """Reject frames out of order, of mixed width, or allocating a bit twice."""
        indices = [frame.frameIndex for frame in self.frames]
        if indices != list(range(len(self.frames))):
            raise ValueError(
                f"{self._where} frames must be indexed 0 .. n-1 in order, got {indices}"
            )
        seen: set[int] = set()
        for frame in self.frames:
            if frame.width != self.frame_bits_per_row:
                raise ValueError(
                    f"{self._where} has a too long or short bitmask for frame : "
                    f"{frame.frameName}"
                )
            for bit in frame.bits.values():
                if bit in seen:
                    raise ValueError(
                        f"Configuration bit index {bit} already allocated in "
                        f"{self._where}, {frame.frameName}."
                    )
                seen.add(bit)

    @property
    def _where(self) -> str:
        """Name the memory in an error, by its file where it has one."""
        if self.source is None:
            return "Configuration memory"
        return f"bitstream mapping file {self.source}"

    @property
    def max_frames_per_col(self) -> int:
        """Number of frames, the number of `FrameStrobe` lines."""
        return len(self.frames)

    @property
    def used_frames(self) -> tuple[ConfigMemFrame, ...]:
        """The frames holding at least one bit, in index order."""
        return tuple(frame for frame in self.frames if frame.bitsUsedInFrame > 0)

    @property
    def config_bits(self) -> int:
        """Number of bits the memory holds."""
        return sum(frame.bitsUsedInFrame for frame in self.frames)

    @property
    def frame_names(self) -> dict[int, str]:
        """Frame name per frame index."""
        return {frame.frameIndex: frame.frameName for frame in self.frames}

    @property
    def bit_at(self) -> dict[Crosspoint, int]:
        """The logical bit at each occupied crosspoint, in frame then mask order."""
        return {
            Crosspoint(frame.frameIndex, line): frame.bits[line]
            for frame in self.frames
            for line in frame.lines
        }

    @property
    def crosspoint_of(self) -> dict[int, Crosspoint]:
        """The crosspoint holding each logical bit."""
        return {bit: crosspoint for crosspoint, bit in self.bit_at.items()}

    @property
    def free_crosspoints(self) -> list[Crosspoint]:
        """Unoccupied crosspoints in frame then mask order, highest data line first."""
        return [
            Crosspoint(frame.frameIndex, line)
            for frame in self.frames
            for line in range(self.frame_bits_per_row - 1, -1, -1)
            if line not in frame.bits
        ]

    def validate(
        self, *, frame_bits_per_row: int, max_frames_per_col: int, config_bits: int
    ) -> Self:
        """Check the memory against the fabric's frame parameters and a bit count.

        Parameters
        ----------
        frame_bits_per_row : int
            The fabric's `FrameBitsPerRow`.
        max_frames_per_col : int
            The fabric's `MaxFramesPerCol`.
        config_bits : int
            The number of bits the memory must hold.

        Returns
        -------
        Self
            The memory itself, so a load can be validated in one expression.

        Raises
        ------
        ValueError
            If the frame count, a frame width or the total bit count differs.
        """
        if self.max_frames_per_col != max_frames_per_col:
            raise ValueError(
                f"The bitstream mapping file has only {self.max_frames_per_col} "
                f"entries but MaxFramesPerCol is {max_frames_per_col}."
            )
        for frame in self.frames:
            if frame.usedBitMask.count("1") > frame_bits_per_row:
                raise ValueError(
                    f"{self._where} has to many 1-elements in bitmask for frame : "
                    f"{frame.frameName}"
                )
        if self.frame_bits_per_row != frame_bits_per_row:
            raise ValueError(
                f"{self._where} has a too long or short bitmask for frame : "
                f"{self.frames[0].frameName}"
            )
        if self.config_bits != config_bits:
            raise ValueError(
                f"{self._where} has a bitmask mismatch; bitmask has in total "
                f"{self.config_bits} 1-values for {config_bits} bits."
            )
        return self

    @classmethod
    def from_csv(cls, path: Path) -> Self:
        """Read a `ConfigMem.csv`.

        The row count and the mask width give the grid; `bits_used_in_frame` is
        ignored and recomputed from the mask. A range is `hi:lo` or `lo:hi` for
        one run, `x;y;z` for a list, one integer, or NULL for an empty frame.

        Parameters
        ----------
        path : Path
            The CSV to read.

        Returns
        -------
        Self
            The memory, with `source` set to `path`.

        Raises
        ------
        ValueError
            If a frame index or range entry is malformed, if a mask and its
            ranges disagree in count, if the frames are not 0 .. n-1 in order,
            if the masks differ in width, or if a bit is allocated twice or
            negative.
        """
        with path.absolute().open() as f:
            rows = list(csv.DictReader(f))
        frames: list[ConfigMemFrame] = []
        for row in rows:
            mask = row["used_bits_mask"].replace("_", "")
            try:
                ranges = _parse_ranges(row["ConfigBits_ranges"])
            except ValueError as exc:
                raise ValueError(f"{path}: {exc}") from exc
            lines = [len(mask) - 1 - k for k, char in enumerate(mask) if char == "1"]
            if len(lines) != len(ranges):
                raise ValueError(
                    f"{path}: frame {row['frame_name']} marks {len(lines)} data "
                    f"lines used but lists {len(ranges)} configuration bits; the "
                    "n-th 1 of the mask binds the n-th bit of the range."
                )
            frames.append(
                ConfigMemFrame(
                    frameName=row["frame_name"],
                    frameIndex=int(row["frame_index"]),
                    width=len(mask),
                    bits=dict(zip(lines, ranges, strict=True)),
                )
            )
        width = frames[0].width if frames else 0
        return cls(tuple(frames), width, source=path)

    def to_csv(self, path: Path) -> None:
        """Write the memory as a `ConfigMem.csv`.

        Masks are grouped in fours with `_`, a descending run of bits is
        written `hi:lo` and any other set `;`-separated, so every mapping
        round-trips through `from_csv`.

        Parameters
        ----------
        path : Path
            Destination file.
        """
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CONFIG_MEM_CSV_FIELDS)
            for frame in self.frames:
                mask = "_".join(
                    frame.usedBitMask[i : i + 4]
                    for i in range(0, len(frame.usedBitMask), 4)
                )
                writer.writerow(
                    [
                        frame.frameName,
                        frame.frameIndex,
                        frame.bitsUsedInFrame,
                        mask,
                        _format_ranges(frame.configBitRanges),
                    ]
                )

    @classmethod
    def default(
        cls, config_bits: int, *, frame_bits_per_row: int, max_frames_per_col: int
    ) -> Self:
        """Pack the bits from the highest down, filling frame 0 first.

        With 100 bits on 32-bit frames, frame 0 holds bits 99 down to 68 on
        `FrameData[31]` down to `FrameData[0]`, and frame 3 holds bits 3 to 0
        on its top four lines. This is the layout every fabric hardened so far
        assumes; a layout fitted to a placement is what the tile flow's
        configuration mapping produces instead.

        Parameters
        ----------
        config_bits : int
            The number of bits to place.
        frame_bits_per_row : int
            Width of every frame.
        max_frames_per_col : int
            Number of frames.

        Returns
        -------
        Self
            The enumerated mapping, empty frames included.

        Raises
        ------
        ValueError
            If the grid cannot hold the bits.
        """
        capacity = frame_bits_per_row * max_frames_per_col
        if config_bits > capacity:
            raise ValueError(
                f"Tile config bits ({config_bits}) exceed fabric capacity "
                f"({capacity} bits). Please adjust the tile configuration."
            )
        # One shared iterator, so each frame takes the bits the last one left.
        remaining = iter(range(config_bits - 1, -1, -1))
        frames = [
            ConfigMemFrame(
                f"frame{index}",
                index,
                frame_bits_per_row,
                dict(
                    zip(range(frame_bits_per_row - 1, -1, -1), remaining, strict=False)
                ),
            )
            for index in range(max_frames_per_col)
        ]
        return cls(tuple(frames), frame_bits_per_row)

    def rebuilt_with(self, bit_at: Mapping[Crosspoint, int]) -> Self:
        """Return the same grid and frame names holding these bits at these lines.

        Parameters
        ----------
        bit_at : Mapping[Crosspoint, int]
            The logical bit of every occupied crosspoint.

        Returns
        -------
        Self
            One frame per index, empty frames included.

        Raises
        ------
        ValueError
            If the bits are not exactly `0 .. n-1`, since neither the HDL
            generator nor the bitstream specification checks the upper bound,
            or if a crosspoint lies outside the grid.
        """
        bits = sorted(bit_at.values())
        if bits != list(range(len(bits))):
            raise ValueError(f"Mapped bits are not a contiguous range from 0: {bits}")
        for crosspoint in bit_at:
            if not (
                0 <= crosspoint.frame < self.max_frames_per_col
                and 0 <= crosspoint.data_bit < self.frame_bits_per_row
            ):
                raise ValueError(
                    f"Crosspoint {crosspoint} lies outside the "
                    f"{self.max_frames_per_col} x {self.frame_bits_per_row} frame grid"
                )
        frames = [
            ConfigMemFrame(
                frame.frameName,
                frame.frameIndex,
                self.frame_bits_per_row,
                {
                    crosspoint.data_bit: bit
                    for crosspoint, bit in bit_at.items()
                    if crosspoint.frame == frame.frameIndex
                },
            )
            for frame in self.frames
        ]
        return type(self)(tuple(frames), self.frame_bits_per_row)
