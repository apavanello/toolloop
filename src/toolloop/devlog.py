"""Developer logging: one-liner setup for terminal or file output.

The agent loop emits records on the ``toolloop`` stdlib logger (INFO: steps,
tool results, run outcomes; WARNING: parse errors; DEBUG: raw envelopes).
This module just makes wiring a handler trivial for dev runs.
"""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "toolloop"


def dev_logger(path: str | None = None, level: int = logging.INFO) -> logging.Logger:
    """Point the ``toolloop`` logger at stderr (default) or a file.

    Replaces any handlers it previously installed, so calling it twice is
    safe. For anything fancier, configure the ``"toolloop"`` logger with the
    standard :mod:`logging` machinery — it composes with any handlers you
    already use.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.FileHandler(path) if path else logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
