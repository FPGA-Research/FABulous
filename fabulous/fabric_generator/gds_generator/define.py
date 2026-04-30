"""Shared tile optimisation mode definitions."""

from enum import StrEnum


class OptMode(StrEnum):
    """Optimisation modes for tile size finding."""

    FIND_MIN_WIDTH = "find_min_width"
    FIND_MIN_HEIGHT = "find_min_height"
    BALANCE = "balance"
    LARGE = "large"
    NO_OPT = "no_opt"

    @classmethod
    def _missing_(cls, value: object) -> "OptMode":
        """Look up an OptMode member case-insensitively."""
        if isinstance(value, str):
            value_lower = value.lower()
            for member in cls:
                if member.value == value_lower:
                    return member

        if value is None:
            return cls.NO_OPT

        raise ValueError(f"{value!r} is not a valid {cls.__name__}")
