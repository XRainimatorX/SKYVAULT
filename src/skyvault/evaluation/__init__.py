"""
Evaluation = the multi-axis verdict on a finished run (Formal Spec sections 8
and 16).

Important:
Like the exporters, this package reads plain dicts and imports nothing from
the rest of the project. It is computed after the run from what event memory
recorded; it never changes the run.
"""

from .anti_gaming import BEHAVIORS, detect_gaming
from .evaluate import evaluate_run
from .metrics import METRIC_REGISTRY, EvaluationContext, Metric, MetricValue
from .tradeoff import build_tradeoff_report, render_tradeoff_report

__all__ = [
    "BEHAVIORS",
    "METRIC_REGISTRY",
    "EvaluationContext",
    "Metric",
    "MetricValue",
    "build_tradeoff_report",
    "detect_gaming",
    "evaluate_run",
    "render_tradeoff_report",
]
