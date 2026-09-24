class FolhapressSourceError(RuntimeError):
    """Falha controlada na fonte externa; nunca carrega corpo ou segredo."""

    def __init__(self, message: str, *, diagnostic_code: str = "source_error") -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


class FolhapressConnectionError(FolhapressSourceError):
    """A página da fonte não respondeu como esperado."""


class FolhapressAuthenticationError(FolhapressSourceError):
    """Não foi possível criar uma sessão autenticada na fonte."""

    def __init__(self, message: str, *, diagnostic_code: str = "authentication_failed") -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


class FolhapressCatalogError(FolhapressSourceError):
    """O catálogo não corresponde ao contrato mínimo esperado."""


class FolhapressDownloadError(FolhapressSourceError):
    """O TXT original não pôde ser baixado ou validado."""

    def __init__(self, message: str, *, diagnostic_code: str = "unknown") -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


RETRYABLE_DIAGNOSTIC_CODES = frozenset({
    "connection_reset",
    "download_failed",
    "download_timeout",
    "temporary_file_missing",
    "browser_download_exception",
    "navigation_timeout",
})


def is_retryable_source_error(error: Exception) -> bool:
    """Indica se a falha é transitória sem inspecionar mensagem ou conteúdo."""

    code = getattr(error, "diagnostic_code", None)
    return isinstance(code, str) and code.lower() in RETRYABLE_DIAGNOSTIC_CODES


class FolhapressItemRetryError(FolhapressSourceError):
    """Falha de item depois de refazer a sessão autenticada de forma limitada."""

    def __init__(self, *, stage: str, error: Exception) -> None:
        diagnostic_code = getattr(error, "diagnostic_code", "unexpected_error")
        if not isinstance(diagnostic_code, str) or not diagnostic_code:
            diagnostic_code = "unexpected_error"
        super().__init__(
            "A nova tentativa controlada da matéria Folhapress falhou",
            diagnostic_code=diagnostic_code,
        )
        self.capture_stage = stage
