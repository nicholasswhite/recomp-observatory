"""Shallow, read-only browsing of local folders for the repository picker."""
from __future__ import annotations

import os
from pathlib import Path

from pathguard import is_linklike

MAX_ENTRIES = 10000
MAX_FOLDERS = 1000


def _is_local_drive(path):
    if os.name != 'nt':
        return True
    import ctypes
    # Removable, fixed, optical and RAM disks are local. Exclude mapped shares.
    return ctypes.windll.kernel32.GetDriveTypeW(str(Path(path).anchor)) in (2, 3, 5, 6)


def local_folder(value):
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str) or not value.strip() or len(value) > 32767 or '\0' in value:
        raise ValueError('Enter an absolute local folder path')
    value = value.strip()
    if value.replace('\\', '/').startswith('//'):
        raise ValueError('Choose a local folder; network and device paths are not supported')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('Enter an absolute local folder path')
    if not _is_local_drive(path):
        raise ValueError('Choose a folder on a local drive')
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError:
        raise ValueError('This folder does not exist') from None
    except (OSError, RuntimeError) as error:
        raise ValueError('This folder is unavailable or cannot be accessed') from error
    if str(path).replace('\\', '/').startswith('//') or not _is_local_drive(path):
        raise ValueError('Choose a folder on a local drive')
    if not path.is_dir():
        raise ValueError('Choose a folder, rather than a file')
    return path


def _shortcuts():
    candidates = [('Projects', Path('C:/Git'))] if os.name == 'nt' else []
    home = Path.home()
    candidates += [('Home', home), ('Desktop', home / 'Desktop'), ('Documents', home / 'Documents')]
    if os.name == 'nt':
        drives = os.listdrives() if hasattr(os, 'listdrives') else [f'{letter}:/' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
        candidates += [(f'{str(drive)[:2]} drive', Path(drive)) for drive in drives]
    else:
        candidates.append(('File system', Path('/')))
    seen, result = set(), []
    for name, candidate in candidates:
        try:
            folder = local_folder(str(candidate))
        except (ValueError, OSError):
            continue
        key = os.path.normcase(str(folder))
        if key not in seen:
            seen.add(key)
            result.append({'name': name, 'path': str(folder)})
    return result


def browse_folders(path=None):
    """List one directory only; never read file contents or follow child links."""
    shortcuts = _shortcuts()
    if path is None:
        if not shortcuts:
            raise ValueError('No accessible local folders were found')
        path = shortcuts[0]['path']
    folder = local_folder(path)
    children, truncated = [], False
    try:
        with os.scandir(folder) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_ENTRIES:
                    truncated = True
                    break
                try:
                    if is_linklike(entry.path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        children.append({'name': entry.name, 'path': str(folder / entry.name)})
                except OSError:
                    continue
    except OSError as error:
        raise ValueError('This folder cannot be opened; choose another folder or check access permissions') from error
    children.sort(key=lambda item: (item['name'].casefold(), item['name']))
    truncated = truncated or len(children) > MAX_FOLDERS
    return {'path': str(folder), 'parent': str(folder.parent) if folder.parent != folder else None,
            'folders': children[:MAX_FOLDERS], 'shortcuts': shortcuts, 'truncated': truncated}
