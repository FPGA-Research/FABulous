from dataclasses import dataclass

from FABulous.fabric_definition.enum_and_type import BitIdx, FrameIdx, Loc


@dataclass(slots=True, frozen=True)
class FeatureValue:
    tileLoc: Loc
    bitPosition: tuple[tuple[FrameIdx, BitIdx], ...] | tuple[tuple[None, None]]
    value: int | None


@dataclass
class FASMFeature:
    feature: str | None
    address: tuple[int, int] | None
    value: int | None
    annotation: dict[str, str] | None
