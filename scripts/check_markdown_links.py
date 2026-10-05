#!/usr/bin/env python3
"""Check published Markdown targets; report local-only output/ artifacts separately."""

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


def _check_links(sources: tuple[Path, ...]) -> tuple[tuple[str, ...], int]:
    failures: list[str] = []
    generated_count = 0
    generated_root = ROOT.resolve() / "output"
    for source in sources:
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK_PATTERN.finditer(line):
                target = match.group(1).strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                if not target or target.startswith(EXTERNAL_PREFIXES):
                    continue
                local_path = unquote(target.split("#", 1)[0])
                resolved_target = (source.parent / local_path).resolve()
                # output/ is an ignored, local experiment workspace. Resolve
                # first so output/../docs/missing.md still fails publication.
                if resolved_target.is_relative_to(generated_root):
                    generated_count += 1
                    continue
                if not resolved_target.exists():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing local target {target!r}"
                    )
    return tuple(failures), generated_count


def missing_links() -> tuple[str, ...]:
    """Return missing published targets, preserving the existing public API."""
    return _check_links(markdown_files())[0]


def main() -> int:
    sources = markdown_files()
    failures, generated_count = _check_links(sources)
    print(
        f"checked local links in {len(sources)} Markdown files; "
        f"{generated_count} local-only generated artifact links under output/ (not checked)"
    )
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
