#!/usr/bin/env python3
"""Bounded, non-interactive recovery for an unattended Run.

Compatibility CLI wrapping ``governed_ai.core.supervisor.recovery``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime

bootstrap_runtime(_ROOT)

from governed_ai.core.supervisor.recovery import recover
from governed_ai.core.workspace import Workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-recoveries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args(argv)
    workspace = Workspace.discover(Path.cwd())
    result = recover(
        workspace,
        args.run_id,
        max_recoveries=max(0, args.max_recoveries),
        launch=args.launch,
        workers=max(1, args.workers),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["outcome"] == "recovered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
