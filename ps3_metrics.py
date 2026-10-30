"""Read-only PS3Recomp inventories. No target tools or binaries are executed."""
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from collector import _iso
from pathguard import is_safe_entry

_CACHE = {}
_DEF = re.compile(rb'(?m)^\s*(?:static\s+)?(?:inline\s+)?void\s+(?:[A-Za-z_][A-Za-z_0-9]*_spu_)?func_([A-Fa-f0-9]+)\s*\([^;{}]{0,200}\)\s*\{')
_TODO = re.compile(rb'/\*\s*TODO:\s*(\S+)')
_COMMENT = re.compile(rb'/\*\s*(nop|trap|dcbt|dcbtst|mtfsf)\s*[:*]')

def signature(path):
    s=path.stat();return s.st_mtime_ns,s.st_size

def scan_source(path):
    """Read a generated translation once; keep only counts, addresses and digest."""
    before=signature(path);cached=_CACHE.get(str(path))
    if cached and cached[0]==before:return cached[1]
    if before[1]>128*1024*1024:raise ValueError('Generated source exceeds the 128 MiB per-file scan limit')
    digest=hashlib.sha256();definitions=set();todos=Counter();comments=Counter();carry=b'';definition_tail=b''
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):
            digest.update(block);data=carry+block;cut=data.rfind(b'\n')
            if cut<0:
                if len(data)>2*1024*1024:raise ValueError('Source line exceeds scan limit')
                carry=data;continue
            part,carry=data[:cut+1],data[cut+1:]
            definitions.update(int(m,16) for m in _DEF.findall(definition_tail+part))
            definition_tail=part[-1024:]
            todos.update(m.decode('ascii',errors='replace') for m in _TODO.findall(part))
            comments.update(m.decode('ascii') for m in _COMMENT.findall(part))
    definitions.update(int(m,16) for m in _DEF.findall(definition_tail+carry))
    todos.update(m.decode('ascii',errors='replace') for m in _TODO.findall(carry))
    comments.update(m.decode('ascii') for m in _COMMENT.findall(carry))
    if signature(path)!=before:raise ValueError('Source changed during scan; waiting for stable input')
    result={'definitions':definitions,'todoCount':sum(todos.values()),'todoByKind':dict(todos),
            'commentOnlyByKind':dict(comments),'sha256':digest.hexdigest(),'bytes':before[1]}
    _CACHE[str(path)]=(before,result);return result

def read_json(path):
    before=signature(path)
    if before[1]>16*1024*1024:raise ValueError('Inventory exceeds 16 MiB')
    key='json:'+str(path);cached=_CACHE.get(key)
    if cached and cached[0]==before:return cached[1]
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if signature(path)!=before:raise ValueError('Inventory changed during read')
    _CACHE[key]=(before,value);return value

def entries(path):
    data=read_json(path)
    if not isinstance(data,list):raise ValueError('Expected a function-entry array')
    values=set()
    for row in data:
        if not isinstance(row,dict) or 'start' not in row:raise ValueError('Missing original function entry')
        value=int(row['start'],0) if isinstance(row['start'],str) else row['start']
        if not isinstance(value,int) or isinstance(value,bool) or value<0:raise ValueError('Invalid original function entry')
        values.add(value)
    return values

def evidence(root,path):
    stat=path.stat()
    return {'name':path.name,'path':path.relative_to(root).as_posix(),'modifiedAt':_iso(stat.st_mtime),
            'size':stat.st_size,'status':'ok','error':None}

def summarize(root,manifest):
    root=Path(root).resolve();started=time.perf_counter();errors=[];sources={};evidence_rows=[]
    def safe(path):
        if not is_safe_entry(path,root):raise ValueError('Linked input is outside the selected scan scope')
        return path
    def matched_files(parent, patterns):
        if not is_safe_entry(parent,root) or not parent.is_dir():return []
        return sorted(path for pattern in patterns for path in parent.glob(pattern)
                      if is_safe_entry(path,root) and path.is_file())
    ppu_files=matched_files(root/'project/recompiled',('ppu_recomp_*.cpp',))
    spu_files=matched_files(root/'project/spu',('*_recomp.c','*_recomp.cpp'))
    if len(ppu_files)+len(spu_files)>1000:raise ValueError('Generated inventory exceeds 1,000 files')
    for path in ppu_files+spu_files:
        try:sources[path.relative_to(root).as_posix()]=scan_source(safe(path))
        except (OSError,ValueError) as error:errors.append({'path':path.relative_to(root).as_posix(),'message':str(error)})
    generated=set();todo=Counter();comments=Counter()
    for path in ppu_files:
        data=sources.get(path.relative_to(root).as_posix())
        if data:generated.update(data['definitions']);todo.update(data['todoByKind']);comments.update(data['commentOnlyByKind'])
    original=None;original_path=root/'analysis/EBOOT.functions.json'
    try:original=entries(safe(original_path));evidence_rows.append(evidence(root,original_path))
    except (OSError,ValueError,TypeError) as error:errors.append({'path':'analysis/EBOOT.functions.json','message':str(error)})
    ppu_complete=bool(ppu_files) and all(p.relative_to(root).as_posix() in sources for p in ppu_files)
    matched=len(original&generated) if original is not None and ppu_complete else None
    ppu={'generatedFunctions':len(generated) if ppu_complete else None,'originalEntries':len(original) if original is not None else None,
         'matchedEntries':matched,'mappingPercent':matched/len(original)*100 if original and matched is not None else None,
         'missingEntries':len(original-generated) if original is not None and ppu_complete else None,
         'extraDefinitions':len(generated-original) if original is not None and ppu_complete else None,
         'generatedFiles':len(ppu_files),'todoCount':sum(todo.values()) if ppu_complete else None,
         'todoByKind':dict(todo),'commentOnlyByKind':dict(comments),'scanComplete':ppu_complete}
    programs=[];total_original=total_matched=0;all_mapped=True
    for path in spu_files:
        name=path.stem.removesuffix('_recomp');data=sources.get(path.relative_to(root).as_posix());inventory=root/'analysis/spu'/f'{name}.functions.json'
        row={'name':name,'generatedFunctions':len(data['definitions']) if data else None,'originalEntries':None,'matchedEntries':None,'mappingPercent':None,'todoCount':data['todoCount'] if data else None,'inventoryAvailable':False}
        try:
            orig=entries(safe(inventory));evidence_rows.append(evidence(root,inventory));row['inventoryAvailable']=True
            if data:
                row.update(originalEntries=len(orig),matchedEntries=len(orig&data['definitions']),mappingPercent=len(orig&data['definitions'])/len(orig)*100 if orig else None)
                total_original+=len(orig);total_matched+=len(orig&data['definitions'])
            else:all_mapped=False
        except (OSError,ValueError,TypeError):all_mapped=False
        programs.append(row)
    # Count only name-matched inventories, never imply all possible SPU jobs were discovered.
    spu={'programs':programs,'generatedPrograms':len(spu_files),'generatedFunctions':sum(r['generatedFunctions'] for r in programs) if programs and all(r['generatedFunctions'] is not None for r in programs) else None,
         'programsWithInventories':sum(r['inventoryAvailable'] for r in programs),'mappedSubsetEntries':total_original,
         'mappedSubsetMatches':total_matched,'mappingPercent':total_matched/total_original*100 if programs and all_mapped and total_original else None}
    checked=0;changed=[];unavailable=[];excluded=0
    recorded=manifest.get('source_sha256',{})
    if not isinstance(recorded,dict):recorded={}
    for filename,expected in recorded.items():
        path=Path(filename);path=(root/path).resolve() if not path.is_absolute() else path.resolve()
        try:relative=path.relative_to(root).as_posix()
        except ValueError:excluded+=1;continue
        if not relative.startswith('project/') or path.suffix.lower() not in {'.cpp','.c','.h','.hpp','.ps1','.cmake','.txt'}:excluded+=1;continue
        try:
            data=sources.get(relative)
            if data:digest=data['sha256']
            else:
                safe(path);before=signature(path)
                if before[1]>16*1024*1024:excluded+=1;continue
                key='hash:'+str(path);cache=_CACHE.get(key)
                if cache and cache[0]==before:digest=cache[1]
                else:
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    if signature(path)!=before:raise ValueError('Source changed during identity check')
                    _CACHE[key]=(before,digest)
            checked+=1
            if digest.lower()!=str(expected).lower():changed.append(relative)
        except (OSError,ValueError) as error:unavailable.append(relative)
    freshness={'checkedFiles':checked,'changedFiles':changed,'unavailableFiles':unavailable,'excludedFiles':excluded,
               'stale':True if changed else None if unavailable or not checked else False,
               'basis':'Hashes of recorded project source inputs within the bounded reader scope. Original game binaries, saves, SDK inputs outside the target and oversized unscanned sources are excluded.'}
    audit_path=root/'analysis/ppu-coverage.json';audit={}
    try:
        prior=read_json(safe(audit_path));evidence_rows.append(evidence(root,audit_path))
        audit={'recordedAt':_iso(audit_path.stat().st_mtime),'functions':prior.get('lifted_function_count'),'todos':prior.get('todo_count'),
               'newerGeneratedFiles':sum(p.stat().st_mtime>audit_path.stat().st_mtime for p in ppu_files),'scope':'Historical audit; fresh scan above does not rewrite it.'}
    except (OSError,ValueError):pass
    return {'schemaVersion':1,'observedAt':_iso(time.time()),'ppu':ppu,'spu':spu,'freshness':freshness,'historicalAudit':audit,
            'evidence':evidence_rows,'errors':errors,'scanMs':round((time.perf_counter()-started)*1000,2),
            'sourceBytesScanned':sum(d['bytes'] for d in sources.values()),
            'basis':'Original function entry addresses matched to generated function definitions. Mapping is not supported-instruction coverage, semantic equivalence or whole-game completion.'}
