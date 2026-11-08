"""
Evaluation = the multi-axis verdict on a finished run (Formal Spec sections 8
and 16).

Important:
Like the exporters, this package reads plain dicts and imports nothing from
the rest of the project. It is computed after the run from what event memory
recorded; it never changes the run.
"""

from .metrics import METRIC_REGISTRY, EvaluationContext, Metric, MetricValue

__all__ = ["METRIC_REGISTRY", "EvaluationContext", "Metric", "MetricValue"]
