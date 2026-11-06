"""Synthetic performance/coverage oracle for the local incremental annual index.

Creates a throwaway Git repo and SQLite database; no network or user repos.
Usage: python scripts/benchmark_annual.py --commits 10000 --authors 50
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gitinsights.incremental import MetricsStore, annual_report, sync_repository


def create_fixture(repo: Path, commits: int, authors: int, heavy_author_commits: int = 0):
    subprocess.run(['git','init','-q','-b','main',str(repo)],check=True,capture_output=True)
    with subprocess.Popen(['git','-C',str(repo),'fast-import','--quiet'],stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL,stderr=subprocess.PIPE) as git:
        assert git.stdin
        for i in range(commits):
            who = 0 if i < heavy_author_commits else (1 + (i-heavy_author_commits) % (authors-1) if heavy_author_commits else i % authors)
            timestamp=1767225600+i  # 2026-01-01 onward
            name=f'Dev {who} <dev{who}@example.test> {timestamp} +0000'.encode()
            message=f'commit {i}'.encode()
            blob=f'value = {i}\nprint(value)\n'.encode()
            record=(b'commit refs/heads/main\n'
                    +b'author '+name+b'\n'
                    +b'committer '+name+b'\n'
                    +b'data '+str(len(message)).encode()+b'\n'+message+b'\n'
                    +b'M 100644 inline src/work.py\n'
                    +b'data '+str(len(blob)).encode()+b'\n'+blob+b'\n')
            git.stdin.write(record)
        git.stdin.close()
        rc=git.wait()
        if rc:
            raise RuntimeError('git fast-import failed')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--commits',type=int,default=10000)
    p.add_argument('--authors',type=int,default=50)
    p.add_argument('--batch-size',type=int,default=400)
    p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--heavy-author-commits',type=int,default=0)
    opts=p.parse_args()
    if not (1<=opts.authors<=opts.commits<=250000) or not 1<=opts.repeat<=10 or not 0<=opts.heavy_author_commits<opts.commits or (opts.heavy_author_commits and opts.authors<2):
        p.error('Invalid workload')
    with tempfile.TemporaryDirectory(prefix='git-insights-benchmark-') as temp:
        root=Path(temp)
        repo=root/'git'
        repo.mkdir()
        create_fixture(repo,opts.commits,opts.authors,opts.heavy_author_commits)
        db=root/'metrics.sqlite3'
        runs=[]
        with MetricsStore(db) as store:
            for i in range(opts.repeat):
                start=perf_counter()
                status=sync_repository(store,'benchmark',repo,'refs/heads/main',batch_size=opts.batch_size)
                seconds=round(perf_counter()-start,3)
                report=annual_report(store,[('benchmark','refs/heads/main')],2026)
                if report['eligible_commits']!=opts.commits or len(report['contributors'])!=opts.authors:
                    raise RuntimeError('Coverage/authorship expectation failed')
                if i>0 and status['processed']!=0:
                    raise RuntimeError('Cached commits were reprocessed')
                runs.append({'seconds':seconds,'processed':status['processed'],
                             'reused':status['reused']})
        print(json.dumps({'commits':opts.commits,'authors':opts.authors,
                          'heavy_author_commits':opts.heavy_author_commits,'runs':runs,'db_size_bytes':db.stat().st_size,
                          'git_version':subprocess.run(['git','--version'],capture_output=True,
                                                       text=True).stdout.strip(),
                          'measured_at':datetime.now(timezone.utc).isoformat()},indent=2))


if __name__=='__main__':
    main()
