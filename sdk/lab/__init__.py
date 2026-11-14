"""Lattice lab SDK — lightweight experiment tracking for the local research hub.

Usage:
    from lab import Run

    with Run(experiment="E0007", params=cfg) as run:
        for step, (loss, acc) in enumerate(train()):
            run.log(step, loss=loss, acc=acc)
        run.save_artifact("curve.png", kind="figure")
        run.summary(final_acc=acc)

The SDK has no third-party dependencies. If the local API is unavailable it
writes a JSONL offline journal and replays it on the next `Run` start.
"""

from .run import Run, sync_pending

__all__ = ["Run", "sync_pending"]
__version__ = "0.1.0"
