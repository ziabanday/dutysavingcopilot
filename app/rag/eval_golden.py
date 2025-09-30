# app/rag/eval_golden.py

from pathlib import Path
from typing import Optional

__all__ = ["run_eval"]


def run_eval(k: int = 10, metrics_path: Optional[Path] = None, *args, **kwargs):
    """
    Thin wrapper around app.eval.golden.run_eval that supplies a default
    metrics_path for offline/CI tests and ensures the artifacts directory exists.
    """
    if metrics_path is None:
        metrics_path = Path("artifacts/test-results/metrics.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    # Import lazily to avoid circulars and keep import-time side effects minimal.
    from app.eval.golden import run_eval as _run_eval

    return _run_eval(k=k, metrics_path=metrics_path, *args, **kwargs)
