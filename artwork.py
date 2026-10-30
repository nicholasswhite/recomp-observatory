"""Generic game presentation metadata and bounded local raster uploads."""
import base64
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

CUSTOM=re.compile(r'[a-f0-9]{64}\.(?:jpg|png|webp)\Z')

def default_branding(target):
    return {'subtitle':'PlayStation 3 recomp project','studio':'','coverAsset':'','source':''}

def validate_metadata(value):
    result={}
    for key in ('subtitle','studio','source'):
        item=value.get(key,'')
        if not isinstance(item,str) or len(item)>1000:raise ValueError(f'Invalid artwork {key}')
        result[key]=item.strip()
    if result['source'] and (urlsplit(result['source']).scheme not in ('http','https') or not urlsplit(result['source']).netloc):
        raise ValueError('Artwork source must be an HTTP or HTTPS URL')
    return result

def save_cover(data_url,folder):
    if not isinstance(data_url,str):raise ValueError('Invalid cover image')
    match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)',data_url)
    if not match:raise ValueError('Choose a JPEG, PNG or WebP cover')
    try:data=base64.b64decode(match[2],validate=True)
    except ValueError:raise ValueError('Invalid cover encoding')
    if not 24<=len(data)<=4*1024*1024:raise ValueError('Cover must be at most 4 MiB')
    kind=match[1]
    valid=(kind=='jpeg' and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')) or (kind=='png' and data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16]==b'IHDR') or (kind=='webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP')
    if not valid:raise ValueError('Image content does not match its type')
    suffix={'jpeg':'jpg','png':'png','webp':'webp'}[kind]
    name=hashlib.sha256(data).hexdigest()+'.'+suffix
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    path=folder/name
    if not path.exists():path.write_bytes(data)
    return 'custom/'+name

def cover_url(asset):
    if asset.startswith('custom/') and CUSTOM.fullmatch(asset[7:]):return '/artwork/'+asset
    return ''
