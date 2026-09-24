from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.application.editorial_summary import (
    EditorialSummaryError,
    SumyLsaEditorialSummary,
)


class EditorialSummaryTest(unittest.TestCase):
    def test_returns_complete_portuguese_sentences_within_150_characters(self) -> None:
        first = "A Polícia Federal cumpriu mandados nesta quinta-feira."
        second = "A investigação apura suspeitas de fraude em licitações."
        third = "O ministro negou pedido de busca contra o candidato."
        source = f"{first} {second} {third} A operação cumpre mandados em vários estados."

        result = SumyLsaEditorialSummary().generate(source)

        self.assertIsNotNone(result)
        self.assertLessEqual(len(result or ""), 150)
        self.assertIn(result, source)
        self.assertTrue((result or "").endswith("."))

    def test_empty_input_returns_no_summary(self) -> None:
        self.assertIsNone(SumyLsaEditorialSummary().generate("  \n "))

    def test_summarizer_failure_is_reported_to_the_capture_service(self) -> None:
        with patch(
            "sumy.summarizers.lsa.LsaSummarizer.__call__",
            side_effect=RuntimeError("synthetic summarizer error"),
        ):
            with self.assertRaises(EditorialSummaryError):
                SumyLsaEditorialSummary().generate(
                    "Uma frase sintética começa aqui. Outra frase sintética termina aqui."
                )


if __name__ == "__main__":
    unittest.main()
