"""Navegação GET com espera de prontidão e diagnóstico sem conteúdo da fonte."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlsplit

from automation_api.infrastructure.folhapress.errors import (
    FolhapressAuthenticationError,
    FolhapressCatalogError,
    FolhapressConnectionError,
    FolhapressSourceError,
)


def error_code(error: Exception) -> str:
    if isinstance(error, FolhapressSourceError):
        return error.diagnostic_code
    if type(error).__name__ == "TimeoutError":
        return "navigation_timeout"
    if "net::ERR_CONNECTION_RESET" in str(error):
        return "connection_reset"
    return "browser_navigation_error"


def navigate_html(
    page: Any,
    url: str,
    *,
    stage: str,
    timeout_ms: int,
    attempts: int = 1,
    ready: Callable[[], object] | None = None,
) -> Any:
    """Retenta somente GETs transitórios; POST/login e download não passam aqui."""
    for attempt in range(max(1, attempts)):
        started = perf_counter()
        status = None
        code = "ok"
        try:
            response = page.goto(url, wait_until="commit", timeout=timeout_ms)
            status = getattr(response, "status", None)
            if status is None or not 200 <= status < 300:
                raise FolhapressConnectionError(
                    "Resposta inesperada da Folhapress",
                    diagnostic_code=f"http_{status}" if status is not None else "missing_response",
                )
            if ready is not None:
                ready()
            return response
        except Exception as error:
            code = error_code(error)
            retryable = code in {
                "navigation_timeout", "connection_reset", "http_502", "http_503", "http_504",
            }
            if not retryable or attempt + 1 >= max(1, attempts):
                if isinstance(error, FolhapressSourceError):
                    raise
                raise FolhapressConnectionError(
                    "Não foi possível concluir a navegação Folhapress", diagnostic_code=code,
                ) from None
        finally:
            logging.getLogger(__name__).info(
                "folhapress stage=%s attempt=%s status=%s duration_ms=%s code=%s",
                stage, attempt + 1, status, round((perf_counter() - started) * 1000), code,
            )
        page.wait_for_timeout(500 * (attempt + 1))


_CATALOG_READY = """({selector, labels}) => {
    const password = Array.from(document.querySelectorAll('input[type="password"]'))
        .some(el => el.getClientRects().length > 0);
    if (password) return 'login';
    const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').toLowerCase();
    const valid = labels.every(label => text.includes(label.toLowerCase()));
    if (valid && document.querySelector(selector)) return 'ready';
    if (document.readyState === 'complete') return valid ? 'empty' : 'invalid';
    return false;
}"""


def wait_for_catalog(page: Any, configuration: Any) -> None:
    handle = page.wait_for_function(
        _CATALOG_READY,
        arg={"selector": configuration.article_link_selector,
             "labels": list(configuration.required_catalog_labels)},
        timeout=configuration.navigation_timeout_ms,
    )
    try:
        state = handle.json_value()
    finally:
        handle.dispose()
    actual, expected = urlsplit(page.url), urlsplit(configuration.catalog_url)
    if (state == "login" or (actual.scheme, actual.netloc, actual.path.rstrip('/')) !=
            (expected.scheme, expected.netloc, expected.path.rstrip('/'))):
        raise FolhapressAuthenticationError(
            "A sessão Folhapress não foi confirmada", diagnostic_code="session_expired",
        )
    if state not in {"ready", "empty"}:
        raise FolhapressCatalogError(
            "O catálogo não contém os marcadores esperados", diagnostic_code="catalog_markup_invalid",
        )


# Usa URL resolvida pelo navegador: href relativo/absoluto, mesma origem e ID.
DOWNLOAD_LINK_INDEX = """(links, expected) => {
    const target = new URL(expected);
    return links.findIndex(link => {
        const url = new URL(link.href);
        return url.origin === target.origin && !url.username && !url.password &&
            url.pathname.replace(/\\/$/, '') === target.pathname.replace(/\\/$/, '') &&
            link.getClientRects().length > 0;
    });
}"""
DOWNLOAD_LINK_READY = """(expected) => {
    if (Array.from(document.querySelectorAll('input[type="password"]'))
        .some(el => el.getClientRects().length > 0)) return 'login';
    return (""" + DOWNLOAD_LINK_INDEX + """ )(
        Array.from(document.querySelectorAll('a[href]')), expected) >= 0;
}"""


def wait_for_download_link(page: Any, url: str, timeout_ms: int) -> Any:
    handle = page.wait_for_function(DOWNLOAD_LINK_READY, arg=url, timeout=timeout_ms)
    try:
        state = handle.json_value()
    finally:
        handle.dispose()
    if state == "login":
        raise FolhapressAuthenticationError(
            "A sessão expirou antes do download", diagnostic_code="session_expired",
        )
    links = page.locator("a[href]")
    index = links.evaluate_all(DOWNLOAD_LINK_INDEX, url)
    if index < 0:
        raise FolhapressConnectionError(
            "O link de download desapareceu", diagnostic_code="download_link_missing",
        )
    return links.nth(index)
