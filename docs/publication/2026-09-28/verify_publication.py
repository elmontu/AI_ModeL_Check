#!/usr/bin/env python3
"""Verify this frozen reporting bundle with Python's standard library.

Checks manifest hashes, all 104 source IDs/pointers, every bundled JSON file,
frozen table hashes and authored navigation links. It does not rerun training or
prove the scientific claims. Run from anywhere: python verify_publication.py
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent


def safe_path(relative):
    p = (ROOT / relative).resolve()
    assert p.is_relative_to(ROOT), "Out-of-bundle manifest path"
    return p


def read_json(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def main():
    manifest = read_json(ROOT / "publication-manifest.json")
    expected = {f["path"] for f in manifest["files"]} | {"publication-manifest.json"}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert expected == actual, "Unexpected or missing bundle files"
    for entry in manifest["files"]:
        data = safe_path(entry["path"]).read_bytes()
        assert len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
        if entry["path"].endswith(".json"):
            json.loads(data.decode("utf-8-sig"))
    sources = read_json(ROOT / "evidence/source-manifest.json")
    assert {s["id"] for s in sources["sources"]} == {f"E{i:03}" for i in range(1, 105)}
    assert len(sources["sources"]) == 104
    assert len({s["published_path"] for s in sources["sources"]}) == 94
    for entry in sources["sources"]:
        data = safe_path(entry["published_path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["published_sha256"]
        if entry["json_pointer"]:
            value = json.loads(data.decode("utf-8-sig"))
            assert entry["json_pointer"].startswith("/")
            for part in entry["json_pointer"][1:].split("/"):
                key = unquote(part).replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
    for entry in sources["frozen_table_inputs"]:
        data = safe_path(entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    links = 0
    external_context_links = []
    for entry in manifest["files"]:
        name = entry["path"]
        if not name.endswith(".md") or name.startswith(("evidence/source/", "evidence/context/")):
            continue
        source = safe_path(name)
        for match in re.finditer(r"\[[^\]]*\]\(([^\n]+?)\)", source.read_text(encoding="utf-8-sig")):
            target = match[1].strip().split(' "', 1)[0].strip("<>")
            if re.match(r"(?:https?://|mailto:|#)", target):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            resolved = (source.parent / target).resolve()
            if not resolved.is_relative_to(ROOT):
                # Maintained specifications live in the parent repository. A
                # downloaded standalone bundle need not contain them.
                external_context_links.append({"from": name, "target": target, "available": resolved.exists()})
                continue
            assert resolved.exists(), f"Broken bundle link: {name}: {target}"
            links += 1
    return {"status": "passed", "manifest_files": len(expected), "source_references": 104,
            "unique_experimental_sources": 94, "table_files": 3, "declared_tables": 238,
            "declared_result_rows": 5543, "internal_links_checked": links,
            "maintained_reference_links": external_context_links,
            "scope": "Reporting hashes, JSON/pointers and navigation; not model training reproduction or scientific certification."}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
