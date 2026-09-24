"""PoC não persistente para validar acesso à área TEXTOS da Folhapress.

Usa somente .env ou variáveis de ambiente. Não grava cookies, HTML, screenshots
nem conteúdo licenciado. O download opcional é lido para cálculo de hash e
removido antes do navegador encerrar.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/automation_api/src"))
from automation_api.infrastructure.folhapress.downloader import validate_txt
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError
from automation_api.infrastructure.folhapress.navigation import DOWNLOAD_LINK_INDEX, DOWNLOAD_LINK_READY, error_code


REQUIRED_SETTINGS = (
    "FOLHAPRESS_BASE_URL",
    "FOLHAPRESS_LOGIN_URL",
    "FOLHAPRESS_TEXTS_URL",
    "FOLHAPRESS_USERNAME",
    "FOLHAPRESS_PASSWORD",
)
DEFAULT_USERNAME_SELECTORS = (
    "input[type='email']",
    "input[name*='email' i]",
    "input[name*='login' i]",
    "input[name*='usuario' i]",
)
DEFAULT_PASSWORD_SELECTOR = "input[type='password']"
DEFAULT_SUBMIT_SELECTOR = "button[type='submit'], input[type='submit']"
DEFAULT_ARTICLE_LINK_SELECTOR = "a[href*='/texto/']"
SOURCE_ID_PATTERN = re.compile(r"/texto/(\d+)(?:[/?#]|$)")


class PocError(RuntimeError):
    """Erro seguro para saída de diagnóstico sem conteúdo da fonte."""


def read_env_file(path: Path) -> dict[str, str]:
    """Lê um arquivo .env simples sem modificar o ambiente do processo."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_settings(env_path: Path) -> dict[str, str]:
    local_values = read_env_file(env_path)
    settings = {
        key: os.environ.get(key, local_values.get(key, "")).strip()
        for key in set(local_values) | set(REQUIRED_SETTINGS)
    }
    settings["FOLHAPRESS_TEXTS_URL"] = settings.get("FOLHAPRESS_TEXTS_URL") or settings.get("FOLHAPRESS_CATALOG_URL", "")
    return settings


def missing_settings(settings: dict[str, str]) -> list[str]:
    return [
        key
        for key in REQUIRED_SETTINGS
        if not settings.get(key) or settings[key].startswith("CHANGE_ME")
    ]


def positive_int(value: str, setting_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise PocError(f"{setting_name} deve ser um inteiro positivo.") from error
    if parsed <= 0:
        raise PocError(f"{setting_name} deve ser um inteiro positivo.")
    return parsed


def next_page_url(current_url: str, page_size: int) -> str:
    """Calcula a próxima página usando a convenção Folhapress sr=1,25,49."""
    parsed = urlsplit(current_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current_start = positive_int(query.get("sr", "1"), "sr")
    query["sr"] = str(current_start + page_size)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def self_check() -> None:
    assert next_page_url("https://example.test/textos?sr=1", 24).endswith("sr=25")
    assert next_page_url("https://example.test/textos?foo=bar&sr=25", 24).endswith(
        "foo=bar&sr=49"
    )
    assert SOURCE_ID_PATTERN.search("https://example.test/texto/123456/baixar")


async def first_visible(page: Page, selectors: tuple[str, ...]) -> Locator | None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() and await locator.is_visible():
                return locator
        except PlaywrightTimeoutError:
            continue
    return None


async def authenticate(page: Page, settings: dict[str, str], timeout_ms: int) -> None:
    await page.goto(settings["FOLHAPRESS_LOGIN_URL"], wait_until="domcontentloaded", timeout=timeout_ms)
    configured_username = settings.get("FOLHAPRESS_LOGIN_USERNAME_SELECTOR")
    username_selectors = (
        (configured_username,) if configured_username else DEFAULT_USERNAME_SELECTORS
    )
    username = await first_visible(page, username_selectors)
    password_selector = settings.get("FOLHAPRESS_LOGIN_PASSWORD_SELECTOR") or DEFAULT_PASSWORD_SELECTOR
    password = await first_visible(page, (password_selector,))
    if username is None or password is None:
        raise PocError("Não foi possível localizar os campos de login; configure os seletores locais.")

    await username.fill(settings["FOLHAPRESS_USERNAME"])
    await password.fill(settings["FOLHAPRESS_PASSWORD"])
    submit_selector = settings.get("FOLHAPRESS_LOGIN_SUBMIT_SELECTOR") or DEFAULT_SUBMIT_SELECTOR
    submit = await first_visible(page, (submit_selector,))
    if submit is None:
        raise PocError("Não foi possível localizar o botão de entrada; configure o seletor local.")
    await submit.click()
    await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)


async def discover_source_ids(page: Page, selector: str) -> set[str]:
    source_ids: set[str] = set()
    links = page.locator(selector)
    for index in range(await links.count()):
        href = await links.nth(index).get_attribute("href")
        if href and (match := SOURCE_ID_PATTERN.search(href)):
            source_ids.add(match.group(1))
    return source_ids


async def temporary_download(
    page: Page, base_url: str, source_id: str, timeout_ms: int
) -> dict[str, int | str]:
    download_url = base_url.rstrip("/") + f"/texto/{source_id}/baixar"
    response = await page.goto(base_url.rstrip("/") + f"/texto/{source_id}", wait_until="commit", timeout=timeout_ms)
    if response is None or not 200 <= response.status < 300:
        raise PocError("A página da matéria não respondeu com sucesso.")
    handle = await page.wait_for_function(DOWNLOAD_LINK_READY, arg=download_url, timeout=timeout_ms)
    await handle.dispose()
    links = page.locator("a[href]")
    index = await links.evaluate_all(DOWNLOAD_LINK_INDEX, download_url)
    if index < 0:
        raise PocError("O link do TXT não foi localizado.")
    download = None
    try:
        async with page.expect_download(timeout=timeout_ms) as download_info:
            await links.nth(index).click(timeout=timeout_ms)
        download = await download_info.value
        if await download.failure():
            raise PocError("O navegador não concluiu o download.")
        temporary_path = await download.path()
        if temporary_path is None:
            raise PocError("O download de TXT não disponibilizou arquivo temporário.")
        content = Path(temporary_path).read_bytes()
        try:
            validate_txt(content)
        except FolhapressDownloadError as error:
            raise PocError(error.diagnostic_code) from None
        return {
            "download_status": "obtido_e_removido",
            "content_size_bytes": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
        }
    finally:
        if download is not None:
            await download.delete()


async def run_poc(settings: dict[str, str], headed: bool, download_first: bool) -> dict[str, Any]:
    timeout_ms = positive_int(settings.get("FOLHAPRESS_TIMEOUT_SECONDS", "30"), "FOLHAPRESS_TIMEOUT_SECONDS") * 1000
    page_size = positive_int(settings.get("FOLHAPRESS_PAGE_SIZE", "24"), "FOLHAPRESS_PAGE_SIZE")
    report: dict[str, Any] = {
        "status": "ok",
        "login": False,
        "textos_acessivel": False,
        "filtro_textos_visivel": False,
        "servico_noticioso_visivel": False,
        "filtro_servico_aplicado": False,
        "itens_detectados": 0,
        "proxima_pagina_calculada": False,
        "download": "nao_solicitado",
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed)
        context = await browser.new_context(user_agent=settings.get("FOLHAPRESS_USER_AGENT") or None)
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            await authenticate(page, settings, timeout_ms)
            report["login"] = True
            await page.goto(settings["FOLHAPRESS_TEXTS_URL"], wait_until="domcontentloaded", timeout=timeout_ms)
            report["textos_acessivel"] = True
            page_text = await page.locator("body").inner_text(timeout=timeout_ms)
            expected_filter = settings.get("FOLHAPRESS_FILTER", "TEXTOS")
            expected_service = settings.get("FOLHAPRESS_SERVICE_FILTER", "SERVIÇO NOTICIOSO")
            report["filtro_textos_visivel"] = expected_filter.casefold() in page_text.casefold()
            report["servico_noticioso_visivel"] = expected_service.casefold() in page_text.casefold()

            service_selector = settings.get("FOLHAPRESS_SERVICE_FILTER_SELECTOR")
            if service_selector:
                service_filter = await first_visible(page, (service_selector,))
                if service_filter is None:
                    raise PocError("O seletor local do Serviço Noticioso não foi localizado.")
                await service_filter.click()
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                report["filtro_servico_aplicado"] = True

            article_selector = settings.get("FOLHAPRESS_ARTICLE_LINK_SELECTOR") or DEFAULT_ARTICLE_LINK_SELECTOR
            source_ids = await discover_source_ids(page, article_selector)
            report["itens_detectados"] = len(source_ids)
            if not source_ids:
                raise PocError("Nenhuma matéria elegível foi localizada; revise filtro e seletor local.")
            next_page_url(page.url, page_size)
            report["proxima_pagina_calculada"] = True
            if download_first:
                report.update(
                    await temporary_download(page, settings["FOLHAPRESS_BASE_URL"], min(source_ids), timeout_ms)
                )
            return report
        finally:
            await context.close()
            await browser.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Executa a PoC segura da Folhapress.")
    result.add_argument("--env-file", default=".env", type=Path, help="arquivo local de configuração")
    result.add_argument("--validate-config", action="store_true", help="valida apenas campos obrigatórios")
    result.add_argument("--self-check", action="store_true", help="valida funções puras sem acessar a fonte")
    result.add_argument("--headed", action="store_true", help="abre o navegador para diagnóstico local")
    result.add_argument("--download-first", action="store_true", help="baixa um TXT temporário e o remove")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_check:
        self_check()
        print(json.dumps({"status": "ok", "self_check": True}))
        return 0
    if not args.env_file.is_file():
        print(json.dumps({"status": "erro", "erro": "Arquivo .env local não encontrado."}))
        return 2

    settings = load_settings(args.env_file)
    missing = missing_settings(settings)
    if args.validate_config or missing:
        print(json.dumps({"status": "ok" if not missing else "pendente", "campos_ausentes": missing}))
        return 0 if not missing else 2
    try:
        print(json.dumps(asyncio.run(run_poc(settings, args.headed, args.download_first)), ensure_ascii=False))
        return 0
    except (PocError, PlaywrightError) as error:
        diagnostic = str(error) if isinstance(error, PocError) else error_code(error)
        print(json.dumps({"status": "erro", "erro": diagnostic}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
