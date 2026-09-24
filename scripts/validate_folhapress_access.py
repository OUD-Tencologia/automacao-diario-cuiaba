"""Valida login, catálogo, extração e TXT Folhapress sem persistir conteúdo."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "automation_api" / "src"))

from automation_api.infrastructure.folhapress import (
    ArticleExtractor,
    FolhapressAuth,
    FolhapressBrowserSession,
    FolhapressCatalog,
    SourceHealth,
    TxtDownloader,
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
        SourceHealth(session.page, configuration).check()
        FolhapressAuth(session.page, configuration).login()
        articles = FolhapressCatalog(session.page, configuration).list_articles()
        if not articles:
            raise RuntimeError("O catálogo Folhapress não retornou matérias")

        article = ArticleExtractor(session.page).extract(articles[0])
        original = TxtDownloader(
            session.context,
            timeout_ms=configuration.navigation_timeout_ms,
        ).download(articles[0])
        draft = ArticleExtractor(session.page).build_draft(article, original)

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
