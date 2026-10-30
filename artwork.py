"""Generic game presentation metadata and bounded local raster artwork."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from pathguard import is_linklike, is_safe_entry

CUSTOM = re.compile(r'[a-f0-9]{64}\.(?:jpg|png|webp)\Z')
AUTO = re.compile(r'[a-f0-9]{64}\.png\Z')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
AUTO_SCHEMA = 'ps3-workbench/artwork-v1'
AUTO_ROLES = ('icon', 'overlay', 'background')
MANIFEST_LIMIT = 64 * 1024
IMAGE_LIMIT = 8 * 1024 * 1024
TOTAL_IMAGE_LIMIT = 16 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_PIXELS = 32 * 1024 * 1024
AUTO_CACHE_LIMIT = 256 * 1024 * 1024


def default_branding(target):
    return {'subtitle': 'PlayStation 3 recomp project', 'studio': '', 'coverAsset': '', 'source': ''}


def validate_metadata(value):
    result = {}
    for key in ('subtitle', 'studio', 'source'):
        item = value.get(key, '')
        if not isinstance(item, str) or len(item) > 1000:
            raise ValueError(f'Invalid artwork {key}')
        result[key] = item.strip()
    if result['source'] and (urlsplit(result['source']).scheme not in ('http', 'https') or not urlsplit(result['source']).netloc):
        raise ValueError('Artwork source must be an HTTP or HTTPS URL')
    return result


def save_cover(data_url, folder):
    if not isinstance(data_url, str):
        raise ValueError('Invalid cover image')
    match = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', data_url)
    if not match:
        raise ValueError('Choose a JPEG, PNG or WebP cover')
    try:
        data = base64.b64decode(match[2], validate=True)
    except ValueError:
        raise ValueError('Invalid cover encoding')
    if not 24 <= len(data) <= 4 * 1024 * 1024:
        raise ValueError('Cover must be at most 4 MiB')
    kind = match[1]
    valid = ((kind == 'jpeg' and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')) or
             (kind == 'png' and data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR') or
             (kind == 'webp' and data[:4] == b'RIFF' and data[8:12] == b'WEBP'))
    if not valid:
        raise ValueError('Image content does not match its type')
    suffix = {'jpeg': 'jpg', 'png': 'png', 'webp': 'webp'}[kind]
    name = hashlib.sha256(data).hexdigest() + '.' + suffix
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
    return 'custom/' + name


def artwork_url(asset):
    if not isinstance(asset, str):
        return ''
    if asset.startswith('custom/') and CUSTOM.fullmatch(asset[7:]):
        return '/artwork/' + asset
    if asset.startswith('auto/') and AUTO.fullmatch(asset[5:]):
        return '/artwork/' + asset
    return ''


def cover_url(asset):
    """Backward-compatible name for callers that only know about covers."""
    return artwork_url(asset)


def _reject_json_constant(value):
    raise ValueError(f'Unsupported JSON number: {value}')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate artwork manifest key')
        result[key] = value
    return result


def _stable_read(path, limit):
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError('Artwork file exceeds its allowed size')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    after = path.stat()
    signature = lambda value: (value.st_dev, value.st_ino, value.st_size,
                               value.st_mtime_ns, getattr(value, 'st_ctime_ns', 0))
    if len(data) > limit or len(data) != before.st_size or signature(before) != signature(after):
        raise ValueError('Artwork file changed while it was read')
    return data


def _png_dimensions(data):
    if (len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or
            data[8:12] != b'\x00\x00\x00\r' or data[12:16] != b'IHDR'):
        raise ValueError('Artwork is not a valid PNG')
    width = int.from_bytes(data[16:20], 'big')
    height = int.from_bytes(data[20:24], 'big')
    if (not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION or
            width * height > MAX_PIXELS):
        raise ValueError('Artwork dimensions exceed the allowed bounds')
    return width, height


def _relative_asset_path(value):
    if (not isinstance(value, str) or not value or len(value) > 512 or value != value.strip() or
            '\\' in value or ':' in value or '//' in value or value.startswith('/')):
        raise ValueError('Artwork paths must be relative POSIX paths')
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in ('', '.', '..') for part in relative.parts):
        raise ValueError('Artwork path escapes its presentation folder')
    return Path(*relative.parts)


def _cache_png(data, digest, folder):
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    if is_linklike(root):
        raise ValueError('Artwork cache root is link-like')
    auto = root / 'auto'
    auto.mkdir(exist_ok=True)
    if is_linklike(auto):
        raise ValueError('Artwork cache is link-like')
    destination = auto / f'{digest}.png'
    if destination.exists() and (is_linklike(destination) or not is_safe_entry(destination, root)):
        raise ValueError('Artwork cache entry is unsafe')
    if destination.is_file():
        try:
            existing = _stable_read(destination, IMAGE_LIMIT)
            if hashlib.sha256(existing).hexdigest() == digest:
                return 'auto/' + destination.name
        except (OSError, ValueError):
            pass
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=auto, prefix='.artwork-', suffix='.tmp', delete=False) as stream:
            stream.write(data)
            temporary = Path(stream.name)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
    return 'auto/' + destination.name


def _cached_branding_is_valid(branding, folder):
    root = Path(folder)
    auto = root / 'auto'
    if not root.is_dir() or not auto.is_dir() or is_linklike(root) or is_linklike(auto):
        return not any(branding.get(f'{role}Asset') for role in AUTO_ROLES)
    for role in AUTO_ROLES:
        asset = branding.get(f'{role}Asset')
        if not asset:
            continue
        if not isinstance(asset, str) or not asset.startswith('auto/') or not AUTO.fullmatch(asset[5:]):
            return False
        source = auto / asset[5:]
        try:
            if is_linklike(source) or not is_safe_entry(source, root):
                return False
            data = _stable_read(source, IMAGE_LIMIT)
            width, height = _png_dimensions(data)
            if (hashlib.sha256(data).hexdigest() != source.stem or
                    width != branding.get(f'{role}Width') or height != branding.get(f'{role}Height')):
                return False
        except (OSError, ValueError):
            return False
    return True


def _prune_auto_cache(folder, cache, keep):
    """Bound only the reproducible automatic cache and invalidate evicted entries."""
    root = Path(folder)
    auto = root / 'auto'
    if not auto.is_dir() or is_linklike(root) or is_linklike(auto):
        return
    entries = []
    try:
        for path in auto.iterdir():
            if (not AUTO.fullmatch(path.name) or is_linklike(path) or
                    not is_safe_entry(path, root)):
                continue
            details = path.stat()
            if stat.S_ISREG(details.st_mode):
                entries.append((details.st_mtime_ns, details.st_size, path))
    except OSError:
        return
    total = sum(size for _, size, _ in entries)
    if total <= AUTO_CACHE_LIMIT:
        return
    referenced = {}
    for target_key, value in cache.items():
        names = {asset[5:] for role in AUTO_ROLES
                 if isinstance((asset := value.get('branding', {}).get(f'{role}Asset')), str)
                 and asset.startswith('auto/') and AUTO.fullmatch(asset[5:])}
        for name in names:
            referenced.setdefault(name, set()).add(target_key)
    deleted = set()
    candidates = sorted(entries, key=lambda item: (item[2].name in referenced, item[0]))
    for _, size, path in candidates:
        if total <= AUTO_CACHE_LIMIT:
            break
        if path.name in keep:
            continue
        try:
            path.unlink()
            total -= size
            deleted.add(path.name)
        except OSError:
            continue
    if deleted:
        for target_key in list(cache):
            value = cache[target_key]
            assets = {asset[5:] for role in AUTO_ROLES
                      if isinstance((asset := value.get('branding', {}).get(f'{role}Asset')), str)
                      and asset.startswith('auto/')}
            if assets & deleted:
                cache.pop(target_key, None)


def automatic_branding(target_root, cache_folder, cache=None):
    """Verify a target-produced manifest and return local cached artwork metadata.

    Invalid or absent artwork is deliberately indistinguishable from no artwork so
    target paths and parser details never leak into the dashboard response.
    """
    key = str(Path(target_root).resolve())
    manifest = Path(target_root) / 'presentation' / 'artwork.json'
    try:
        root = Path(target_root)
        presentation = root / 'presentation'
        if (not manifest.is_file() or is_linklike(manifest) or
                not is_safe_entry(manifest, root)):
            if cache is not None:
                cache.pop(key, None)
            return {}
        raw = _stable_read(manifest, MANIFEST_LIMIT)
        manifest_digest = hashlib.sha256(raw).hexdigest()
        if cache is not None and cache.get(key, {}).get('digest') == manifest_digest:
            cached_branding = cache[key]['branding']
            if _cached_branding_is_valid(cached_branding, cache_folder):
                return dict(cached_branding)
            cache.pop(key, None)
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=_reject_json_constant)
        if not isinstance(value, dict) or value.get('schema') != AUTO_SCHEMA:
            raise ValueError('Unsupported artwork manifest')
        entries = value.get('artwork')
        if not isinstance(entries, dict) or any(role not in AUTO_ROLES for role in entries):
            raise ValueError('Invalid artwork role map')
        branding = {}
        total = 0
        for role in AUTO_ROLES:
            entry = entries.get(role)
            if entry is None:
                continue
            required = {'path', 'mime', 'byteCount', 'width', 'height', 'sha256'}
            if not isinstance(entry, dict) or set(entry) != required or entry.get('mime') != 'image/png':
                raise ValueError('Invalid artwork entry')
            if (type(entry.get('byteCount')) is not int or type(entry.get('width')) is not int or
                    type(entry.get('height')) is not int or
                    not 24 <= entry['byteCount'] <= IMAGE_LIMIT or
                    not SHA256.fullmatch(entry.get('sha256', ''))):
                raise ValueError('Invalid artwork metadata')
            source = presentation / _relative_asset_path(entry['path'])
            if (source.suffix.lower() != '.png' or not source.is_file() or is_linklike(source) or
                    not is_safe_entry(source, presentation)):
                raise ValueError('Unsafe artwork source')
            data = _stable_read(source, IMAGE_LIMIT)
            width, height = _png_dimensions(data)
            digest = hashlib.sha256(data).hexdigest()
            if (len(data) != entry['byteCount'] or width != entry['width'] or
                    height != entry['height'] or digest != entry['sha256']):
                raise ValueError('Artwork metadata does not match its PNG')
            total += len(data)
            if total > TOTAL_IMAGE_LIMIT:
                raise ValueError('Combined artwork exceeds the allowed size')
            asset = _cache_png(data, digest, cache_folder)
            branding[f'{role}Asset'] = asset
            branding[f'{role}Width'] = width
            branding[f'{role}Height'] = height
        if branding:
            branding['artworkOrigin'] = 'target'
        if cache is not None:
            cache[key] = {'digest': manifest_digest, 'branding': dict(branding)}
            keep = {asset[5:] for role in AUTO_ROLES
                    if isinstance((asset := branding.get(f'{role}Asset')), str)
                    and asset.startswith('auto/')}
            _prune_auto_cache(cache_folder, cache, keep)
        return branding
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        if cache is not None:
            cache.pop(key, None)
        return {}
