"""Whitelisted report readers. Never execute or serve repository code."""
import json
import time
from itertools import islice
from pathlib import Path
from collector import collect_snapshot, _iso, _integer, _overall_progress
from pathguard import is_safe_entry

def read_evidence(root, relative):
    path = (root / relative).resolve()
    row = {'name': Path(relative).name, 'path': relative, 'modifiedAt': None, 'size': None, 'status': 'unavailable', 'error': None}
    try:
        if not path.is_relative_to(root): raise ValueError('Report is outside target folder')
        stat = path.stat()
        row.update(modifiedAt=_iso(stat.st_mtime), size=stat.st_size)
        if stat.st_size > 16*1024*1024: raise ValueError('Report exceeds 16 MiB')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        after = path.stat()
        if (after.st_mtime_ns, after.st_size) != (stat.st_mtime_ns, stat.st_size): raise ValueError('Report changed while reading')
        if not isinstance(value, dict): raise ValueError('Report must be an object')
        row['status'] = 'ok'
        return value, row
    except (OSError, ValueError) as error:
        row['error'] = str(error)
        return {}, row

def collect_target(target):
    started = time.perf_counter()
    root = Path(target['root']).resolve()
    d = collect_snapshot(root, empty=target['adapter'] != 'independent-reports-v1')
    d['project'].update(title=target['gameTitle'], mode=target['title'], testingPolicy='Use this target\'s recorded testing policy and evidence.')
    if target['adapter'] == 'independent-reports-v1':
        d['capabilities'] = {'translation': True, 'runtime': 'independent', 'description': 'Independent report format: selected PPU/SPU word coverage and compile receipts.'}
        return d
    # Different formats must not inherit any independent-reader measurements.
    d.update(sourceRoot=str(root), errors=[], evidence=[], activity=[])
    d['project'].update(title=target['gameTitle'], mode=target['title'], testingPolicy='No runtime actions are performed by this observer.')
    d['capabilities'] = {'translation': False, 'runtime': 'recorded', 'description': 'This reader has no supported translation denominator; coverage stays unknown.'}
    d['recordedRuntime'] = None
    if not root.is_dir():
        d['errors'].append({'path': '.', 'message': 'Target folder is unavailable'})
    if target['adapter'] == 'ps3recomp-manifest-v1':
        reports = target.get('reports', {})
        build_path = reports.get('build')
        if not build_path:
            startup = root / 'analysis/startup'
            candidates = []
            if is_safe_entry(startup, root) and startup.is_dir():
                candidates = [path for path in islice(startup.iterdir(), 1000)
                              if path.name.startswith('build-') and path.suffix == '.json'
                              and is_safe_entry(path, root) and path.is_file()]
                candidates = sorted(candidates, key=lambda p:p.stat().st_mtime, reverse=True)[:50]
            # Recognize a narrowly supported manifest schema; filenames alone never prove a link.
            for candidate in candidates:
                candidate_value, _ = read_evidence(root, candidate.relative_to(root).as_posix())
                if candidate_value.get('status') == 'production_build_succeeded_native_pending' and isinstance(candidate_value.get('compile_proof'), dict):
                    build_path = candidate.relative_to(root).as_posix(); break
        build_report = {}
        if build_path:
            build_report, row = read_evidence(root, build_path); d['evidence'].append(row)
            success = build_report.get('status') == 'production_build_succeeded_native_pending'
            proof = build_report.get('compile_proof', {})
            object_targets = proof.get('object_targets') if isinstance(proof, dict) else None
            d['build'].update(available=success, status=build_report.get('status'), linkedAt=build_report.get('created_utc') or row['modifiedAt'],
                              translationUnits=len(object_targets) if isinstance(object_targets, list) else _integer(object_targets),
                              elapsedSeconds=build_report.get('build_seconds'), reportPath=build_path,
                              stale=None, gameRun=None, testsRun=None, gameComplete=None,
                              remaining=['Translation coverage denominator unavailable', 'Current source/build identity not checked by this reader', 'Review recorded runtime evidence in its original scope'])
        performance_path = reports.get('performance')
        if performance_path:
            measurement, row = read_evidence(root, performance_path); d['evidence'].append(row)
            same_build = bool(build_report.get('executable_sha256')) and measurement.get('executable_sha256') == build_report.get('executable_sha256')
            fps = measurement.get('gameplay_fps')
            if same_build and str(measurement.get('status', '')).startswith('ADMITTED_') and isinstance(fps, (int,float)) and not isinstance(fps,bool) and 0 < fps < 100000:
                d['recordedRuntime'] = {'fps': fps, 'frames': _integer(measurement.get('frames')), 'recordedAt': measurement.get('created_utc'),
                                        'scope': 'Historical stationary-scene sample for the pinned executable; current performance is unverified.', 'reportPath': performance_path}
                d['build']['gameRun'] = True
        from ps3_metrics import summarize
        metrics=summarize(root,build_report)
        metrics['milestones']=[
            {'name':'Windows executable','state':'Link recorded' if d['build']['available'] else 'Unverified'},
            {'name':'Native execution','state':'Historical run recorded' if d['build']['gameRun'] else 'Unverified'},
            {'name':'Rendered-scene performance','state':f"{d['recordedRuntime']['fps']:.2f} FPS · stationary historical sample" if d['recordedRuntime'] else 'Unverified'},
            {'name':'Opening audio / synchronization','state':'Not established by these reports'},
            {'name':'Movement / input fidelity','state':'Not established by a stationary sample'},
            {'name':'30 FPS gameplay','state':'Not established'},
        ]
        d['ps3Metrics']=metrics
        d['evidence'].extend(metrics['evidence'])
        d['errors'].extend(metrics['errors'])
        fresh=metrics['freshness']
        d['build'].update(stale=fresh['stale'],recordedSourcesChecked=fresh['checkedFiles'],
                          changedRecordedSources=fresh['changedFiles'],freshnessBasis=fresh['basis'])
        d['build']['remaining']=['Instruction semantics and runtime integration require separate evidence', 'SPU inventory is partial', 'Whole-game completion is unmeasured']
        audit_path=root/'analysis/import-services/current-registration-audit.json'
        if is_safe_entry(audit_path, root) and audit_path.is_file():
            audit,row=read_evidence(root,'analysis/import-services/current-registration-audit.json');d['evidence'].append(row)
            providers=audit.get('available_providers',{})
            unresolved=audit.get('unresolved_imports')
            run=audit.get('run_record',{})
            same=bool(build_report.get('executable_sha256')) and run.get('executable_sha256','').lower()==build_report.get('executable_sha256','').lower()
            metrics['imports']={'total':_integer(audit.get('count')),'providers':{k:_integer(providers.get(k)) for k in ('hle','native_prx','unresolved')},
                                'recordedAt':row['modifiedAt'],'matchesSelectedBuild':same,'unresolvedCount':len(unresolved) if isinstance(unresolved,list) else None}
            if same and isinstance(unresolved,list):
                d['imports'].update(available=True,unresolvedCount=len(unresolved),unresolved=[{'importer':'original game','library':r.get('library'),'kind':'function','nid':r.get('nid'),'reason':'No provider in recorded audit'} for r in unresolved],boundFunctions=None,boundVariables=None)
        d['capabilities']['description']='Fresh read-only PPU/SPU function-entry inventory, scoped build hashes and historical service/runtime audits. Instruction-emission coverage remains unmeasured.'
        d['errors'] += [{'path': r['path'], 'message': r['error']} for r in d['evidence'] if r['status'] != 'ok']
    # Metadata activity only: do not read source/generated payloads.
    rows = []
    for directory in ('src', 'tools', 'docs', 'reports', 'analysis/startup'):
        parent = root / directory
        if not is_safe_entry(parent, root) or not parent.is_dir(): continue
        for path in islice(parent.iterdir(), 1000):
            if is_safe_entry(path, root) and path.is_file() and path.suffix in {'.cpp','.hpp','.py','.md','.json'}:
                s=path.stat(); rows.append({'path': path.relative_to(root).as_posix(), 'category': directory, 'modifiedAt':_iso(s.st_mtime), 'size':s.st_size})
    d['activity'] = sorted(rows,key=lambda r:r['modifiedAt'],reverse=True)[:40]
    d['overall'] = _overall_progress(d['ppu'], d['spu'])
    d['collectionMs'] = round((time.perf_counter()-started)*1000,3)
    return d
