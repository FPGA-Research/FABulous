"""Step substitution for `WhileStep`'s internal loop body.

LibreLane's `SequentialFlow.Substitute`/`meta.substituting_steps` only walks a
flow's top-level `Steps` list, so it cannot see steps nested inside a
`WhileStep` (a FABulous-authored composite, not a LibreLane built-in). This
module reproduces the same matching/replace semantics for that nested list,
so `gds_config.yaml` can target loop-internal steps with identical syntax.
"""

import fnmatch

from librelane.flows.flow import FlowException
from librelane.flows.sequential import Substitution, SubstitutionsObject
from librelane.steps.step import Step

__all__ = ["apply_step_substitutions"]


def _substitute_one(
    steps: list[type[Step]],
    id: str,  # noqa: A002
    with_step: Substitution,
) -> None:
    mode = "replace"
    if id.startswith("+"):
        id = id[1:]  # noqa: A001
        mode = "append"
        if with_step is None:
            raise FlowException("Cannot prepend or append None.")
    elif id.startswith("-"):
        id = id[1:]  # noqa: A001
        mode = "prepend"
        if with_step is None:
            raise FlowException("Cannot prepend or append None.")

    step_indices = [
        i
        for i, step in enumerate(steps)
        if step.id != NotImplemented and fnmatch.fnmatch(step.id.lower(), id.lower())
    ]
    if not step_indices:
        if with_step is None:
            raise FlowException(
                f"Could not remove '{id}': no steps with ID '{id}' found in loop body"
            )
        raise FlowException(
            f"Could not {mode} '{id}' with '{with_step}': no steps with ID "
            f"'{id}' found in loop body."
        )

    if with_step is None:
        for index in reversed(step_indices):
            del steps[index]
        return

    resolved_step = with_step
    if isinstance(resolved_step, str):
        found = Step.factory.get(resolved_step)
        if found is None:
            raise FlowException(
                f"Could not {mode} '{id}' with '{resolved_step}': no replacement "
                f"step with ID '{resolved_step}' found."
            )
        resolved_step = found

    for i in step_indices:
        if mode == "replace":
            steps[i] = resolved_step
        elif mode == "append":
            steps.insert(i + 1, resolved_step)
        elif mode == "prepend":
            steps.insert(i, resolved_step)


def apply_step_substitutions(
    steps: list[type[Step]],
    substitutions: SubstitutionsObject,
) -> list[type[Step]]:
    """Apply LibreLane-style step substitutions to a nested step list.

    Parameters
    ----------
    steps : list[type[Step]]
        The loop body to substitute into. Not mutated; a copy is returned.
    substitutions : SubstitutionsObject
        A dict or list of (id, step) tuples, using the same syntax as
        LibreLane's `meta.substituting_steps`: a bare id replaces, `+id`
        appends after, `-id` prepends before, and a `None` value removes.

    Returns
    -------
    list[type[Step]]
        The resulting step list.
    """
    result = list(steps)
    items = substitutions.items() if isinstance(substitutions, dict) else substitutions
    for id, with_step in items:  # noqa: A001
        _substitute_one(result, id, with_step)
    return result
