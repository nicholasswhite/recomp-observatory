"""Local target catalog, bounded discovery and isolated observation histories."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from adapters import collect_target
from artwork import default_branding, validate_metadata, save_cover, artwork_url, automatic_branding
from folders import local_folder
from pathguard import is_contained, is_linklike, is_safe_entry

ADAPTERS = {'independent-reports-v1', 'ps3recomp-manifest-v1', 'inventory-v1'}

def identity(target):
    value = f"{Path(target['root']).resolve()}|{target['adapter']}|{target['id']}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]

def validate_target(value, base):
    if not isinstance(value, dict):
        raise ValueError('A target must be an object')
    result = {}
    for key in ('id', 'gameId', 'gameTitle', 'title', 'toolchain', 'root', 'adapter'):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip() or len(item) > 1000:
            raise ValueError(f'Missing or invalid target {key}')
        result[key] = item.strip()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', result['id']):
        raise ValueError('Target ID must use letters, numbers, underscores or hyphens')
    if result['adapter'] not in ADAPTERS:
        raise ValueError('Unsupported report reader')
    root = Path(result['root']).expanduser()
    result['root'] = str((root if root.is_absolute() else base / root).resolve())
    reports = value.get('reports', {})
    if not isinstance(reports, dict):
        raise ValueError('Reports must be an object')
    result['reports'] = {}
    for key in ('build', 'performance'):
        if key in reports:
            path = Path(reports[key])
            if path.is_absolute() or not (Path(result['root']) / path).resolve().is_relative_to(Path(result['root'])):
                raise ValueError('Report paths must stay inside their target folder')
            result['reports'][key] = path.as_posix()
    return result

def discover(folder):
    root = local_folder(folder)
    skip = {'.git', '.venv', 'venv', 'work', 'node_modules', 'build', 'dist', 'generated',
            'third_party', 'vendor', 'saves', 'logs', 'rollback', 'deps', '__pycache__'}
    found, seen, warnings = [], set(), []
    visited = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        current = Path(current)
        if current != root and not is_safe_entry(current, root):
            dirs[:] = []
            continue
        visited += 1
        if visited > 1000:
            warnings.append('Discovery stopped after 1,000 folders. Scan a narrower folder for more targets.')
            break
        depth = len(current.relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip and is_safe_entry(current / d, root)) if depth < 4 else []
        if 'observatory.project.json' in files:
            manifest = current / 'observatory.project.json'
            try:
                if is_linklike(manifest) or not is_contained(manifest, root):
                    raise ValueError('Project manifest must be an unlinked file inside the selected repository folder')
                if manifest.stat().st_size > 256000:
                    raise ValueError('Project manifest exceeds 256 kB')
                data = json.loads(manifest.read_text(encoding='utf-8-sig'))
                if not isinstance(data, dict) or data.get('schemaVersion') != 1 or not isinstance(data.get('targets'), list):
                    raise ValueError('Expected schemaVersion 1 and a targets array')
                for candidate in data['targets'][:50]:
                    target = validate_target(candidate, current)
                    if not is_contained(target['root'], root):
                        raise ValueError('Manifest target roots must stay inside the selected repository folder')
                    if (target['root'], target['adapter']) not in seen:
                        found.append(target); seen.add((target['root'], target['adapter']))
                dirs[:] = []  # Manifest explicitly defines this project's boundaries.
                continue
            except (OSError, ValueError, TypeError) as error:
                warnings.append(f'{manifest.relative_to(root)}: {error}')
        adapter = None
        reports = current / 'reports'
        ppu_report = reports / 'ppu-generation.json'
        spu_report = reports / 'spu-generation.json'
        project_output = current / 'project/recompiled'
        startup_analysis = current / 'analysis/startup'
        if (is_safe_entry(reports, root) and reports.is_dir() and
                ((is_safe_entry(ppu_report, root) and ppu_report.is_file()) or
                 (is_safe_entry(spu_report, root) and spu_report.is_file()))):
            adapter = 'independent-reports-v1'
        elif (is_safe_entry(project_output, root) and project_output.is_dir() and
              is_safe_entry(startup_analysis, root) and startup_analysis.is_dir()):
            adapter = 'ps3recomp-manifest-v1'
        if adapter and (str(current), adapter) not in seen:
            key = hashlib.sha256(f'{current}|{adapter}'.encode()).hexdigest()[:12]
            found.append({'id': f'target-{key}', 'gameId': f'game-{key}', 'gameTitle': current.name,
                          'title': 'Independent port' if adapter == 'independent-reports-v1' else 'PS3Recomp port',
                          'toolchain': 'Independent tooling' if adapter == 'independent-reports-v1' else 'PS3Recomp',
                          'root': str(current), 'adapter': adapter, 'reports': {}})
            seen.add((str(current), adapter)); dirs[:] = []
    if not found:
        warnings.append('No recognized reports found. You can still add this folder for metadata-only observation, or supply observatory.project.json.')
        key = hashlib.sha256(str(root).encode()).hexdigest()[:12]
        found.append({'id': f'target-{key}', 'gameId': f'game-{key}', 'gameTitle': root.name,
                      'title': 'Repository inventory', 'toolchain': 'Unspecified', 'root': str(root),
                      'adapter': 'inventory-v1', 'reports': {}})
    return {'targets': found, 'warnings': warnings, 'foldersVisited': visited, 'maxDepth': 4}

class Workspace:
    def __init__(self, config, state):
        self.config, self.state = Path(config), Path(state)
        self.lock = threading.RLock()
        self.cache = {}
        self.artwork_cache = {}
        self.targets = []
        self.name = 'Recomp workspace'
        self.games = {}
        self.reload()

    def reload(self):
        if self.config.exists():
            value = json.loads(self.config.read_text(encoding='utf-8-sig'))
            self.targets = [validate_target(t, self.config.parent) for t in value['targets']]
            if len({t['id'] for t in self.targets}) != len(self.targets):
                raise ValueError('Target IDs must be unique')
            self.name = str(value.get('name', 'Recomp workspace'))
            self.games = value.get('games',{}) if isinstance(value.get('games',{}),dict) else {}

    def presentation(self,target):
        automatic = automatic_branding(target['root'], self.state.parent/'artwork', self.artwork_cache)
        manual = self.games.get(target['gameId'], {})
        branding = {**default_branding(target), **automatic, **manual}
        branding['coverUrl'] = artwork_url(branding.get('coverAsset', ''))
        for role in ('icon', 'overlay', 'background'):
            branding[f'{role}Url'] = artwork_url(branding.get(f'{role}Asset', ''))
        if branding['coverUrl']:
            branding['artworkOrigin'] = 'manual'
        elif automatic:
            branding['artworkOrigin'] = 'target'
        else:
            branding['artworkOrigin'] = ''
        return {**target,'branding':branding}

    def set_branding(self,game_id,data):
        with self.lock:
            target=next((t for t in self.targets if t['gameId']==game_id),None)
            if not target:raise ValueError('Unknown game')
            if data.get('reset') is True:
                self.games.pop(game_id,None)
            else:
                branding={**default_branding(target),**self.games.get(game_id,{}),**validate_metadata(data)}
                if data.get('image'):
                    branding['coverAsset']=save_cover(data['image'],self.state.parent/'artwork')
                self.games[game_id]=branding
            self.config.parent.mkdir(parents=True,exist_ok=True)
            temp=self.config.with_suffix('.tmp')
            temp.write_text(json.dumps({'schemaVersion':1,'name':self.name,'targets':self.targets,'games':self.games},indent=2),encoding='utf-8')
            temp.replace(self.config);self.cache.clear()
            return self.catalog()

    def catalog(self):
        with self.lock:
            return {'name': self.name, 'targets': [{**self.presentation(t), 'available': Path(t['root']).is_dir()} for t in self.targets]}

    def add(self, values):
        with self.lock:
            if not isinstance(values, list) or not 1 <= len(values) <= 50:
                raise ValueError('Select between 1 and 50 targets')
            targets = [validate_target(t, self.config.parent) for t in values]
            combined = list(self.targets)
            for target in targets:
                existing = next((t for t in combined if Path(t['root']) == Path(target['root']) and t['adapter'] == target['adapter']), None)
                if existing:
                    continue  # Same repo scan is idempotent and retains the saved name.
                if any(t['id'] == target['id'] for t in combined):
                    raise ValueError('Target ID already exists')
                same_game = next((t for t in combined if t['gameTitle'].casefold() == target['gameTitle'].casefold()), None)
                if same_game:
                    target['gameId'] = same_game['gameId']
                combined.append(target)
            if len(combined) > 100:
                raise ValueError('Workspace supports up to 100 targets')
            self.config.parent.mkdir(parents=True, exist_ok=True)
            temp = self.config.with_suffix('.tmp')
            temp.write_text(json.dumps({'schemaVersion': 1, 'name': self.name, 'targets': combined, 'games':self.games}, indent=2), encoding='utf-8')
            temp.replace(self.config)
            self.targets = combined
            return self.catalog()

    def snapshot(self, target_id):
        with self.lock:
            target = next((t for t in self.targets if t['id'] == target_id), None)
            if not target:
                raise KeyError('Unknown target')
            key = identity(target)
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached[0] < 3:
                return copy.deepcopy(cached[1])
            value = collect_target(target)
            value['target'] = self.presentation(target)
            self.state.mkdir(parents=True, exist_ok=True)
            history_path = self.state / f'{key}.json'
            try:
                history = json.loads(history_path.read_text(encoding='utf-8'))
                if not isinstance(history, list): history = []
            except (OSError, ValueError):
                history = []
            point = {'at': value['collectedAt'], 'ppu': value['ppu'].get('emittedSourceBytes'),
                     'spu': value['spu'].get('emittedSourceBytes'), 'unresolved': value['imports'].get('unresolvedCount'),
                     'rawSpu': value.get('rawSpu',{}).get('emittedSourceBytes'),
                     'buildAt': value['build'].get('linkedAt'),
                     'ppuTotal': value['ppu'].get('sourceBytes'), 'spuTotal': value['spu'].get('sourceBytes'),
                     'rawSpuTotal': value.get('rawSpu',{}).get('sourceBytes'),
                     'buildUnits': value['build'].get('translationUnits'),
                     'componentTrue': value['build'].get('componentSummary',{}).get('trueCount'),
                     'componentTotal': value['build'].get('componentSummary',{}).get('total')}
            metrics=value.get('ps3Metrics',{})
            point.update(ppuFunctions=metrics.get('ppu',{}).get('generatedFunctions'),
                         spuFunctions=metrics.get('spu',{}).get('generatedFunctions'))
            try:
                elapsed = (datetime.fromisoformat(point['at'].replace('Z','+00:00')) - datetime.fromisoformat(history[-1]['at'].replace('Z','+00:00'))).total_seconds() if history else 60
            except (ValueError, KeyError, TypeError): elapsed = 60
            if not history or elapsed >= 60 or {k:v for k,v in point.items() if k!='at'} != {k:v for k,v in history[-1].items() if k!='at'}:
                history = (history + [point])[-10080:]
                temp = history_path.with_suffix('.tmp')
                temp.write_text(json.dumps(history, indent=2), encoding='utf-8'); temp.replace(history_path)
            value['history'] = history
            value['monitor'] = {'refreshSeconds': 5, 'sampleSeconds': 30, 'historyHeartbeatSeconds': 60, 'historyStartedAt': history[0]['at'], 'historySamples': len(history), 'readOnly': True}
            self.cache[key] = (time.monotonic(), copy.deepcopy(value))
            # Standard metadata-only report emitted by the observer, not the target build.
            report_path=self.state.parent/'reports'/f'{key}.json'
            report_path.parent.mkdir(exist_ok=True)
            report={'schema':'recomp-observatory/progress-v1','targetId':target['id'],'observedAt':value['collectedAt'],
                    'overall':value['overall'],'build':{k:value['build'].get(k) for k in ('status','linkedAt','translationUnits','stale','testsRun','gameRun')},
                    'rawSpu':value.get('rawSpu'),
                    'componentSummary':value['build'].get('componentSummary'),
                    'ps3Metrics':{k:v for k,v in metrics.items() if k not in ('evidence','errors')},
                    'measurementKind':'Observed reports and static inventories; not whole-game completion'}
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=report_path.parent,suffix='.tmp',delete=False) as stream:
                json.dump(report,stream,indent=2);temp=Path(stream.name)
            temp.replace(report_path)
            return value
