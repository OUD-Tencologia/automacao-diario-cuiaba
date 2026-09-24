from __future__ import annotations

import logging
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.observability import configure_automation_logging


class ObservabilityTest(unittest.TestCase):
    def test_configures_only_the_application_logger(self) -> None:
        logger = logging.getLogger("automation_api")
        previous_handlers = list(logger.handlers)
        previous_level = logger.level
        previous_propagate = logger.propagate
        try:
            logger.handlers.clear()
            configure_automation_logging("INFO")

            self.assertEqual(logger.level, logging.INFO)
            self.assertEqual(len(logger.handlers), 1)
            self.assertFalse(logger.propagate)
        finally:
            logger.handlers.clear()
            logger.handlers.extend(previous_handlers)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate


if __name__ == "__main__":
    unittest.main()
