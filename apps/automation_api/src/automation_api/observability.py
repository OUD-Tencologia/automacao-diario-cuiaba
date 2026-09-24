from __future__ import annotations

import logging
import sys


def configure_automation_logging(level: str) -> None:
    """Habilita logs operacionais próprios sem alterar os logs do Uvicorn."""

    logger = logging.getLogger("automation_api")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
