"""Comando interno para reconstruir metadados pelo TXT original do MinIO."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from automation_api.application.folhapress_txt_metadata_repair import (
    run_folhapress_txt_metadata_repair,
)
from automation_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repara chapéu, título, data, autor e local pelo TXT Folhapress"
    )
    parser.add_argument("--limit", type=int, default=100)
    arguments = parser.parse_args()
    result = run_folhapress_txt_metadata_repair(get_settings(), limit=arguments.limit)
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
