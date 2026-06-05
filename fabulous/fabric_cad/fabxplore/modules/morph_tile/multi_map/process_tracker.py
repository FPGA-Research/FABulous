"""Track multi-map grouping and SAT progress.

The multi-map flow samples groups first and then spends most of its time in SAT checks.
This tracker mirrors the normal morph-tile progress style while using group-specific
counters.
"""

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    MultiMapResult,
)


class MultiMapProcessTracker:
    """Report batched multi-map progress.

    Parameters
    ----------
    enabled : bool
        Whether progress lines are emitted.
    chunk_size : int
        Number of checked groups between progress updates.
    """

    def __init__(self, enabled: bool, chunk_size: int) -> None:
        self.enabled = enabled
        self.chunk_size = max(1, chunk_size)
        self._total_luts = 0
        self._sampled_groups = 0
        self._checked_groups = 0
        self._sat_groups = 0
        self._unsat_groups = 0
        self._stored_matches = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_selector_progress_key: tuple[str, str] | None = None
        self._last_selector_progress_time = -1.0

    def start(
        self,
        top_name: str,
        total_luts: int,
        sampled_groups: int,
        options_summary: dict[str, list[str]],
    ) -> None:
        """Start progress tracking for one multi-map plan.

        Parameters
        ----------
        top_name : str
            Processed top module.
        total_luts : int
            Number of LUT cells found in the source graph.
        sampled_groups : int
            Number of structurally valid groups to check.
        options_summary : dict[str, list[str]]
            User-facing multi-map options.
        """
        self._total_luts = total_luts
        self._sampled_groups = sampled_groups
        options = _format_options(options_summary)
        self._print(
            "Start multi-map mapping: "
            f"top={top_name}, "
            f"luts={self._total_luts}, "
            f"sampled_groups={self._sampled_groups}, "
            f"options={options}"
        )

    def sampling_start(
        self,
        top_name: str,
        total_luts: int,
        options_summary: dict[str, list[str]],
    ) -> None:
        """Start progress tracking for group sampling.

        Parameters
        ----------
        top_name : str
            Processed top module.
        total_luts : int
            Number of LUT cells found in the source graph.
        options_summary : dict[str, list[str]]
            User-facing multi-map options.
        """
        self._total_luts = total_luts
        options = _format_options(options_summary)
        self._print(
            "Start multi-map group sampling: "
            f"top={top_name}, "
            f"luts={self._total_luts}, "
            f"options={options}"
        )

    def sampled(
        self,
        phase: str,
        current: int,
        total: int,
        kept_groups: int,
    ) -> None:
        """Record group sampling progress.

        Parameters
        ----------
        phase : str
            Sampling phase name.
        current : int
            Current sampled seed or random attempt.
        total : int
            Total seeds or random attempts for the phase.
        kept_groups : int
            Number of structurally valid groups retained so far.
        """
        if not self._should_emit_sampling(current, total):
            return
        pct = (100.0 * current) / float(total) if total else 100.0
        self._print(
            "Sampling groups: "
            f"phase={phase}, "
            f"{current}/{total} "
            f"({pct:.1f}%), "
            f"kept_groups={kept_groups}"
        )

    def sampling_finish(self, sampled_groups: int) -> None:
        """Emit a final group sampling summary.

        Parameters
        ----------
        sampled_groups : int
            Number of structurally valid groups retained for SAT checks.
        """
        self._print(f"Done group sampling: sampled_groups={sampled_groups}")

    def checked(
        self,
        sat: bool,
        cache_hit: bool,
        stored_matches: int,
    ) -> None:
        """Record one checked group and emit progress when due.

        Parameters
        ----------
        sat : bool
            Whether the group fit the candidate tile.
        cache_hit : bool
            Whether the SAT result came from the permutation cache.
        stored_matches : int
            Number of currently retained successful matches.
        """
        self._checked_groups += 1
        self._stored_matches = stored_matches
        if sat:
            self._sat_groups += 1
        else:
            self._unsat_groups += 1
        if cache_hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

        if self._should_emit():
            self._print_progress()

    def finish(self, result: MultiMapResult) -> None:
        """Emit a final progress summary.

        Parameters
        ----------
        result : MultiMapResult
            Final multi-map result.
        """
        stats = result.stats
        self._print(
            "Done multi-map mapping: "
            f"selected_groups={stats.selected_groups}, "
            f"replaced_luts={stats.replaced_luts}, "
            f"sat_matches={stats.sat_matches_total}, "
            f"stored_matches={stats.matched_groups}, "
            f"cache_hits={stats.cache_hits}, "
            f"unique_solves={stats.cache_misses}"
        )

    def selector_event(self, event: dict[str, object]) -> None:
        """Emit one selector progress event.

        Parameters
        ----------
        event : dict[str, object]
            Event payload from the disjoint selector.
        """
        kind = str(event.get("event", "progress"))
        selector = str(event.get("selector", "unknown"))
        if selector == "local_improvement":
            self._local_improvement_event(kind, event)
            return
        if kind == "start":
            self._print(
                "Start disjoint selector: "
                f"selector={event.get('selector')}, "
                f"matches={event.get('input_matches')}, "
                f"lut_constraints={event.get('lut_constraints')}, "
                f"fallback={event.get('fallback_selector')}, "
                f"time_limit={event.get('max_time_seconds')}s, "
                f"workers={event.get('num_search_workers')}"
            )
            return
        if kind == "progress":
            self._print(
                "Disjoint selector progress: "
                f"selector={event.get('selector')}, "
                f"selected_groups={event.get('selected_groups')}, "
                f"replaced_luts={event.get('replaced_luts')}, "
                f"objective={_format_float(event.get('objective'))}, "
                f"best_bound={_format_float(event.get('best_bound'))}, "
                f"time={_format_float(event.get('wall_time_s'))}s"
            )
            return
        if kind == "bound":
            self._print(
                "Disjoint selector bound: "
                f"selector={event.get('selector')}, "
                f"best_bound={_format_float(event.get('best_bound'))}, "
                f"time={_format_float(event.get('wall_time_s'))}s"
            )
            return
        if kind == "finish":
            self._print(
                "Done disjoint selector: "
                f"selector={event.get('selector')}, "
                f"status={event.get('status')}, "
                f"fallback_used={event.get('fallback_used')}, "
                f"selected_groups={event.get('selected_groups')}, "
                f"replaced_luts={event.get('replaced_luts')}, "
                f"time={_format_float(event.get('wall_time_s'))}s"
            )
            return
        self._print(f"Disjoint selector event: {event}")

    def writer_event(self, event: dict[str, object]) -> None:
        """Emit one writer progress event.

        Parameters
        ----------
        event : dict[str, object]
            Event payload from the multi-map writer.
        """
        kind = str(event.get("event", "progress"))
        if kind == "start":
            self._print(
                "Start applying multi-map replacements: "
                f"replacements={event.get('replacements')}, "
                f"removed_luts={event.get('removed_luts')}"
            )
            return
        if kind == "progress":
            current = int(event.get("current", 0))
            total = int(event.get("total", 0))
            if not self._should_emit_sampling(current, total):
                return
            pct = (100.0 * current) / float(total) if total else 100.0
            self._print(
                "Applying multi-map replacements: "
                f"{current}/{total} "
                f"({pct:.1f}%), "
                f"removed_luts={event.get('removed_luts')}"
            )
            return
        if kind == "fixup_start":
            self._print("Fixing multi-map module ports")
            return
        if kind == "finish":
            self._print(
                "Done applying multi-map replacements: "
                f"replacements={event.get('replacements')}, "
                f"removed_luts={event.get('removed_luts')}"
            )
            return
        self._print(f"Multi-map writer event: {event}")

    def _print_progress(self) -> None:
        """Print one group-progress update."""
        if self._sampled_groups <= 0:
            self._print("Groups: 0/0")
            return
        pct = (100.0 * self._checked_groups) / float(self._sampled_groups)
        self._print(
            "Groups: "
            f"{self._checked_groups}/{self._sampled_groups} "
            f"({pct:.1f}%), "
            f"sat={self._sat_groups}, "
            f"unsat={self._unsat_groups}, "
            f"stored_matches={self._stored_matches}, "
            f"cache_hits={self._cache_hits}, "
            f"unique_solves={self._cache_misses}"
        )

    def _local_improvement_event(
        self,
        kind: str,
        event: dict[str, object],
    ) -> None:
        """Emit one local-improvement selector event.

        Parameters
        ----------
        kind : str
            Selector event kind.
        event : dict[str, object]
            Event payload.
        """
        if kind == "start":
            self._last_selector_progress_key = None
            self._last_selector_progress_time = -1.0
            self._print(
                "Start disjoint selector: "
                f"selector=local_improvement, "
                f"matches={event.get('input_matches')}, "
                f"initial_groups={event.get('selected_groups')}, "
                f"initial_replaced_luts={event.get('replaced_luts')}"
            )
            return
        if kind == "progress":
            phase = str(event.get("phase", "progress"))
            if phase == "removal_scan":
                self._local_improvement_scan_event(event)
                return
            self._print(
                "Disjoint selector progress: "
                f"selector=local_improvement, "
                f"accepted_improvements={event.get('accepted_improvements')}, "
                f"selected_groups={event.get('selected_groups')}, "
                f"replaced_luts={event.get('replaced_luts')}, "
                f"time={_format_float(event.get('wall_time_s'))}s"
            )
            return
        if kind == "finish":
            self._print(
                "Done disjoint selector: "
                f"selector=local_improvement, "
                f"status={event.get('status')}, "
                f"accepted_improvements={event.get('accepted_improvements')}, "
                f"selected_groups={event.get('selected_groups')}, "
                f"replaced_luts={event.get('replaced_luts')}, "
                f"time={_format_float(event.get('wall_time_s'))}s"
            )
            return
        self._print(f"Local-improvement selector event: {event}")

    def _local_improvement_scan_event(self, event: dict[str, object]) -> None:
        """Emit throttled local-improvement scan progress.

        Parameters
        ----------
        event : dict[str, object]
            Removal-scan event payload.
        """
        current = int(event.get("current", 0))
        total = int(event.get("total", 0))
        elapsed = float(event.get("wall_time_s", 0.0))
        key = (str(event.get("scan", "")), "removal_scan")
        should_emit = self._should_emit_sampling(current, total)
        if (
            key == self._last_selector_progress_key
            and self._last_selector_progress_time >= 0.0
            and elapsed - self._last_selector_progress_time < 2.0
            and current != total
        ):
            should_emit = False
        if not should_emit:
            return
        self._last_selector_progress_key = key
        self._last_selector_progress_time = elapsed
        pct = (100.0 * current) / float(total) if total else 100.0
        self._print(
            "Disjoint selector progress: "
            f"selector=local_improvement, "
            f"phase=removal_scan, "
            f"scan={event.get('scan')}, "
            f"removals={current}/{total} "
            f"({pct:.1f}%), "
            f"scan_best_groups={event.get('scan_best_groups')}, "
            f"scan_best_replaced_luts={event.get('scan_best_replaced_luts')}, "
            f"time={_format_float(event.get('wall_time_s'))}s"
        )

    def _should_emit(self) -> bool:
        """Return whether the current group count should be logged.

        Returns
        -------
        bool
            ``True`` when a progress update should be printed.
        """
        return (
            self._checked_groups % self.chunk_size == 0
            or self._checked_groups == self._sampled_groups
        )

    def _should_emit_sampling(self, current: int, total: int) -> bool:
        """Return whether sampling progress should be logged.

        Parameters
        ----------
        current : int
            Current sampling item.
        total : int
            Total sampling items.

        Returns
        -------
        bool
            ``True`` when a sampling progress line should be printed.
        """
        if current <= 0:
            return False
        step = max(self.chunk_size, total // 20, 1)
        return current == 1 or current % step == 0 or current == total

    def _print(self, message: str) -> None:
        """Emit one progress line when tracking is enabled.

        Parameters
        ----------
        message : str
            Message body without the standard prefix.
        """
        if self.enabled:
            logger.info(f"[MultiMapMapper] {message}")


def _format_options(options_summary: dict[str, list[str]]) -> str:
    """Format multi-map options for compact progress output.

    Parameters
    ----------
    options_summary : dict[str, list[str]]
        Option values selected for this run.

    Returns
    -------
    str
        Compact option string.
    """
    if not options_summary:
        return "none"
    parts = []
    for key, values in sorted(options_summary.items()):
        parts.append(f"{key}=[{', '.join(values) if values else 'none'}]")
    return "; ".join(parts)


def _format_float(value: object) -> str:
    """Format an optional numeric value for progress output.

    Parameters
    ----------
    value : object
        Value to render.

    Returns
    -------
    str
        Compact numeric string or ``"n/a"``.
    """
    if not isinstance(value, int | float):
        return "n/a"
    return f"{float(value):.3f}"
