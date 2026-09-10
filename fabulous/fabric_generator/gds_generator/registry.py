"""Type-preserving registration decorators for LibreLane flows and steps.

LibreLane annotates its registration decorators as
`Callable[[Type[Flow]], Type[Flow]]` (and the `Step` equivalent), so a decorated
class is erased to its base type and every keyword argument at a construction
site is checked against `Flow.__init__` rather than the real signature. Both
decorators return the class unchanged, so re-attaching the concrete type costs
nothing at runtime. Delete this module once the upstream decorators are generic.
"""

from librelane.flows.flow import Flow
from librelane.steps.step import Step


def register_flow[F: type[Flow]](cls: F) -> F:
    """Register a flow with LibreLane, keeping its concrete type.

    Parameters
    ----------
    cls : F
        The flow class to register.

    Returns
    -------
    F
        `cls`, unchanged.
    """
    Flow.factory.register()(cls)
    return cls


def register_step[S: type[Step]](cls: S) -> S:
    """Register a step with LibreLane, keeping its concrete type.

    Parameters
    ----------
    cls : S
        The step class to register.

    Returns
    -------
    S
        `cls`, unchanged.
    """
    Step.factory.register()(cls)
    return cls
