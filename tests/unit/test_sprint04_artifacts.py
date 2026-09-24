from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows/n8n/folhapress-hourly-mvp.json"
COMPOSE = ROOT / "infra/compose/automation-api.compose.yml"


class Sprint04ArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        cls.compose = COMPOSE.read_text(encoding="utf-8")
        cls.nodes = {node["name"]: node for node in cls.workflow["nodes"]}

    def test_workflow_is_importable_inactive_and_hourly(self) -> None:
        self.assertFalse(self.workflow["active"])
        self.assertEqual(self.workflow["settings"]["timezone"], "America/Sao_Paulo")
        schedule = self.nodes["A cada hora"]
        self.assertEqual(
            schedule["parameters"]["rule"]["interval"][0]["expression"],
            "0 * * * *",
        )

    def test_workflow_only_calls_the_api_and_has_bounded_retry(self) -> None:
        request = self.nodes["Capturar Folhapress pela API"]
        self.assertEqual(request["parameters"]["method"], "POST")
        self.assertEqual(
            request["parameters"]["url"],
            "http://automation-api:8000/automation/folhapress/capture",
        )
        self.assertTrue(request["retryOnFail"])
        self.assertEqual(request["maxTries"], 2)
        self.assertEqual(request["waitBetweenTries"], 60000)
        self.assertEqual(request["parameters"]["options"]["timeout"], 900000)
        self.assertFalse(any(node.get("credentials") for node in self.workflow["nodes"]))
        self.assertFalse(
            any(
                "postgres" in node["name"].lower() or "minio" in node["name"].lower()
                for node in self.workflow["nodes"]
            )
        )

    def test_compose_adds_only_private_api_to_existing_network(self) -> None:
        self.assertIn("automacao-editorial_interna", self.compose)
        self.assertIn("external: true", self.compose)
        self.assertIn("POSTGRES_HOST: automacao-editorial-postgres-1", self.compose)
        self.assertIn("http://automacao-editorial-minio-1:9000", self.compose)
        self.assertNotRegex(self.compose, r"(?m)^    ports:")
        self.assertNotRegex(self.compose, r"(?m)^  postgres:")
        self.assertNotRegex(self.compose, r"(?m)^  minio:")
        self.assertNotRegex(self.compose, r"(?m)^  n8n:")
        self.assertIn('FOLHAPRESS_MAX_PAGES_PER_CYCLE: "1"', self.compose)


if __name__ == "__main__":
    unittest.main()
