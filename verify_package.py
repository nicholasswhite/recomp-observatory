"""Verify that a Recomp Observatory source ZIP contains only public files."""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from package_dashboard import FILES

PREFIX = PurePosixPath("recomp-observatory")
TEXT_SUFFIXES = {"", ".md", ".txt", ".py", ".js", ".css", ".json", ".ps1", ".cmd", ".yml", ".yaml"}
FORBIDDEN_MEMBERS = {"work", "__pycache__", ".git", ".venv", "public/artwork"}
FORBIDDEN_TEXT = (
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"[A-Za-z]:/Users/", re.IGNORECASE),
    re.compile(re.escape(chr(92) + "AppData" + chr(92)), re.IGNORECASE),
    re.compile(r"Documents[\\/]Codex", re.IGNORECASE),
    re.compile(r"\bBC[UE][A-Z]\d{5}\b", re.IGNORECASE),
)


def verify(path: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    expected = {PurePosixPath(value).as_posix() for value in FILES}
    with ZipFile(path) as archive:
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or not member.parts or member.parts[0] != PREFIX.name:
                errors.append(f"unsafe member path: {info.filename}")
                continue
            relative = PurePosixPath(*member.parts[1:])
            relative_name = relative.as_posix()
            if relative_name in seen:
                errors.append(f"duplicate release member: {relative}")
            seen.add(relative_name)
            forbidden_path = any(part in FORBIDDEN_MEMBERS for part in relative.parts) or relative.parts[:2] == ("public", "artwork")
            if forbidden_path or relative.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bin", ".elf", ".exe"}:
                errors.append(f"forbidden release member: {relative}")
                continue
            if relative.suffix.lower() in TEXT_SUFFIXES and not info.is_dir():
                try:
                    text = archive.read(info).decode("utf-8")
                except UnicodeDecodeError:
                    errors.append(f"non-UTF-8 public text file: {relative}")
                    continue
                for pattern in FORBIDDEN_TEXT:
                    if pattern.search(text):
                        errors.append(f"private or proprietary identifier in {relative}: {pattern.pattern}")
    for missing in sorted(expected - seen):
        errors.append(f"missing allowlisted member: {missing}")
    for extra in sorted(seen - expected):
        errors.append(f"unexpected release member: {extra}")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python verify_package.py path/to/recomp-observatory.zip", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    errors = verify(path)
    if errors:
        print("Release verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Verified public source package: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
