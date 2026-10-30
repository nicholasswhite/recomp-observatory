"""Export the standard observer report without modifying a target repository."""
import argparse
import json
from pathlib import Path
from workspace import Workspace, identity
from adapters import collect_target
import tempfile

def main():
    base=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=base/'work/workspace.json')
    parser.add_argument('--target',required=True)
    args=parser.parse_args()
    workspace=Workspace(args.workspace,base/'work/history')
    target=next(t for t in workspace.targets if t['id']==args.target)
    value=collect_target(target);metrics=value.get('ps3Metrics',{})
    report={'schema':'recomp-observatory/progress-v1','targetId':target['id'],'observedAt':value['collectedAt'],
            'overall':value['overall'],'build':{k:value['build'].get(k) for k in ('status','linkedAt','translationUnits','stale','testsRun','gameRun')},
            'ps3Metrics':{k:v for k,v in metrics.items() if k not in ('evidence','errors')},
            'measurementKind':'Observed reports and static inventories; not whole-game completion'}
    output=base/'work/reports'/f'{identity(target)}.json';output.parent.mkdir(exist_ok=True,parents=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=output.parent,suffix='.tmp',delete=False) as stream:
        json.dump(report,stream,indent=2);temp=Path(stream.name)
    temp.replace(output);print(output)

if __name__=='__main__':main()
