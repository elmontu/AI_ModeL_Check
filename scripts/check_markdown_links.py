#!/usr/bin/env python3
"""Fail when a repository Markdown link points to a missing local target."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {".git", ".venv", ".venv-pipeline", ".local", ".privacy-venv", "build", "dist", "output"}
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("#", "http://", "https://", "mailto:")


def markdown_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            source
            for source in ROOT.rglob("*.md")
            if not SKIP_DIRECTORIES.intersection(source.relative_to(ROOT).parts)
        )
    )


def missing_links() -> tuple[str, ...]:
    failures: list[str] = []
    for source in markdown_files():
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK_PATTERN.finditer(line):
                target = match.group(1).strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                if not target or target.startswith(EXTERNAL_PREFIXES):
                    continue
                local_path = unquote(target.split("#", 1)[0])
                if not (source.parent / local_path).exists():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing local target {target!r}"
                    )
    return tuple(failures)


def main() -> int:
    failures = missing_links()
    if failures:
        print("\n".join(failures))
        return 1
    print(f"checked local links in {len(markdown_files())} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
