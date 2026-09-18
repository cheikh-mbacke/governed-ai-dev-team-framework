#!/usr/bin/env python3
"""Opt-in: migrate a standalone in-tree install to an out-of-tree instance (Document 25)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
SRC_ROOT = SOURCE_ROOT / "src"
if SRC_ROOT.is_dir() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from distribution.installer.errors import InstallationValidationError
from distribution.installer.migrate_to_instance import migrate_in_tree_to_instance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move an in-tree 0.7.x standalone install to a separate instance directory, "
            "leaving a thin member-link on the product checkout. Opt-in — never implied "
            "by tools/install.py --update (INS-AC-018)."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Existing standalone product install (Git root with authoritative .ai-team/)",
    )
    parser.add_argument(
        "--instance",
        required=True,
        help="Empty or non-existent directory that will become the framework instance",
    )
    parser.add_argument("--ensemble-id", required=True, help="Ensemble id (product id)")
    parser.add_argument("--member-id", required=True, help="Member id for the former root")
    parser.add_argument(
        "--member-kind",
        default="service",
        help="Member kind (default: service)",
    )
    parser.add_argument(
        "--instance-id",
        default=None,
        help="Instance project id (default: instance directory name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without changing the disk",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = migrate_in_tree_to_instance(
            source=Path(args.source),
            instance=Path(args.instance),
            ensemble_id=args.ensemble_id,
            member_id=args.member_id,
            member_kind=args.member_kind,
            instance_id=args.instance_id,
            dry_run=args.dry_run,
        )
    except InstallationValidationError as exc:
        print(f"Migration refused ({exc.code}): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
