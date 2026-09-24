"""Adaptadores isolados para navegação autenticada na Folhapress."""

from automation_api.infrastructure.folhapress.auth import FolhapressAuth
from automation_api.infrastructure.folhapress.browser import FolhapressBrowserSession
from automation_api.infrastructure.folhapress.catalog import FolhapressCatalog
from automation_api.infrastructure.folhapress.downloader import TxtDownloader
from automation_api.infrastructure.folhapress.extractor import ArticleExtractor
from automation_api.infrastructure.folhapress.health import SourceHealth

__all__ = [
    "ArticleExtractor",
    "FolhapressAuth",
    "FolhapressBrowserSession",
    "FolhapressCatalog",
    "SourceHealth",
    "TxtDownloader",
]
