from __future__ import annotations

from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

from automation_api.domain.folhapress import (
    ArticleReference,
    ExtractedArticle,
    FolhapressDataError,
    normalize_location,
)
from automation_api.domain.news import NewsDraft
from automation_api.infrastructure.folhapress.errors import FolhapressConnectionError


_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_TEXT_FIELD_PATTERN = re.compile(
    r"(?im)^\s*(?P<label>CHAP[ÉE]U|T[ÍI]TULO|DATA\s*/\s*HORA|AUTOR|LOCAL|DESCRI[CÇ][AÃ]O|DESTAQUE|TIPO\s+DE\s+CONTE[ÚU]DO|PUBLICAR\s+IMEDIATAMENTE|RESUMO)\s*:\s*"
)
_TAG_TEXT_PATTERN = re.compile(
    r"<(?:h1|p|time)\b[^>]*>(?P<text>.*?)</(?:h1|p|time)>",
    re.IGNORECASE | re.DOTALL,
)


class ArticleExtractor:
    """Extrai metadados da página; o corpo definitivo vem do TXT autenticado."""

    def __init__(self, page: Any) -> None:
        self._page = page

    def extract(self, reference: ArticleReference) -> ExtractedArticle:
        try:
            response = self._page.goto(reference.article_url, wait_until="domcontentloaded")
            status_code = getattr(response, "status", None)
            if status_code is None or not 200 <= status_code < 400:
                raise FolhapressConnectionError("A página da matéria não respondeu com sucesso")
            return extract_article_from_html(self._page.content(), reference)
        except FolhapressConnectionError:
            raise
        except Exception:
            raise FolhapressConnectionError("Não foi possível extrair a matéria Folhapress") from None

    def build_draft(self, extracted: ExtractedArticle, original_text: bytes) -> NewsDraft:
        return build_news_draft(extracted, original_text)


def extract_article_from_html(html: str, reference: ArticleReference) -> ExtractedArticle:
    """Extrator sem dependência de seletor frágil, compatível com meta e JSON-LD."""

    parser = _MetadataParser()
    parser.feed(html)
    json_ld = _find_json_ld(parser.json_ld)
    tag_text = _tag_texts(html)

    title = _first_value(
        parser.meta.get("property:og:title"),
        parser.meta.get("name:twitter:title"),
        _json_value(json_ld, "headline"),
        tag_text[0] if tag_text else None,
    )
    raw_date = _first_value(
        parser.meta.get("property:article:published_time"),
        parser.meta.get("name:date"),
        parser.meta.get("name:datepublished"),
        _json_value(json_ld, "datePublished"),
    )
    content = _first_value(
        _json_value(json_ld, "articleBody"),
        "\n".join(tag_text[1:]) if len(tag_text) > 1 else None,
    )
    author = _first_value(
        parser.meta.get("name:author"),
        parser.meta.get("property:article:author"),
        _json_author(json_ld),
    )
    eyebrow = _first_value(
        parser.meta.get("property:article:section"),
        _json_value(json_ld, "articleSection"),
    )

    return ExtractedArticle(
        reference=reference,
        title=title,
        published_at=parse_folhapress_datetime(raw_date) if raw_date else None,
        eyebrow=eyebrow,
        author=author,
        location=normalize_location(content),
        content=content,
        raw_metadata={
            "page_title_found": bool(title),
            "page_published_at_found": bool(raw_date),
            "page_author_found": bool(author),
        },
    )


def build_news_draft(extracted: ExtractedArticle, original_text: bytes) -> NewsDraft:
    """Combina HTML e TXT sem alterar o arquivo original que seguirá ao MinIO."""

    txt = decode_original_text(original_text)
    fields = _labeled_txt_fields(txt)
    title = _first_value(fields.get("title"), extracted.title)
    published_at = _first_datetime(fields.get("published_at"), extracted.published_at)
    content = _first_value(fields.get("content"), extracted.content, txt)
    location = normalize_location(_first_value(fields.get("location"), extracted.location, content))

    if not title or not published_at or not content:
        raise FolhapressDataError("A matéria não contém título, data/hora ou conteúdo")

    return NewsDraft(
        source="folhapress",
        source_id=extracted.reference.source_id,
        published_at=published_at,
        title=title,
        content=content,
        source_url=extracted.reference.article_url,
        eyebrow=_first_value(fields.get("eyebrow"), extracted.eyebrow),
        author=_first_value(fields.get("author"), extracted.author),
        location=location,
        raw_metadata={
            **dict(extracted.raw_metadata),
            "download_url": extracted.reference.download_url,
            "source_id": extracted.reference.source_id,
        },
    )


def decode_original_text(content: bytes) -> str:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = content.decode("latin-1")
    return "\n".join(line.rstrip() for line in decoded.replace("\x00", "").splitlines()).strip()


def parse_folhapress_datetime(value: str) -> datetime:
    normalized = " ".join(value.strip().split())
    normalized = re.sub(r"(\d{1,2})h(\d{2})", r"\1:\2", normalized, flags=re.IGNORECASE)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(normalized, pattern)
                break
            except ValueError:
                continue
        else:
            raise FolhapressDataError("Data/hora Folhapress inválida")
    return parsed.replace(tzinfo=_SAO_PAULO) if parsed.tzinfo is None else parsed.astimezone(_SAO_PAULO)


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._inside_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if tag.casefold() == "meta":
            key = attributes.get("property") or attributes.get("name")
            value = attributes.get("content")
            if key and value:
                self.meta[f"{'property' if attributes.get('property') else 'name'}:{key.casefold()}"] = value.strip()
        if tag.casefold() == "script" and attributes.get("type", "").casefold() == "application/ld+json":
            self._inside_json_ld = True
            self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_json_ld:
            self._json_ld_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._inside_json_ld:
            self.json_ld.append("".join(self._json_ld_parts))
            self._inside_json_ld = False
            self._json_ld_parts = []


def _labeled_txt_fields(text: str) -> dict[str, str | datetime]:
    matches = list(_TEXT_FIELD_PATTERN.finditer(text))
    fields: dict[str, str | datetime] = {}
    label_map = {
        "chapeu": "eyebrow",
        "titulo": "title",
        "data/hora": "published_at",
        "autor": "author",
        "local": "location",
        "descricao": "content",
    }
    for index, match in enumerate(matches):
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end() : value_end].strip()
        normalized_label = (
            match.group("label")
            .casefold()
            .replace("é", "e")
            .replace("í", "i")
            .replace("ç", "c")
            .replace("ã", "a")
            .replace(" ", "")
        )
        field_name = label_map.get(normalized_label)
        if value and field_name:
            fields[field_name] = (
                parse_folhapress_datetime(value) if field_name == "published_at" else value
            )
    return fields


def _tag_texts(html: str) -> list[str]:
    return [
        _clean_html_text(match.group("text"))
        for match in _TAG_TEXT_PATTERN.finditer(html)
        if _clean_html_text(match.group("text"))
    ]


def _clean_html_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", unescape(value)).split())


def _find_json_ld(candidates: list[str]) -> dict[str, object]:
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        entries = parsed if isinstance(parsed, list) else [parsed]
        for entry in entries:
            if isinstance(entry, dict) and _json_value(entry, "headline"):
                return entry
    return {}


def _json_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _json_author(payload: dict[str, object]) -> str | None:
    author = payload.get("author")
    if isinstance(author, dict):
        return _json_value(author, "name")
    if isinstance(author, list):
        names = [_json_author({"author": item}) for item in author]
        return ", ".join(name for name in names if name) or None
    return author.strip() if isinstance(author, str) and author.strip() else None


def _first_value(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _first_datetime(value: object, fallback: datetime | None) -> datetime | None:
    return value if isinstance(value, datetime) else fallback
