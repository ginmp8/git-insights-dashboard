"""Calculate ICE-Git from external, already-derived per-developer signals.

Example: python -m scripts.score_ice_json --input docs/ice-git-example.json
This does NOT read Git, inspect repositories, or verify the provenance of data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gitinsights.ice_score import ICEPolicy, score_cohort


def main() -> int:
    parser=argparse.ArgumentParser(description='ICE-Git/1 experimental evidence scoring (offline)')
    parser.add_argument('--input',type=Path,required=True,help='JSON array of per-developer signals')
    parser.add_argument('--policy',type=Path,default=None,help='Versioned policy JSON')
    parser.add_argument('--collaboration-complete',action='store_true',
                        help='Only when every selected GitHub snapshot is complete and identity-mapped')
    parser.add_argument('--out',type=Path,default=None,help='New JSON output file (never overwrites)')
    args=parser.parse_args()
    policy=ICEPolicy(**json.loads(args.policy.read_text(encoding='utf-8'))) if args.policy else ICEPolicy()
    payload=json.loads(args.input.read_text(encoding='utf-8'))
    if not isinstance(payload,list):
        parser.error('--input must contain one array of contributor objects')
    result=score_cohort(payload,policy=policy,collaboration_complete=args.collaboration_complete)
    output=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.out:
        with args.out.open('x',encoding='utf-8') as dest:
            dest.write(output)
        print(f'Resultado salvo em {args.out}')
    else:
        print(output,end='')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
