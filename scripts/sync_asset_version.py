#!/usr/bin/env python3
"""Synchronise les paramètres ?v= des assets statiques avec VERSION."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
INDEX_HTML = ROOT / "index.html"


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def sync_index(version: str) -> bool:
    content = INDEX_HTML.read_text(encoding="utf-8")
    updated = re.sub(r"(\.(?:css|js)\?v=)\d+", rf"\g<1>{version}", content)
    updated = re.sub(
        r"(Mode-emploi-Lab-Console\.pdf\?v=)\d+",
        rf"\g<1>{version}",
        updated,
    )
    if updated == content:
        return False
    INDEX_HTML.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    version = read_version()
    changed = sync_index(version)
    print(f"Version assets : {version}" + (" (index.html mis à jour)" if changed else ""))


if __name__ == "__main__":
    main()
