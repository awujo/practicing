"""Finalize saved research in short self-dispatched slices; never replay completed studies."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import zipfile

from .research import encoded
from .research_scenarios import aggregate
from .research_publish import publish, PublicationBudgetExceeded

MAX_SLICES=200
TASK=re.compile(r'([A-Z]{6})/window-\d{2}/(?:native|scenarios)/ledger\.sqlite\Z')


def unpack(root):
    root=Path(root).resolve()
    for p in root.rglob('*.zip'):
        with zipfile.ZipFile(p) as z:
            if sum(i.file_size for i in z.infolist())>160*1024**2:raise ValueError('expanded pair archive too large')
            for i in z.infolist():
                if not (root/i.filename).resolve().is_relative_to(root):raise ValueError('unsafe archive')
            z.extractall(root)


def save(state,path):
    path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_bytes(encoded(state));tmp.replace(path)


def validate(state,source):
    if state['source_run']!=str(source) or not str(source).isdigit():raise ValueError('source mismatch')
    tasks=state['tasks'];cursor=state['cursor']
    if not tasks or len(tasks)>560 or len(set(tasks))!=len(tasks) or any(not TASK.fullmatch(p) for p in tasks):raise ValueError('invalid task plan')
    if not 0<=cursor<=len(tasks) or not 0<=state['slices']<=MAX_SLICES:raise ValueError('invalid cursor/budget')


def plan(root,source,state_path='finalize-state.json',expected_pairs=None):
    root=Path(root);path=Path(state_path)
    if path.exists():
        state=json.loads(path.read_text());validate(state,source)
    else:
        unpack(root)
        reports=[json.loads(p.read_text()) for p in sorted(root.rglob('history-report.json'))]
        from .backtest import PAIRS
        actual=[r['pair'] for r in reports]
        # This recovery is for the complete 28-pair run; don't mistake partial download for completion.
        expected=expected_pairs or PAIRS
        if len(set(expected))!=len(expected) or not set(expected)<=set(PAIRS):raise ValueError('invalid expected pairs')
        if set(actual)!=set(expected) or len(actual)!=len(expected) or any(r['status']!='complete' for r in reports):
            raise ValueError('source is not a complete 28-pair study')
        tasks=sorted(str(p.relative_to(root)) for p in root.rglob('ledger.sqlite'))
        required=sorted(f"{r['pair']}/window-{i:02d}/{kind}/ledger.sqlite" for r in reports for i in range(r['planned_windows']) for kind in ('native','scenarios'))
        if tasks!=required:raise ValueError('missing or unexpected source ledger files')
        state={'source_run':str(source),'tasks':tasks,'cursor':0,'slices':0,'consecutive_errors':0,'status':'pending',
               'expected_pairs':list(expected),'analysis_status':'complete','completed_ledgers':0,'errors':[]}
        validate(state,source);save(state,path)
        summary={'source_run':str(source),'analysis_status':'complete','pairs':reports,'analysis':aggregate(root),
                 'publication_status':'separate resumable workflow; analysis survives publication failures'}
        Path('history-summary.json').write_bytes(encoded(summary))
    pair=state['tasks'][state['cursor']].split('/')[0] if state['cursor']<len(state['tasks']) else ''
    return state,pair


def advance(root,source,state_path='finalize-state.json',seconds=420,limit=4,publisher=publish):
    if not 1<=limit<=4 or not 1<=seconds<=420:raise ValueError('slice budget outside bounds')
    path=Path(state_path);state=json.loads(path.read_text());validate(state,source)
    if state['slices']>=MAX_SLICES or state['status'] in ('complete','storage_blocked','failed'):return state
    state['slices']+=1;save(state,path)
    deadline=time.monotonic()+seconds;count=0
    while state['cursor']<len(state['tasks']) and count<limit and time.monotonic()<deadline:
        task=state['tasks'][state['cursor']];local=Path(root)/task
        # Only one pair's archive is needed in each continuation run.
        if not local.exists():break
        try:
            n=publisher(local,max_total_bytes=128*1024**2,deadline=deadline)
            state['cursor']+=1;state['completed_ledgers']=state['cursor'];state['consecutive_errors']=0;count+=1
            print(f"Saved {task}: {n} records; {state['cursor']}/{len(state['tasks'])} ledgers",flush=True)
            state['status']='pending';save(state,path)
        except PublicationBudgetExceeded:
            state['status']='storage_blocked';state['errors'].append({'task':task,'reason':'128 MiB research payload cap'})
            save(state,path);break
        except TimeoutError:
            state['status']='pending';save(state,path);break
        except Exception as exc:
            state['consecutive_errors']+=1
            state['errors'].append({'task':task,'error_type':type(exc).__name__})
            state['status']='failed' if state['consecutive_errors']>=2 else 'pending'
            save(state,path);break
    if state['cursor']==len(state['tasks']):state['status']='complete'
    elif state['slices']>=MAX_SLICES:state['status']='failed'
    save(state,path)
    return state


def outputs(values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            for k,v in values.items():f.write(str(k)+'='+str(v)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['plan','advance'])
    p.add_argument('--input',default='history-results');p.add_argument('--source',required=True)
    p.add_argument('--expected-pairs',default='[]')
    a=p.parse_args()
    if a.mode=='plan':
        state,pair=plan(a.input,a.source,expected_pairs=json.loads(a.expected_pairs) or None);outputs({'pair':pair,'source':a.source})
    else:
        unpack(a.input);state=advance(a.input,a.source)
        outputs({'more':'true' if state['status']=='pending' else 'false'})
        summary=f"Analysis complete. Database ledgers: {state['cursor']}/{len(state['tasks'])}. Status: {state['status']}. Slice: {state['slices']}."
        print(summary,flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(summary+'\n')
        if state['status'] in ('storage_blocked','failed'):raise SystemExit('Finalization stopped: '+state['status'])
