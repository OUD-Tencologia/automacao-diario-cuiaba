from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from automation_api.application.folhapress_reconciliation import run_folhapress_reconciliation
from automation_api.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repara registros Folhapress antigos sem apagar dados ou expor uma API.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Quantidade mÃ¡xima de itens elegÃ­veis")
    arguments = parser.parse_args()
    result = run_folhapress_reconciliation(get_settings(), limit=arguments.limit)
    print(json.dumps(asdict(result), ensure_ascii=False, default=list))
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
