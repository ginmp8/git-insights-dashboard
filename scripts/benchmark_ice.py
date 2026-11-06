"""Reproducible synthetic ICE-Git/1 query benchmark, no external repos/network.

Run: python -m scripts.benchmark_ice --commits 50000 --authors 50 --heavy-author-commits 8000
The reference data and Git workload match scripts/benchmark_annual.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter

from scripts.benchmark_annual import create_fixture
from gitinsights.incremental import MetricsStore, sync_repository
from gitinsights.ice_score import score_annual_store


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--commits',type=int,default=50000)
    p.add_argument('--authors',type=int,default=50)
    p.add_argument('--heavy-author-commits',type=int,default=8000)
    p.add_argument('--repeat',type=int,default=3)
    args=p.parse_args()
    if not (3<=args.authors<=args.commits<=250000 and 0<=args.heavy_author_commits<args.commits and 1<=args.repeat<=10):
        p.error('Invalid workload')
    with tempfile.TemporaryDirectory(prefix='git-insights-ice-') as temp:
        root=Path(temp)
        repo=root/'git';repo.mkdir()
        create_fixture(repo,args.commits,args.authors,args.heavy_author_commits)
        db=root/'metrics.sqlite3'
        with MetricsStore(db) as store:
            before=perf_counter()
            idx=sync_repository(store,'benchmark',repo,'refs/heads/main')
            indexing=round(perf_counter()-before,3)
            times=[]
            for _ in range(args.repeat):
                start=perf_counter()
                scores=score_annual_store(store,[('benchmark','refs/heads/main')],2026)
                times.append(round(perf_counter()-start,3))
                assert len(scores['contributors'])==args.authors and scores['status']=='ok'
                assert all(x['ice_git'] is not None for x in scores['contributors'])
            cached=sync_repository(store,'benchmark',repo,'refs/heads/main')
            assert cached['processed']==0
        print(json.dumps({'commits':args.commits,'authors':args.authors,'heavy_author_commits':args.heavy_author_commits,
                          'initial_indexing_s':indexing,'score_query_s':times,
                          'cached_reprocessed':cached['processed'], 'db_size_bytes':db.stat().st_size,
                          'methodology':'ICE-Git/1','fixture':'same_git_fast_import_as_benchmark_annual'},indent=2))


if __name__=='__main__':
    main()
