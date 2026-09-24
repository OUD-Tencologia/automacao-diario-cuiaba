from __future__ import annotations

from typing import Any

from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError


class TxtDownloader:
    """Baixa o original na mesma sessão autenticada, sem gravá-lo em disco local."""

    def __init__(self, browser_context: Any, *, timeout_ms: int) -> None:
        self._browser_context = browser_context
        self._timeout_ms = timeout_ms

    def download(self, reference: ArticleReference) -> bytes:
        try:
            response = self._browser_context.request.get(
                reference.download_url,
                timeout=self._timeout_ms,
            )
            status_code = getattr(response, "status", None)
            if status_code is None or not 200 <= status_code < 300:
                raise FolhapressDownloadError(
                    "O download do TXT Folhapress falhou",
                    diagnostic_code="http_status",
                )
            body = response.body()
        except FolhapressDownloadError:
            raise
        except Exception:
            raise FolhapressDownloadError(
                "Não foi possível baixar o TXT Folhapress",
                diagnostic_code="request_exception",
            ) from None

        if not body:
            raise FolhapressDownloadError(
                "O download Folhapress não retornou um TXT válido",
                diagnostic_code="empty_body",
            )
        if _looks_like_html(body):
            raise FolhapressDownloadError(
                "O download Folhapress não retornou um TXT válido",
                diagnostic_code="html_response",
            )
        return body


def _looks_like_html(body: bytes) -> bool:
    prefix = body[:512].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")
