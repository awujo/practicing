"""Run a declared local feed: python -m bishop.v2.backtest --help."""
import argparse
import json
from pathlib import Path
from .engine import run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed',required=True)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--as-of',required=True)
    parser.add_argument('--history-start')
    parser.add_argument('--scan-start')
    parser.add_argument('--policy',help='JSON policy file; omitted uses source-confirmation defaults')
    parser.add_argument('--costs',required=True,help='JSON cost file; explicit costs including zero hypothesis')
    parser.add_argument('--max-open-orders',type=int,default=10)
    parser.add_argument('--management-actions',help='JSON list of explicitly timed paper management actions')
    parser.add_argument('--diagnostics',action='store_true')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=run(args.feed,args.manifest,as_of=args.as_of,history_start=args.history_start,scan_start=args.scan_start,
               policy=json.loads(Path(args.policy).read_text()) if args.policy else None,
               costs=json.loads(Path(args.costs).read_text()),max_open_orders=args.max_open_orders,
               include_diagnostics=args.diagnostics,
               management_actions=json.loads(Path(args.management_actions).read_text()) if args.management_actions else ())
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(target),'status':result['status'],'summary':result['summary']}))


if __name__=='__main__': main()
