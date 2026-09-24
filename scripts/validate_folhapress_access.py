"""Valida uma amostra Folhapress sem gravar no PostgreSQL/MinIO ou exibir conteúdo."""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "automation_api" / "src"))

from automation_api.domain.folhapress import FolhapressDataError
from automation_api.infrastructure.folhapress import (
    ArticleExtractor, FolhapressAuth, FolhapressBrowserSession,
    FolhapressCatalog, SourceHealth, TxtDownloader,
)
from automation_api.infrastructure.folhapress.navigation import error_code
from automation_api.settings import get_settings


_DATE_STRUCTURE = """() => {
    const datePattern = /\\b\\d{1,2}\\/\\d{1,2}\\/\\d{4}\\b/;
    const clean = value => (value || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 48);
    const descriptor = element => element ? [
        element.tagName.toLowerCase(),
        Array.from(element.classList).map(clean).filter(Boolean).slice(0, 3).join('.')
    ].join('.') : 'none';
    const hints = [];
    for (const element of document.querySelectorAll('body *')) {
        const ownText = Array.from(element.childNodes)
            .filter(node => node.nodeType === Node.TEXT_NODE)
            .map(node => node.textContent || '').join(' ');
        if (!datePattern.test(ownText) && !element.hasAttribute('datetime')) continue;
        const classes = Array.from(element.classList).map(clean).filter(Boolean).slice(0, 3);
        const attributes = ['datetime', 'itemprop', 'data-date', 'data-testid']
            .filter(name => element.hasAttribute(name));
        const normalized = ownText.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
        const keyword = ['publicad', 'cadastrad', 'atualiz', 'data', 'hora']
            .find(word => normalized.includes(word)) || 'none';
        hints.push([
            element.tagName.toLowerCase(), classes.join('.'), attributes.join('.'),
            keyword, descriptor(element.parentElement), descriptor(element.parentElement?.parentElement)
        ].join(':'));
        if (hints.length >= 8) break;
    }
    return hints;
}"""


def _safe_date_structure(page: object | None) -> str:
    if page is None:
        return "unavailable"
    try:
        hints = page.evaluate(_DATE_STRUCTURE)
    except Exception:
        return "unavailable"
    if not isinstance(hints, list) or not hints:
        return "none"
    return ",".join(str(hint) for hint in hints)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=1)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.max_pages <= 100:
        parser.error("--max-pages deve estar entre 1 e 100")
    try:
        configuration = replace(get_settings().folhapress(), max_pages_per_cycle=arguments.max_pages)
    except Exception:
        print("folhapress_access=failed stage=configuration error_code=invalid_configuration")
        return 2

    stage = "browser"
    started = perf_counter()
    count = 0
    original = b""
    page = None
    date_structure = "not_checked"
    try:
        with FolhapressBrowserSession(configuration) as session:
            page = session.page
            stage = "source_health"
            SourceHealth(session.page, configuration).check()
            stage = "login"
            FolhapressAuth(session.page, configuration).login()
            stage = "catalog"
            articles = FolhapressCatalog(session.page, configuration).list_articles()
            count = len(articles)
            if not articles:
                print("folhapress_access=failed stage=catalog error_code=empty_catalog")
                return 1
            extractor = ArticleExtractor(
                session.page, timeout_ms=configuration.navigation_timeout_ms,
                navigation_attempts=configuration.navigation_attempts,
            )
            stage = "article_page"
            article = extractor.extract(articles[0])
            date_structure = _safe_date_structure(page)
            stage = "download"
            original = TxtDownloader(session.page, timeout_ms=configuration.navigation_timeout_ms).download(articles[0])
            stage = "draft"
            draft = extractor.build_draft(article, original)
    except Exception as error:
        code = error.diagnostic_code if isinstance(error, FolhapressDataError) else error_code(error)
        missing = (
            ",".join(error.missing_fields)
            if isinstance(error, FolhapressDataError) and error.missing_fields
            else "none"
        )
        print(
            f"folhapress_access=failed stage={stage} error_code={code} "
            f"missing_fields={missing} "
            f"date_structure={date_structure} "
            f"articles_found={count} txt_bytes={len(original)} "
            f"duration_ms={round((perf_counter() - started) * 1000)}"
        )
        return 1

    print(
        f"folhapress_access=ok articles_found={count} first_id={draft.source_id} "
        f"txt_bytes={len(original)} has_author={bool(draft.author)} "
        f"has_location={bool(draft.location)} "
        f"duration_ms={round((perf_counter() - started) * 1000)}"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
