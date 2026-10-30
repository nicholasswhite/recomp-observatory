"""Local, read-only observatory for multiple recompilation projects."""
from __future__ import annotations
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from workspace import Workspace, discover
from folders import browse_folders

BASE = Path(__file__).resolve().parent
PUBLIC = BASE / 'public'
PORT = 8768
WORKSPACE = None

def workspace_file(value):
    """Keep every writable workspace catalog under the ignored local work tree."""
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else BASE / path).resolve()
    work = (BASE / 'work').resolve()
    if path == work or not path.is_relative_to(work):
        raise ValueError('Workspace files must stay inside the dashboard work folder')
    return path

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        allowed_hosts = {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}
        if self.headers.get('Host') not in allowed_hosts:
            self.send_error(403, 'Loopback host required')
            return
        path = urlsplit(self.path).path
        routes = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/workspace-ui.js': ('workspace-ui.js', 'text/javascript; charset=utf-8'),
                  '/progress.js': ('progress.js', 'text/javascript; charset=utf-8'),
                  '/ps3-details.js': ('ps3-details.js', 'text/javascript; charset=utf-8'),
                  '/ps3-theme.css': ('ps3-theme.css', 'text/css; charset=utf-8'),
                  '/branding.js': ('branding.js', 'text/javascript; charset=utf-8'),
                  '/folders.js': ('folders.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path == '/api/workspace':
            self.send_payload(json.dumps(WORKSPACE.catalog()).encode(), 'application/json')
        elif path == '/api/snapshot':
            try:
                selected = parse_qs(urlsplit(self.path).query).get('target', [None])[0]
                selected = selected or (WORKSPACE.targets[0]['id'] if WORKSPACE.targets else '')
                payload = json.dumps(WORKSPACE.snapshot(selected), allow_nan=False).encode('utf-8')
            except KeyError:
                self.send_payload(b'{"error":"Unknown target"}', 'application/json', 404)
                return
            except Exception as error:
                payload = json.dumps({'error': f'Telemetry unavailable: {type(error).__name__}'}).encode()
                self.send_payload(payload, 'application/json', 503)
                return
            self.send_payload(payload, 'application/json')
        elif path.startswith('/artwork/'):
            from artwork import CUSTOM
            name=path[len('/artwork/'):]
            if name.startswith('custom/') and CUSTOM.fullmatch(name[7:]):asset=BASE/'work/artwork'/name[7:]
            else:self.send_error(404);return
            if not asset.is_file() or asset.is_symlink():self.send_error(404);return
            mime={'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[asset.suffix]
            self.send_payload(asset.read_bytes(),mime)
        elif path in routes:
            filename, mime = routes[path]
            self.send_payload((PUBLIC / filename).read_bytes(), mime)
        elif path == '/health':
            self.send_payload(b'{"service":"recomp-observatory","ok":true}', 'application/json')
        else:
            self.send_error(404)

    def do_POST(self):
        allowed_hosts = {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}
        origin = self.headers.get('Origin')
        if self.headers.get('Host') not in allowed_hosts or self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin not in {f'http://{h}' for h in allowed_hosts}):
            self.send_error(403, 'Same-origin loopback request required'); return
        if self.headers.get_content_type() != 'application/json':
            self.send_error(415, 'JSON required'); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            limit=6*1024*1024 if self.path=='/api/branding' else 256000
            if not 0 < length <= limit: raise ValueError('Request exceeds the allowed size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError('Expected a JSON object')
            if self.path == '/api/discover':
                folder = data.get('root')
                if not isinstance(folder, str) or not folder.strip(): raise ValueError('Enter a repository folder')
                value = discover(folder)
            elif self.path == '/api/folders': value = browse_folders(data.get('path'))
            elif self.path == '/api/targets': value = WORKSPACE.add(data.get('targets'))
            elif self.path == '/api/branding': value = WORKSPACE.set_branding(data.get('gameId'),data)
            else: self.send_error(404); return
            self.send_payload(json.dumps(value).encode(), 'application/json')
        except (ValueError, TypeError, OSError) as error:
            self.send_payload(json.dumps({'error':str(error)}).encode(), 'application/json', 400)

    def send_payload(self, data, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ('200', '304'):
            super().log_message(fmt, *args)

def main():
    global PORT, WORKSPACE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=BASE / 'work/workspace.json')
    parser.add_argument('--source', type=Path, help='Discover and add a repository')
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    try:
        args.workspace = workspace_file(args.workspace)
    except ValueError as error:
        parser.error(str(error))
    PORT = args.port
    WORKSPACE = Workspace(args.workspace, BASE / 'work/history')
    if args.source: WORKSPACE.add(discover(args.source)['targets'])
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    stop_sampler = threading.Event()
    def sample_targets():
        while not stop_sampler.is_set():
            for target in WORKSPACE.catalog()['targets']:
                if stop_sampler.is_set(): break
                try: WORKSPACE.snapshot(target['id'])
                except (OSError, ValueError, KeyError, TypeError): pass
            stop_sampler.wait(30)
    sampler = threading.Thread(target=sample_targets, name='observatory-history', daemon=True)
    sampler.start()
    print(f'Recomp Observatory: http://127.0.0.1:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_sampler.set()
        server.server_close()

if __name__ == '__main__':
    main()
