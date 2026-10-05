"""Compile source-hashed Markdown tables from the curated later research reports.

This optional documentation builder reads a separate local academic checkout.
The government package and its tests do not require that checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "advisory" / "displayed-tables-2026-10-01.md"
ACADEMIC_COMMIT = "826b5e5fbda2cd50e6bb856a90be1b18619afc11"
ACADEMIC_URL = f"https://github.com/elmontu/AI_Model_Academic/blob/{ACADEMIC_COMMIT}/"
SEPARATOR = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
DATED_FAMILY = re.compile(r"-(20\d{6})$")


def source_documents(index: dict) -> list[tuple[str, str, str, str]]:
    """Return (family, path, published SHA, source status), without duplicates."""
    documents: dict[str, tuple[str, str, str, str]] = {}
    for item in index["families"]:
        family = item["family"]
        match = DATED_FAMILY.search(family)
        if match is None or match.group(1) < "20260929":
            continue
        path = item["canonical_result_markdown"]
        documents[path] = (family, path, item["published_sha256"], item["status"])

    # The v2 gate's duplicate-execution failure was repaired and measured in
    # this later amendment. Omitting it would invert the current-status claim.
    for item in index["advisor_later_results_O1_O7"]:
        if item["label"] != "O4":
            continue
        for companion in item.get("companion_evidence", []):
            path = companion["path"]
            if path.lower().endswith(".md"):
                documents[path] = (
                    "gate-scaling-20260930",
                    path,
                    companion["published_sha256"],
                    "later claim-first gate amendment",
                )
    return sorted(documents.values(), key=lambda row: (row[0], row[1]))


def displayed_tables(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """Extract ordinary pipe-delimited Markdown tables, excluding code fences."""
    found: list[tuple[int, str, list[str]]] = []
    heading = "Unlabelled source section"
    in_fence = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            i += 1
            continue
        if not in_fence and stripped.startswith("#"):
            heading = stripped.lstrip("# ").strip() or heading
        if not in_fence and stripped.startswith("|"):
            start = i
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].rstrip())
                i += 1
            if len(block) >= 2 and SEPARATOR.fullmatch(block[1]):
                found.append((start + 1, heading, block))
            continue
        i += 1
    return found


def compile_digest(academic_root: Path) -> str:
    index_path = academic_root / "CANONICAL-RESULTS.json"
    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    if index.get("schema") != "academic-canonical-results-v1":
        raise ValueError("Unexpected academic canonical-results schema")

    rendered: list[tuple[str, str, str, str, list[tuple[int, str, list[str]]]]] = []
    for family, relative, expected_sha, status in source_documents(index):
        path = academic_root / relative
        data = path.read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(f"Published SHA mismatch for {relative}: {actual_sha}")
        tables = displayed_tables(data.decode("utf-8-sig").splitlines())
        rendered.append((family, relative, expected_sha, status, tables))

    total_tables = sum(len(row[4]) for row in rendered)
    total_rows = sum(max(0, len(table[2]) - 2) for row in rendered for table in row[4])
    families = len({row[0] for row in rendered})
    out = [
        "# Later experimental results: displayed-table digest",
        "",
        "**Evidence cut-off: 1 October 2026.** This is a source-hashed, report-level",
        "appendix to the [technical advisory](technical-report-2026-10-01.md). It",
        "reproduces the pipe-delimited Markdown tables in the curated canonical",
        "29 September–1 October research reports and the later O4 gate amendment.",
        "The 28 September [retired supplement](../government-academic-separation-plan-2026-10-01.md#retired-28-september-archive)",
        "previously contained 51 sections, 238 tables and 5,543 displayed rows;",
        "its files were removed from this checkout at the user's request.",
        "",
        f"**Compiled scope:** {families} dated families, {len(rendered)} source documents,",
        f"{total_tables} Markdown tables and {total_rows} displayed data rows. A row is",
        "a display row, not an independent experimental trial. The compilation",
        "verifies each curated document's published SHA-256 against",
        "`CANONICAL-RESULTS.json`; transformed portable copies can have a different",
        "original source SHA. Research run archives, raw records, model weights,",
        "JSON-only results and other noncanonical amendments are not reproduced",
        "here. The source documents retain methods, denominators, uncertainty,",
        "failed options and caveats needed to interpret these tables.",
        "",
        "The academic GitHub links below pin local academic commit",
        f"`{ACADEMIC_COMMIT}` and are intended public destinations.",
        "At this local-first checkpoint the separate repository has not been",
        "published, so the links must be checked again after publication.",
        "A missing source path or SHA mismatch makes regeneration fail.",
        "",
        "| Family | Curated report | Tables | Displayed rows | Status |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for family, relative, _, status, tables in rendered:
        url = ACADEMIC_URL + relative
        rows = sum(max(0, len(block) - 2) for _, _, block in tables)
        out.append(f"| {family} | [{relative}]({url}) | {len(tables)} | {rows} | {status} |")

    out += [
        "",
        "## Source tables",
        "",
        "Tables below preserve the curated report's displayed text; they are not",
        "fresh experiment reruns or a pooled privacy account. Follow the linked",
        "source section for the result's unit, controls and interpretation.",
        "",
    ]
    table_number = 0
    for family, relative, sha, status, tables in rendered:
        out += [
            f"### {family}: {Path(relative).name}",
            "",
            f"Curated source: [{relative}]({ACADEMIC_URL + relative}) ·",
            f"published SHA-256 `{sha}` · {status}.",
            "",
        ]
        if not tables:
            out += ["No pipe-delimited result table in this canonical report; read its narrative and linked evidence.", ""]
            continue
        for line, heading, block in tables:
            table_number += 1
            out += [
                f"#### T{table_number:03d}: {heading}",
                "",
                f"Source: [{relative}:L{line}]({ACADEMIC_URL + relative}#L{line}).",
                "",
                *block,
                "",
            ]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--academic-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = compile_digest(args.academic_root.resolve())
    output = args.output.resolve()
    if args.check:
        if output.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Display digest differs from curated sources: {output}")
        print(f"verified displayed-table digest: {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote displayed-table digest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
