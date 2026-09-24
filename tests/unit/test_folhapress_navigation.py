from __future__ import annotations

import unittest
from unittest.mock import Mock

from automation_api.infrastructure.folhapress.errors import FolhapressConnectionError
from automation_api.infrastructure.folhapress.navigation import navigate_html


class FolhapressNavigationTest(unittest.TestCase):
    def test_reset_retries_are_bounded_and_do_not_log_raw_errors(self):
        page = Mock()
        page.goto.side_effect = RuntimeError('net::ERR_CONNECTION_RESET secret-cookie example')
        with self.assertLogs('automation_api.infrastructure.folhapress.navigation', level='INFO') as logs:
            with self.assertRaises(FolhapressConnectionError) as raised:
                navigate_html(page, 'https://example.test/', stage='catalog', timeout_ms=1000, attempts=3)
        self.assertEqual(raised.exception.diagnostic_code, 'connection_reset')
        self.assertEqual(page.goto.call_count, 3)
        self.assertEqual([c.args[0] for c in page.wait_for_timeout.call_args_list], [500, 1000])
        self.assertNotIn('secret-cookie', '\n'.join(logs.output))

    def test_forbidden_is_not_retried(self):
        page = Mock()
        page.goto.return_value.status = 403
        with self.assertRaises(FolhapressConnectionError) as raised:
            navigate_html(page, 'https://example.test/', stage='catalog', timeout_ms=1000, attempts=3)
        self.assertEqual(raised.exception.diagnostic_code, 'http_403')
        self.assertEqual(page.goto.call_count, 1)
        page.wait_for_timeout.assert_not_called()

    def test_readiness_timeout_is_not_success_and_is_bounded(self):
        page = Mock()
        page.goto.return_value.status = 200
        ready = Mock(side_effect=TimeoutError())
        with self.assertRaises(FolhapressConnectionError) as raised:
            navigate_html(page, 'https://example.test/', stage='catalog', timeout_ms=1000, attempts=2, ready=ready)
        self.assertEqual(raised.exception.diagnostic_code, 'navigation_timeout')
        self.assertEqual(ready.call_count, 2)
