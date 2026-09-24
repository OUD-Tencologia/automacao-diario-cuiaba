from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
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
from automation_api.infrastructure.folhapress.navigation import navigate_html, wait_for_download_link


_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_TEXT_FIELD_PATTERN = re.compile(
    r"(?im)^\s*(?P<label>CHAP[ÉE]U|T[ÍI]TULO|DATA\s*/\s*HORA|AUTOR|LOCAL|DESCRI[CÇ][AÃ]O|DESTAQUE|TIPO\s+DE\s+CONTE[ÚU]DO|PUBLICAR\s+IMEDIATAMENTE|RESUMO)\s*:\s*"
)
_TAG_TEXT_PATTERN = re.compile(
    r"<(?:h1|p|time)\b[^>]*>(?P<text>.*?)</(?:h1|p|time)>",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_PORTAL_TITLES = frozenset({"folhapress", "folha press"})
_TITLE_HINT_PATTERN = re.compile(r"(?:title|titulo|headline|manchete)", re.IGNORECASE)
_AUTHOR_HINT_PATTERN = re.compile(r"(?:author|autor|byline)", re.IGNORECASE)
_EYEBROW_HINT_PATTERN = re.compile(r"(?:eyebrow|chapeu|chap[eé]u|section|category|editoria)", re.IGNORECASE)
_DATE_HINT_PATTERN = re.compile(r"(?:date|data|published|publish|time)", re.IGNORECASE)
_CONTENT_HINT_PATTERN = re.compile(r"(?:article-body|article-content|text-content|text-body|conteudo|content)", re.IGNORECASE)
_DISPLAYED_DATETIME_PATTERN = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*(?:[-–—,]|\b(?:a|à|as|às)\b)?\s*"
    r"(?P<hour>\d{1,2})(?:h|:)(?P<minute>\d{2})(?::(?P<second>\d{2}))?",
    flags=re.IGNORECASE,
)


class ArticleExtractor:
    """Extrai metadados da página; o corpo definitivo vem do TXT autenticado."""

    def __init__(self, page: Any, *, timeout_ms: int = 30_000, navigation_attempts: int = 3) -> None:
        self._page = page
        self._timeout_ms = timeout_ms
        self._navigation_attempts = navigation_attempts

    def extract(self, reference: ArticleReference) -> ExtractedArticle:
        navigate_html(
            self._page, reference.article_url, stage="article_page",
            timeout_ms=self._timeout_ms, attempts=self._navigation_attempts,
            ready=lambda: wait_for_download_link(self._page, reference.download_url, self._timeout_ms),
        )
        try:
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
    semantic = _SemanticContentParser()
    semantic.feed(html)

    page_title_candidates = (
        semantic.value_for(_TITLE_HINT_PATTERN, tags=("h1", "h2", "h3")),
        _json_value(json_ld, "headline"),
        parser.meta.get("property:og:title"),
        parser.meta.get("name:twitter:title"),
        semantic.heading_value(),
        semantic.any_heading_value(),
    )
    page_title = _first_specific_value(*page_title_candidates) or _first_value(*page_title_candidates)
    title = _first_specific_value(reference.catalog_title, page_title) or _first_value(
        reference.catalog_title, page_title
    )
    raw_date = _first_value(
        parser.meta.get("property:article:published_time"),
        parser.meta.get("name:date"),
        parser.meta.get("name:datepublished"),
        parser.meta.get("itemprop:datepublished"),
        _json_value(json_ld, "datePublished"),
        *parser.time_values,
        *_semantic_published_values(parser.text_info_values),
    )
    content = _first_value(
        _json_value(json_ld, "articleBody"),
        semantic.value_for(_CONTENT_HINT_PATTERN),
    )
    author = _first_value(
        semantic.value_for(_AUTHOR_HINT_PATTERN),
        parser.meta.get("name:author"),
        parser.meta.get("property:article:author"),
        _json_author(json_ld),
    )
    page_eyebrow = _first_value(
        semantic.value_for(_EYEBROW_HINT_PATTERN),
        parser.meta.get("property:article:section"),
        _json_value(json_ld, "articleSection"),
    )
    eyebrow = _first_value(reference.catalog_eyebrow, page_eyebrow)

    return ExtractedArticle(
        reference=reference,
        title=title,
        published_at=parse_folhapress_datetime(raw_date) if raw_date else None,
        eyebrow=eyebrow,
        author=author,
        location=normalize_location(content),
        content=content,
        raw_metadata={
            "extraction_contract_version": 3,
            "page_title_found": bool(page_title),
            "catalog_title_found": bool(reference.catalog_title),
            "page_published_at_found": bool(raw_date),
            "page_author_found": bool(author),
            "page_eyebrow_found": bool(page_eyebrow),
            "catalog_eyebrow_found": bool(reference.catalog_eyebrow),
            "metadata_sources": {
                "title": "catalog" if reference.catalog_title else "article_page" if title else None,
                "published_at": "article_page" if raw_date else None,
                "author": "article_page" if author else None,
                "eyebrow": "catalog" if reference.catalog_eyebrow else "article_page" if eyebrow else None,
            },
        },
    )


def build_news_draft(extracted: ExtractedArticle, original_text: bytes) -> NewsDraft:
    """Combina HTML e TXT sem alterar o arquivo original que seguirá ao MinIO."""

    txt = decode_original_text(original_text)
    fields = _labeled_txt_fields(txt)
    title = _first_specific_value(
        fields.get("title"), extracted.reference.catalog_title, extracted.title
    ) or _first_value(
        fields.get("title") if isinstance(fields.get("title"), str) else None,
        extracted.reference.catalog_title,
        extracted.title,
    )
    published_at = _first_datetime(fields.get("published_at"), extracted.published_at)
    # O TXT e o original editorial. HTML serve para metadados; somente um TXT
    # explicitamente estruturado pode substituir o corpo pelo campo DESCRICAO.
    content = _first_value(fields.get("content"), txt)
    explicit_location = _first_value(fields.get("location"))
    location = (
        normalize_location(explicit_location)
        if explicit_location
        else _location_from_txt_opening(content) or extracted.location
    )

    if _is_generic_portal_title(title):
        raise FolhapressDataError(
            "A pÃ¡gina retornou um tÃ­tulo genÃ©rico do portal",
            diagnostic_code="generic_article_title",
            missing_fields=("title",),
        )

    missing_fields = tuple(
        field_name
        for field_name, value in (
            ("title", title),
            ("published_at", published_at),
            ("content", content),
        )
        if not value
    )
    if missing_fields:
        raise FolhapressDataError(
            "A matéria não contém todos os campos obrigatórios",
            diagnostic_code="required_fields_missing",
            missing_fields=missing_fields,
        )

    return NewsDraft(
        source="folhapress",
        source_id=extracted.reference.source_id,
        published_at=published_at,
        title=title,
        content=content,
        source_url=extracted.reference.article_url,
        eyebrow=_first_value(
            fields.get("eyebrow"), extracted.reference.catalog_eyebrow, extracted.eyebrow
        ),
        author=_first_value(fields.get("author"), extracted.author),
        location=location,
        raw_metadata={
            **dict(extracted.raw_metadata),
            "download_url": extracted.reference.download_url,
            "source_id": extracted.reference.source_id,
            "metadata_sources": {
                **dict(extracted.raw_metadata.get("metadata_sources", {})),
                "title": (
                    "txt" if fields.get("title") and title == fields.get("title")
                    else "catalog" if extracted.reference.catalog_title and title == extracted.reference.catalog_title
                    else "article_page"
                ),
                "published_at": "txt" if fields.get("published_at") else "article_page",
                "content": "txt",
                "location": "txt" if fields.get("location") else "txt_opening",
            },
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
    displayed = _DISPLAYED_DATETIME_PATTERN.search(normalized)
    if displayed:
        normalized = (
            f"{displayed.group('date')} {displayed.group('hour')}:{displayed.group('minute')}"
            + (f":{displayed.group('second')}" if displayed.group('second') else "")
        )
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
            raise FolhapressDataError(
                "Data/hora Folhapress inválida",
                diagnostic_code="invalid_published_at",
            )
    return parsed.replace(tzinfo=_SAO_PAULO) if parsed.tzinfo is None else parsed.astimezone(_SAO_PAULO)


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.time_values: list[str] = []
        self.text_info_values: list[str] = []
        self._inside_json_ld = False
        self._json_ld_parts: list[str] = []
        self._inside_time = False
        self._time_parts: list[str] = []
        self._time_datetime: str | None = None
        self._text_info_div_stack: list[bool] = []
        self._inside_text_info_li = False
        self._text_info_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if tag.casefold() == "meta":
            key_kind = next(
                (kind for kind in ("property", "name", "itemprop") if attributes.get(kind)),
                None,
            )
            key = attributes.get(key_kind) if key_kind else None
            value = attributes.get("content")
            if key and value:
                self.meta[f"{key_kind}:{key.casefold()}"] = value.strip()
        if tag.casefold() == "script" and attributes.get("type", "").casefold() == "application/ld+json":
            self._inside_json_ld = True
            self._json_ld_parts = []
        if tag.casefold() == "time":
            self._inside_time = True
            self._time_parts = []
            self._time_datetime = attributes.get("datetime", "").strip() or None
        if tag.casefold() == "div":
            classes = set(attributes.get("class", "").split())
            parent_active = self._text_info_div_stack[-1] if self._text_info_div_stack else False
            self._text_info_div_stack.append(parent_active or "text-info" in classes)
        if tag.casefold() == "li" and self._text_info_div_stack and self._text_info_div_stack[-1]:
            self._inside_text_info_li = True
            self._text_info_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_json_ld:
            self._json_ld_parts.append(data)
        if self._inside_time:
            self._time_parts.append(data)
        if self._inside_text_info_li:
            self._text_info_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._inside_json_ld:
            self.json_ld.append("".join(self._json_ld_parts))
            self._inside_json_ld = False
            self._json_ld_parts = []
        if tag.casefold() == "time" and self._inside_time:
            value = self._time_datetime or " ".join("".join(self._time_parts).split())
            if value:
                self.time_values.append(value)
            self._inside_time = False
            self._time_parts = []
            self._time_datetime = None
        if tag.casefold() == "li" and self._inside_text_info_li:
            value = " ".join("".join(self._text_info_parts).split())
            if value:
                self.text_info_values.append(value)
            self._inside_text_info_li = False
            self._text_info_parts = []
        if tag.casefold() == "div" and self._text_info_div_stack:
            self._text_info_div_stack.pop()


@dataclass
class _SemanticNode:
    tag: str
    attributes: dict[str, str]
    text_parts: list[str]

    @property
    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())

    @property
    def descriptor(self) -> str:
        return " ".join(
            value for key, value in self.attributes.items()
            if key in {"class", "id", "itemprop", "data-testid", "data-test"}
        )


class _SemanticContentParser(HTMLParser):
    """Coleta apenas candidatos editoriais; nunca usa a navegaÃ§Ã£o do portal."""

    _TEXT_TAGS = frozenset({"h1", "h2", "h3", "p", "span", "time", "div", "section"})

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, _SemanticNode | None]] = []
        self.nodes: list[_SemanticNode] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        attributes = {name.casefold(): value or "" for name, value in attrs}
        descriptor = " ".join(
            value for key, value in attributes.items()
            if key in {"class", "id", "itemprop", "data-testid", "data-test"}
        )
        is_candidate = (
            normalized_tag in {"h1", "h2", "h3", "time"}
            or bool(
                normalized_tag in self._TEXT_TAGS
                and any(pattern.search(descriptor) for pattern in (
                    _TITLE_HINT_PATTERN,
                    _AUTHOR_HINT_PATTERN,
                    _EYEBROW_HINT_PATTERN,
                    _DATE_HINT_PATTERN,
                    _CONTENT_HINT_PATTERN,
                ))
            )
        )
        node = _SemanticNode(normalized_tag, attributes, []) if is_candidate else None
        self._stack.append((normalized_tag, node))
        if node is not None:
            self.nodes.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for _, node in self._stack:
            if node is not None:
                node.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        # HTML da origem pode conter marcaÃ§Ã£o imperfeita; descarta atÃ© o fim
        # correspondente para evitar que texto posterior contamine um candidato.
        normalized_tag = tag.casefold()
        for index in range(len(self._stack) - 1, -1, -1):
            stack_tag, _ = self._stack[index]
            if stack_tag == normalized_tag:
                del self._stack[index:]
                return

    def value_for(self, hint: re.Pattern[str], *, tags: tuple[str, ...] = ()) -> str | None:
        candidates: list[tuple[int, str]] = []
        for node in self.nodes:
            text = node.text
            if not text:
                continue
            descriptor = node.descriptor
            if hint.search(descriptor):
                candidates.append((100, text))
            elif tags and node.tag in tags:
                candidates.append((20, text))
        for _, value in sorted(candidates, key=lambda item: (-item[0], -len(item[1]))):
            if not _is_generic_portal_title(value):
                return value
        return None

    def heading_value(self) -> str | None:
        return self.value_for(re.compile(r"a^"), tags=("h1", "h2", "h3"))

    def any_heading_value(self) -> str | None:
        for node in self.nodes:
            if node.tag in {"h1", "h2", "h3"} and node.text:
                return node.text
        return None


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


def _semantic_published_values(values: list[str]) -> tuple[str, ...]:
    """Mantém somente data+hora do bloco editorial observado, nunca do corpo."""
    return tuple(
        value
        for value in values
        if len(value) <= 160 and _DISPLAYED_DATETIME_PATTERN.search(value)
    )


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


def _first_specific_value(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip() and not _is_generic_portal_title(value):
            return value.strip()
    return None


def _is_generic_portal_title(value: str | None) -> bool:
    if not value:
        return False
    normalized = " ".join(value.casefold().split())
    return normalized in _GENERIC_PORTAL_TITLES


def _location_from_txt_opening(content: str) -> str | None:
    normalized = " ".join(content.split())
    # Não trate o corpo inteiro como local quando o TXT não começa pela
    # abertura editorial. Nesse caso, o metadado extraído da página prevalece.
    if not re.match(r"^[^()\n]{1,120}\(FOLHAPRESS\)\s*[-–—]", normalized, re.IGNORECASE):
        return None
    return normalize_location(normalized)


def _first_datetime(value: object, fallback: datetime | None) -> datetime | None:
    return value if isinstance(value, datetime) else fallback
