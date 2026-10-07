#!/usr/bin/env python3
"""Refresh the embedded dataset helper and package a reproducible one-file ZIP."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def artifacts() -> tuple[bytes, bytes]:
    helper = (ROOT / "scripts/prepare_demo_data.py").read_bytes()
    source = (ROOT / "Try-Demo.cmd").read_bytes().decode("utf-8")
    fields = {
        "DataProbeBase64": base64.b64encode(helper).decode("ascii"),
        "DataProbeHash": hashlib.sha256(helper).hexdigest(),
    }
    for name, value in fields.items():
        source, count = re.subn(r"(?m)^\$" + name + r" = '[^'\r\n]*'",
                               lambda _: "$" + name + " = '" + value + "'", source)
        if count != 1:
            raise ValueError("Expected exactly one embedded helper field: " + name)
    launcher = source.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entry = zipfile.ZipInfo("Try-Demo.cmd", (2026, 10, 7, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, launcher, compresslevel=9)
    return launcher, output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify distribution without writing")
    args = parser.parse_args()
    launcher, archive = artifacts()
    outputs = ((ROOT / "Try-Demo.cmd", launcher), (ROOT / "demo/Try-Demo.zip", archive))
    for path, content in outputs:
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                parser.exit(1, "Distribution differs: " + str(path) + "\nRun scripts/build_demo_launcher.py.\n")
        elif not path.is_file() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print("Verified one-file distribution:", hashlib.sha256(archive).hexdigest())


if __name__ == "__main__":
    main()
