from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from fastapi.testclient import TestClient

from automation_api.application.capture_folhapress import (
    CaptureCycleError,
    CaptureFailure,
    CaptureResult,
    CaptureSourceError,
)
from automation_api.infrastructure.folhapress.errors import FolhapressAuthenticationError
from automation_api.infrastructure.postgres import CaptureAlreadyRunningError
from automation_api.main import create_app


class AutomationCaptureApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.settings = object()
        self.settings_patcher = patch(
            "automation_api.presentation.automation.get_settings", return_value=self.settings
        )
        self.settings_patcher.start()

    def tearDown(self) -> None:
        self.settings_patcher.stop()

    def test_success_returns_safe_operational_counts(self) -> None:
        result = CaptureResult(
            capture_id="capture-success",
            scanned=3,
            captured=1,
            skipped_existing=2,
            failed=0,
            duration_ms=321,
        )
        with patch(
            "automation_api.presentation.automation.run_folhapress_capture", return_value=result
        ) as runner:
            response = self.client.post("/automation/folhapress/capture")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capture_id"], "capture-success")
        self.assertEqual(response.json()["failed"], 0)
        self.assertEqual(response.json()["duration_ms"], 321)
        self.assertEqual(runner.call_args.kwargs["capture_id"].__class__, str)

    def test_partial_failure_returns_sanitized_operational_diagnostics(self) -> None:
        result = CaptureResult(
            capture_id="capture-failure",
            scanned=3,
            captured=1,
            skipped_existing=1,
            failed=1,
            duration_ms=654,
        )
        error = CaptureCycleError(
            result,
            [CaptureFailure("101", "download", "download_timeout", True)],
        )
        with patch(
            "automation_api.presentation.automation.run_folhapress_capture", side_effect=error
        ):
            response = self.client.post("/automation/folhapress/capture")

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["result"]["captured"], 1)
        self.assertEqual(payload["failures"], [{
            "source_id": "101",
            "stage": "download",
            "diagnostic_code": "download_timeout",
            "retryable": True,
        }])
        self.assertNotIn("synthetic", response.text)

    def test_openapi_documents_the_partial_failure_contract(self) -> None:
        document = self.client.get("/openapi.json").json()
        responses = document["paths"]["/automation/folhapress/capture"]["post"]["responses"]

        self.assertIn("502", responses)
        self.assertIn("CaptureErrorResponse", str(responses["502"]))

    def test_source_failure_keeps_its_safe_stage_and_code(self) -> None:
        source_error = CaptureSourceError(
            capture_id="capture-source",
            stage="login",
            error=FolhapressAuthenticationError(
                "username=user@example.com password=not-allowed",
                diagnostic_code="login_submit_navigation_timeout",
            ),
            duration_ms=123,
        )
        with patch(
            "automation_api.presentation.automation.run_folhapress_capture", side_effect=source_error
        ):
            response = self.client.post("/automation/folhapress/capture")

        self.assertEqual(response.status_code, 502)
        failure = response.json()["failures"][0]
        self.assertEqual(failure["stage"], "login")
        self.assertEqual(failure["diagnostic_code"], "login_submit_navigation_timeout")
        self.assertNotIn("user@example.com", response.text)

    def test_running_capture_returns_retryable_conflict(self) -> None:
        with patch(
            "automation_api.presentation.automation.run_folhapress_capture",
            side_effect=CaptureAlreadyRunningError("already running"),
        ):
            response = self.client.post("/automation/folhapress/capture")

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["retryable"])
        self.assertNotIn("already running", response.text)


if __name__ == "__main__":
    unittest.main()
