"""Human-readable reporting for benchmark-driven inverse routing."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.models import (
    InverseRouterResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Inverse Router Report
Tile: {{ result.tile_name }}

Configuration
- training benchmarks: {{ result.options.training_benchmarks | length }}
- test benchmarks: {{ result.options.test_benchmarks | length }}
- io_seed_start: {{ result.options.io_seed_start }}
- io_seed_count: {{ result.options.io_seed_count }}
- optimize_switch_matrix: {{ result.options.optimize_switch_matrix }}
- switch_matrix_remove_unused_ratio:
  {{ result.options.switch_matrix_remove_unused_ratio }}
- switch_matrix_remove_used_ratio:
  {{ result.options.switch_matrix_remove_used_ratio }}
- optimize_external_pips: {{ result.options.optimize_external_pips }}
- external_remove_unused_ratio:
  {{ result.options.external_remove_unused_ratio }}
- external_remove_used_ratio:
  {{ result.options.external_remove_used_ratio }}

Training Collection
- routes: {{ result.training_routes | length }}
- passed: {{ result.training_routes | selectattr("passed") | list | length }}
- failed: {{ result.training_routes | rejectattr("passed") | list | length }}
- fasm available:
  {{ result.training_routes | selectattr("fasm_available") | list | length }}

Switch Matrix
- candidates: {{ result.switch_matrix_stats.candidates }}
- unused candidates: {{ result.switch_matrix_stats.unused_candidates }}
- used candidates: {{ result.switch_matrix_stats.used_candidates }}
- removed unused: {{ result.switch_matrix_stats.removed_unused }}
- removed used: {{ result.switch_matrix_stats.removed_used }}
- kept: {{ result.switch_matrix_stats.kept }}

External PIPs
- candidates: {{ result.external_stats.candidates }}
- unused candidates: {{ result.external_stats.unused_candidates }}
- used candidates: {{ result.external_stats.used_candidates }}
- removed unused: {{ result.external_stats.removed_unused }}
- removed used: {{ result.external_stats.removed_used }}
- kept: {{ result.external_stats.kept }}

Training Validation
- routes: {{ result.training_validation_routes | length }}
- passed:
  {{ result.training_validation_routes | selectattr("passed") | list | length }}
- failed:
  {{ result.training_validation_routes | rejectattr("passed") | list | length }}

Test Validation
- routes: {{ result.test_validation_routes | length }}
- passed:
  {{ result.test_validation_routes | selectattr("passed") | list | length }}
- failed:
  {{ result.test_validation_routes | rejectattr("passed") | list | length }}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_inverse_router_report(result: InverseRouterResult) -> str:
    """Render an inverse-router report.

    Parameters
    ----------
    result : InverseRouterResult
        Structured inverse-router result.

    Returns
    -------
    str
        Human-readable report text.
    """
    return _REPORT_TEMPLATE.render(result=result).rstrip()
