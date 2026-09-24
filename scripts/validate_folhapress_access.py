"""Valida login, catálogo, extração e TXT Folhapress sem persistir conteúdo."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "automation_api" / "src"))

from automation_api.domain.folhapress import FolhapressDataError
from automation_api.infrastructure.folhapress import (
    ArticleExtractor,
    FolhapressAuth,
    FolhapressBrowserSession,
    FolhapressCatalog,
    SourceHealth,
    TxtDownloader,
)
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError
from automation_api.infrastructure.folhapress.extractor import (
    _labeled_txt_fields,
    decode_original_text,
)
from automation_api.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=1)
    arguments = parser.parse_args()
    if arguments.max_pages < 1:
        raise ValueError("--max-pages deve ser maior que zero")

    settings = get_settings()
    configuration = replace(settings.folhapress(), max_pages_per_cycle=arguments.max_pages)
    with FolhapressBrowserSession(configuration) as session:
        stage = "source_health"
        try:
            SourceHealth(session.page, configuration).check()
            stage = "login"
            FolhapressAuth(session.page, configuration).login()
            stage = "catalog"
            articles = FolhapressCatalog(session.page, configuration).list_articles()
            if not articles:
                print("folhapress_access=failed stage=catalog error=empty_catalog")
                return
            stage = "article_page"
            article = ArticleExtractor(session.page).extract(articles[0])
        except Exception as error:
            print(
                "folhapress_access=failed "
                f"stage={stage} error_type={type(error).__name__}"
            )
            return

        try:
            original = TxtDownloader(
                session.context,
                timeout_ms=configuration.navigation_timeout_ms,
            ).download(articles[0])
        except FolhapressDownloadError as error:
            print(
                "folhapress_access=partial "
                f"articles_found={len(articles)} "
                f"download_result=failed "
                f"download_failure={error.diagnostic_code}"
            )
            return
        try:
            draft = ArticleExtractor(session.page).build_draft(article, original)
        except FolhapressDataError:
            fields = _labeled_txt_fields(decode_original_text(original))
            print(
                "folhapress_access=partial "
                f"articles_found={len(articles)} "
                f"first_id={articles[0].source_id} "
                f"txt_bytes={len(original)} "
                f"has_page_title={bool(article.title)} "
                f"has_page_datetime={bool(article.published_at)} "
                f"has_page_content={bool(article.content)} "
                f"has_txt_title={bool(fields.get('title'))} "
                f"has_txt_datetime={bool(fields.get('published_at'))} "
                f"has_txt_description={bool(fields.get('content'))} "
                "draft_error=required_fields_missing"
            )
            return

    print(
        "folhapress_access=ok "
        f"articles_found={len(articles)} "
        f"first_id={draft.source_id} "
        f"txt_bytes={len(original)} "
        f"has_author={bool(draft.author)} "
        f"has_location={bool(draft.location)}"
    )


if __name__ == "__main__":
    main()
