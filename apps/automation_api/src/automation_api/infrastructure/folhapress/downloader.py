from __future__ import annotations

from pathlib import Path
from typing import Any

from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError
from automation_api.infrastructure.folhapress.navigation import error_code, wait_for_download_link


class TxtDownloader:
    """Baixa o TXT pela sessão do navegador e remove o arquivo temporário."""

    def __init__(self, page: Any, *, timeout_ms: int) -> None:
        self._page = page
        self._timeout_ms = timeout_ms

    def download(self, reference: ArticleReference) -> bytes:
        download: Any | None = None
        stage = "link"
        try:
            link = wait_for_download_link(self._page, reference.download_url, self._timeout_ms)
            stage = "download"
            with self._page.expect_download(timeout=self._timeout_ms) as download_info:
                link.click(timeout=self._timeout_ms)
            download = download_info.value
            if download.failure():
                raise FolhapressDownloadError(
                    "O navegador não concluiu o download", diagnostic_code="download_failed",
                )
            temporary_path = download.path()
            if temporary_path is None:
                raise FolhapressDownloadError(
                    "O download Folhapress não disponibilizou arquivo temporário",
                    diagnostic_code="temporary_file_missing",
                )
            body = Path(temporary_path).read_bytes()
        except FolhapressDownloadError:
            raise
        except Exception as error:
            code = error_code(error)
            if code == "navigation_timeout":
                try:
                    if self._page.locator('input[type="password"]:visible').count():
                        code = "session_expired"
                except Exception:
                    pass
            diagnostic_code = code if code in {"session_expired", "connection_reset"} else (
                "download_link_missing" if stage == "link" else (
                "download_timeout" if code == "navigation_timeout" else
                "browser_download_exception")
            )
            raise FolhapressDownloadError(
                "Não foi possível baixar o TXT Folhapress",
                diagnostic_code=diagnostic_code,
            ) from None
        finally:
            if download is not None:
                try:
                    download.delete()
                except Exception:
                    pass

        validate_txt(body)
        return body


def validate_txt(body: bytes) -> None:
    if not body.removeprefix(b"\xef\xbb\xbf").strip():
        raise FolhapressDownloadError("TXT vazio", diagnostic_code="empty_body")
    if _looks_like_html(body):
        raise FolhapressDownloadError("HTML recebido em lugar de TXT", diagnostic_code="html_response")


def _looks_like_html(body: bytes) -> bool:
    prefix = body[:512].removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    return prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body", b"<form"))
