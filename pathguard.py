"""Filesystem-boundary helpers shared by all read-only repository scanners."""
from __future__ import annotations

import stat
import os
from pathlib import Path


def is_linklike(path) -> bool:
    """Treat symlinks and Windows reparse points (including junctions) alike."""
    candidate = Path(path)
    try:
        if candidate.is_symlink():
            return True
        is_junction = getattr(candidate, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse)
    except (OSError, RuntimeError):
        # An unreadable or unstable entry is never worth crossing during an
        # observational scan.
        return True


def is_contained(path, root) -> bool:
    """Return whether a resolved path remains under the resolved scan root."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def is_safe_entry(path, root) -> bool:
    """Accept an existing entry only when every scanned component is safe."""
    try:
        boundary = Path(root).resolve()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = boundary / candidate
        # abspath normalizes parent segments without following links. Check each
        # component in order so a junction is rejected before touching children.
        lexical = Path(os.path.abspath(candidate))
        relative = lexical.relative_to(boundary)
        current = boundary
        for part in relative.parts:
            current = current / part
            if is_linklike(current):
                return False
        return is_contained(lexical, boundary)
    except (OSError, RuntimeError, ValueError):
        return False
