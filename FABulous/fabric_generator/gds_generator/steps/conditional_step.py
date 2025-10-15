"""Conditional Step factory that conditionally runs an inner Step.

It returns a subclass of the given InnerStep. If the provided condition
evaluates to True, it simply calls ``super().run(...)``; otherwise it becomes
an intentional no-op and returns no updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from librelane.logging.logger import info

if TYPE_CHECKING:
    from collections.abc import Callable

    from librelane.config.config import Config
    from librelane.state.state import State
    from librelane.steps.step import Step


def _try_call_condition(
    cond: Callable[..., bool],
    *,
    cfg: Config,
    state: State,
    self_obj: object | None = None,
) -> bool:
    """Best-effort invocation for condition callables with flexible signatures."""
    for args in ((cfg, state), (cfg,), (state,), tuple()):
        try:
            return bool(cond(*args))
        except TypeError:
            continue
    if self_obj is not None:
        for args in (
            (self_obj, cfg, state),
            (self_obj, cfg),
            (self_obj, state),
            (self_obj,),
        ):
            try:
                return bool(cond(*args))
            except TypeError:
                continue
    try:
        return bool(cond())
    except TypeError:
        pass
    raise TypeError(
        "Condition callable has an unsupported signature. Expected one of: "
        "(config, state), (config), (state), or ()."
    )


def ConditionalStep(
    InnerStep: type[Step], condition: Callable[..., bool]
) -> type[Step]:
    """Return a Step subclass wrapping InnerStep based on a condition."""
    InnerStep.assert_concrete("wrapped by ConditionalStep")

    class _ConditionalWrapper(InnerStep):
        id: str = InnerStep.id
        _implementation_id = InnerStep.get_implementation_id()

        name = getattr(InnerStep, "name", InnerStep.__name__)
        long_name = getattr(
            InnerStep,
            "long_name",
            (f"Conditional({getattr(InnerStep, 'name', InnerStep.__name__)})"),
        )

        def run(self: Step, state_in: State, **kwargs: object) -> tuple[dict, dict]:
            should_run = _try_call_condition(
                condition, cfg=self.config, state=state_in, self_obj=self
            )
            if not should_run:
                info(f"Conditional skip: '{self.id}' condition evaluated to False")
                return {}, {}
            return InnerStep.run(self, state_in, **kwargs)

    _ConditionalWrapper.__name__ = f"Conditional_{InnerStep.__name__}"
    return _ConditionalWrapper


# Friendly alias with common misspelling
ConditonalStep = ConditionalStep
