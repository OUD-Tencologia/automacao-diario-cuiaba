from __future__ import annotations

import re


class EditorialSummaryError(RuntimeError):
    """O sumarizador local não conseguiu produzir uma sugestão segura."""


class SumyLsaEditorialSummary:
    """Sugestão extrativa local; não envia texto jornalístico a terceiros."""

    def __init__(self, max_characters: int = 150) -> None:
        if max_characters < 1:
            raise ValueError("max_characters deve ser maior que zero")
        self._max_characters = max_characters

    def generate(self, content: str) -> str | None:
        normalized = _normalize(content)
        if not normalized:
            return None

        try:
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.summarizers.lsa import LsaSummarizer

            parser = PlaintextParser.from_string(normalized, Tokenizer("portuguese"))
            sentences = [
                _normalize(str(sentence))
                for sentence in LsaSummarizer()(parser.document, sentences_count=5)
            ]
        except Exception:
            raise EditorialSummaryError("Sumy LSA não pôde processar o texto") from None

        return _join_complete_sentences(sentences, self._max_characters)


def _join_complete_sentences(sentences: list[str], max_characters: int) -> str | None:
    selected: list[str] = []
    current_size = 0
    for sentence in sentences:
        if not sentence:
            continue
        separator_size = 1 if selected else 0
        candidate_size = current_size + separator_size + len(sentence)
        if candidate_size > max_characters:
            continue
        selected.append(sentence)
        current_size = candidate_size
    return " ".join(selected) or None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
