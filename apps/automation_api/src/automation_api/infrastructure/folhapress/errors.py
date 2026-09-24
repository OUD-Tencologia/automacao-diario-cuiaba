class FolhapressSourceError(RuntimeError):
    """Falha controlada na fonte externa; nunca carrega corpo ou segredo."""


class FolhapressConnectionError(FolhapressSourceError):
    """A página da fonte não respondeu como esperado."""


class FolhapressAuthenticationError(FolhapressSourceError):
    """Não foi possível criar uma sessão autenticada na fonte."""


class FolhapressCatalogError(FolhapressSourceError):
    """O catálogo não corresponde ao contrato mínimo esperado."""


class FolhapressDownloadError(FolhapressSourceError):
    """O TXT original não pôde ser baixado ou validado."""

    def __init__(self, message: str, *, diagnostic_code: str = "unknown") -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
