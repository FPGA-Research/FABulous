"""Options for the multi-LUT morph-tile mapper.

The options bound the randomized group search and the final disjoint group selection so
the mapper remains predictable on larger LUT-mapped designs.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MultiMapOptions(BaseModel):
    """Configure multi-LUT grouping and selection.

    Attributes
    ----------
    model_config
        Pydantic model configuration.
    luts_per_group : int | list[int]
        Exact number, or allowed numbers, of LUT cells selected into one
        candidate group. A list lets the mapper try several group sizes, merge
        the SAT candidates, and let the final selector choose the best mix.
        This should usually match the architectural shapes being tested, such
        as two and three LUTs for different multi-output tile modes.
    min_boundary_inputs : int
        Minimum number of distinct external group inputs. Raising this can skip
        tiny or overly local groups that are unlikely to exercise the target
        tile.
    max_boundary_inputs : int
        Maximum number of distinct external group inputs. This is the main
        input-capacity filter and should not exceed the useful routable inputs
        of the candidate tile.
    min_boundary_outputs : int
        Minimum number of selected LUT outputs that leave the group. This is
        normally the number of observable functions the tile mode should
        replace.
    max_boundary_outputs : int
        Maximum number of selected LUT outputs that leave the group. Setting
        this equal to ``min_boundary_outputs`` forces an exact output boundary.
    max_graph_frontier : int
        Maximum local graph expansion candidates considered per growth step.
        Larger values explore more local alternatives but increase candidate
        generation time.
    max_graph_hops : int | None
        Optional LUT-to-LUT graph search depth override. If unset, graph search
        depth is derived from luts_per_group. Setting this can find wider
        fan-in/fan-out neighborhoods, but large values may create many groups.
    max_iterations : int
        Maximum randomized sampling attempts after deterministic seed search.
        This does not cap deterministic groups; it only controls the random
        phase.
    random_seed : int
        Seed used by the randomized group sampler. Deterministic seed search is
        stable and does not depend on this value.
    pure_random_match : float
        Fraction of random attempts that sample globally unrelated LUT groups.
        Values near one are useful when unrelated LUTs can still satisfy the
        boundary, such as when grouped LUT count equals boundary output count.
    connected_only : bool
        If true, only groups connected by LUT-to-LUT edges are sampled. Keeping
        this false allows independent LUTs with shared inputs to be packed
        together.
    max_stored_matches : int
        Maximum successful SAT matches retained in memory before final
        selection. If this cap is reached, lower-scoring SAT matches are
        discarded.
    max_selected_groups : int | None
        Optional cap on finally selected disjoint groups. This is useful for
        debugging or partial mapping runs; ``None`` means no explicit cap.
    enable_permute_cache : bool
        Whether input-permutation-equivalent group functions share SAT results.
        This should normally stay enabled because it avoids repeated SAT solves
        for the same multi-output function with renamed inputs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    luts_per_group: int | list[int] = 2
    min_boundary_inputs: int = Field(default=1, ge=0)
    max_boundary_inputs: int = Field(default=6, ge=0)
    min_boundary_outputs: int = Field(default=2, ge=1)
    max_boundary_outputs: int = Field(default=2, ge=1)
    max_graph_frontier: int = Field(default=16, ge=1)
    max_graph_hops: int | None = Field(default=None, ge=1)
    max_iterations: int = Field(default=10_000, ge=1)
    random_seed: int = 1
    pure_random_match: float = Field(default=0.0, ge=0.0, le=1.0)
    connected_only: bool = False
    max_stored_matches: int = Field(default=10_000, ge=1)
    max_selected_groups: int | None = Field(default=None, ge=1)
    enable_permute_cache: bool = True

    @field_validator("luts_per_group")
    @classmethod
    def validate_luts_per_group(cls, value: int | list[int]) -> int | list[int]:
        """Validate and normalize allowed group sizes.

        Parameters
        ----------
        value : int | list[int]
            Requested exact group size or list of exact group sizes.

        Returns
        -------
        int | list[int]
            Validated group size. Lists are deduplicated and sorted.

        Raises
        ------
        ValueError
            If no group size is provided, or if any size is smaller than one.
        """
        if isinstance(value, int):
            if value < 1:
                raise ValueError("luts_per_group must be >= 1")
            return value
        sizes = sorted(set(value))
        if not sizes:
            raise ValueError("luts_per_group must not be empty")
        if any(size < 1 for size in sizes):
            raise ValueError("all luts_per_group values must be >= 1")
        return sizes

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        """Validate related boundary bounds.

        Returns
        -------
        Self
            Validated options.

        Raises
        ------
        ValueError
            If a minimum boundary count is larger than its maximum.
        """
        if self.min_boundary_inputs > self.max_boundary_inputs:
            raise ValueError("min_boundary_inputs must be <= max_boundary_inputs")
        if self.min_boundary_outputs > self.max_boundary_outputs:
            raise ValueError("min_boundary_outputs must be <= max_boundary_outputs")
        if self.min_boundary_outputs > max(self.group_sizes()):
            raise ValueError("min_boundary_outputs must be <= max(luts_per_group)")
        return self

    def group_sizes(self) -> tuple[int, ...]:
        """Return allowed exact group sizes.

        Returns
        -------
        tuple[int, ...]
            One or more positive group sizes in deterministic order.

        Examples
        --------
        ``luts_per_group=2`` becomes ``(2,)``. ``luts_per_group=[3, 2, 2]``
        becomes ``(2, 3)`` after validation.
        """
        if isinstance(self.luts_per_group, int):
            return (self.luts_per_group,)
        return tuple(self.luts_per_group)

    def with_luts_per_group(self, luts_per_group: int) -> Self:
        """Return a single-size copy for one group-finder pass.

        Parameters
        ----------
        luts_per_group : int
            Exact group size selected from :meth:`group_sizes`.

        Returns
        -------
        Self
            Options copy with ``luts_per_group`` set to one integer.
        """
        return self.model_copy(update={"luts_per_group": luts_per_group})
