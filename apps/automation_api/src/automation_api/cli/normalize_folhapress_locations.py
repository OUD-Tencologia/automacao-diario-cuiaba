"""Comando interno para corrigir ``ds_local`` a partir do TXT no MinIO."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from automation_api.application.folhapress_location_normalization import (
    run_folhapress_location_normalization,
)
from automation_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza locais Folhapress pelo TXT original")
    parser.add_argument("--limit", type=int, default=100)
    arguments = parser.parse_args()
    result = run_folhapress_location_normalization(get_settings(), limit=arguments.limit)
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
