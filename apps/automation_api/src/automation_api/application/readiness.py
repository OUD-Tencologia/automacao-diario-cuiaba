from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Mapping, Protocol


class DependencyProbe(Protocol):
    """Contrato mínimo para uma dependência necessária à escrita editorial."""

    def ping(self) -> None:
        """Lança exceção se a dependência não puder ser usada."""


@dataclass(frozen=True)
class DependencyStatus:
    status: str
    latency_ms: int


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    dependencies: Mapping[str, DependencyStatus]


class ReadinessService:
    """Verifica se as dependências críticas aceitam operações autenticadas."""

    def __init__(self, dependencies: Mapping[str, DependencyProbe]) -> None:
        self._dependencies = dependencies

    def check(self) -> ReadinessResult:
        statuses: dict[str, DependencyStatus] = {}

        for name, dependency in self._dependencies.items():
            started_at = perf_counter()
            try:
                dependency.ping()
                status = "up"
            except Exception:  # A resposta pública não revela host, segredo ou erro interno.
                status = "down"

            elapsed_ms = round((perf_counter() - started_at) * 1000)
            statuses[name] = DependencyStatus(status=status, latency_ms=elapsed_ms)

        return ReadinessResult(
            ready=all(status.status == "up" for status in statuses.values()),
            dependencies=statuses,
        )
