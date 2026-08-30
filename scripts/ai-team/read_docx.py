#!/usr/bin/env python3
"""Extract text from a .docx file: paragraphs and table rows, in document order.

Usage:
  python scripts/ai-team/read_docx.py PATH.docx
  python scripts/ai-team/read_docx.py PATH.docx --grep PATTERN [--context N]

This exists so reading an authoritative .docx product source (common under
docs/product/) does not require an ad hoc inline script each time - an
allowlisted, fixed command instead of Shell(python) approval on every call.
Table rows are joined with ' | ' so a row stays one greppable line - useful
for matrix/table-heavy sources (traceability matrices, decision registers).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from i18n import project_language, t

try:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ModuleNotFoundError:
    print("Missing dependency: python-docx. Install it first, then re-run this command:")
    print("  pip install -r requirements.txt")
    print("(or: pip install python-docx)")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
LANG = project_language(ROOT)


def extract_blocks(path: Path) -> list[str]:
    document = docx.Document(str(path))
    blocks = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, document).text.strip()
            if text:
                blocks.append(text)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, document).rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    blocks.append(" | ".join(cells))
    return blocks


def main() -> int:
    # Extracted document text is whatever the source uses (often French, with
    # accents); force UTF-8 out regardless of the host console's codepage
    # (default cp1252/cp850 on Windows would otherwise corrupt it).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--grep", help="case-insensitive regex; print only matching blocks")
    parser.add_argument(
        "--context",
        type=int,
        default=0,
        help="characters of context to print around each --grep match instead of the full block",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(t(LANG, f"File not found: {args.path}", f"Fichier introuvable : {args.path}"))
        return 2

    try:
        blocks = extract_blocks(args.path)
    except Exception as exc:
        print(t(
            LANG,
            f"Could not read {args.path}: {exc}",
            f"Lecture impossible de {args.path} : {exc}",
        ))
        return 1

    if not args.grep:
        for block in blocks:
            print(block)
        return 0

    pattern = re.compile(args.grep, re.IGNORECASE)
    matched = False
    for block in blocks:
        match = pattern.search(block)
        if not match:
            continue
        matched = True
        if args.context:
            start = max(0, match.start() - args.context)
            end = min(len(block), match.end() + args.context)
            print(f"...{block[start:end]}...")
        else:
            print(block)
        print("---")
    if not matched:
        print(t(
            LANG,
            f"No match for {args.grep!r} in {args.path}",
            f"Aucune correspondance pour {args.grep!r} dans {args.path}",
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
