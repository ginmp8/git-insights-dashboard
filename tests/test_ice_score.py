"""Frozen acceptance for the experimental Git evidence contribution index."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from gitinsights.ice_score import ICEPolicy, score_cohort, score_annual_store
from gitinsights.incremental import MetricsStore, annual_report, sync_repository


def _row(email, material, diff, supported=0, *, commits=None, prs=None, reviews=None):
    return {
        'email': email, 'author': email.split('@')[0],
        'commits': material if commits is None else commits,
        'material_commits': material, 'bounded_diff_credit': diff,
        'supported_commits': supported,
        'merged_prs': prs, 'reviews_submitted': reviews,
    }


def test_cosmetic_volume_cannot_outscore_substantive_work():
    rows = [
        _row('cosmetic@example.org', 0, 0, 0, commits=8000),
        _row('meaningful@example.org', 1000, 800, 180),
        _row('small@example.org', 200, 110, 40),
        _row('another@example.org', 300, 160, 50),
        _row('third@example.org', 450, 250, 80),
    ]
    result = score_cohort(rows)
    by_email = {x['email']: x for x in result['contributors']}
    assert by_email['cosmetic@example.org']['ice_git'] == 0
    assert by_email['meaningful@example.org']['ice_git'] >= by_email['small@example.org']['ice_git']
    assert result['methodology'] == 'ICE-Git/1'
    assert by_email['meaningful@example.org']['ice_combined'] is None
    assert by_email['small@example.org']['coverage_percent'] == 85
    assert by_email['meaningful@example.org']['components']['technical_diff'] > 0


def test_increments_saturate_and_large_commit_count_does_not_linearly_dominate():
    rows = [
        _row('a@example.org', 8000, 7000, 1000),
        _row('b@example.org', 1000, 900, 200),
        _row('c@example.org', 950, 850, 200),
        _row('d@example.org', 1100, 1000, 220),
        _row('e@example.org', 1050, 950, 210),
    ]
    out = score_cohort(rows)
    a, b = [{x['email']: x for x in out['contributors']}[e] for e in ('a@example.org','b@example.org')]
    assert a['ice_git'] <= 100
    assert a['ice_git'] - b['ice_git'] < 15  # 8x commits is not 8x credit
    assert out['references']['material_commits_p75'] >= 950


def test_collaboration_is_opt_in_and_missing_is_not_zero():
    rows = [
        _row('a@example.org', 12, 8, 3, prs=4, reviews=8),
        _row('b@example.org', 10, 7, 2, prs=1, reviews=3),
        _row('c@example.org', 8, 6, 1, prs=0, reviews=1),
        _row('d@example.org', 9, 5, 1, prs=None, reviews=None),
    ]
    no_snapshot = score_cohort(rows, collaboration_complete=False)
    assert all(c['ice_combined'] is None for c in no_snapshot['contributors'])
    done = score_cohort(rows, collaboration_complete=True)
    scores = {x['email']: x for x in done['contributors']}
    assert scores['a@example.org']['ice_combined'] is not None
    assert scores['a@example.org']['coverage_percent'] == 100
    assert scores['c@example.org']['ice_combined'] is not None  # confirmed zero is valid
    assert scores['d@example.org']['ice_combined'] is None
    assert scores['d@example.org']['coverage_percent'] == 85
    assert scores['d@example.org']['components']['collaboration'] is None


def test_inadequate_cohort_does_not_invent_a_relative_score():
    out = score_cohort([_row('a@example.org', 1, 1)], policy=ICEPolicy(min_cohort=3))
    assert out['contributors'][0]['ice_git'] is None
    assert out['status'] == 'insufficient_cohort'


def test_invalid_policies_and_invalid_signals_fail():
    with pytest.raises(ValueError):
        ICEPolicy(max_lines_per_file=0)
    with pytest.raises(ValueError):
        ICEPolicy(weight_delivery=0.8)
    with pytest.raises(ValueError):
        score_cohort([_row('a@example.org', -1, 2)])
    with pytest.raises(ValueError):
        score_cohort([_row('a@example.org', 5, 5), _row('a@example.org', 10, 10)])


def _git(repo: Path, *args: str, env=None):
    result = subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,check=True,env=env)
    return result.stdout.strip()


def _commit(repo, name, email, message):
    env={**os.environ,'GIT_AUTHOR_NAME':name,'GIT_AUTHOR_EMAIL':email,
         'GIT_COMMITTER_NAME':name,'GIT_COMMITTER_EMAIL':email,
         'GIT_AUTHOR_DATE':'2026-06-01T12:00:00+00:00',
         'GIT_COMMITTER_DATE':'2026-06-01T12:00:00+00:00'}
    _git(repo,'add','-A')
    _git(repo,'commit','-m',message,env=env)
    return _git(repo,'rev-parse','HEAD')


def test_git_diffs_file_provenance_sqlite_and_reuse(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    _git(repo,'init','-b','main')
    _git(repo,'config','user.name','Test')
    _git(repo,'config','user.email','test@example.org')
    # Three materially contributing authors and one cosmetic-only author.
    for person in ('a','b','c'):
        p=repo/f'{person}.py';p.write_text(f'def {person}():\n    return 1\n',encoding='utf-8')
        _commit(repo,person,f'{person}@example.org',f'add {person}')
    (repo/'a.py').write_text('def a():\n    return 2\n',encoding='utf-8')
    sha=_commit(repo,'a','a@example.org','change behavior')
    (repo/'package-lock.json').write_text('{"lockfileVersion":3}\n',encoding='utf-8')
    _commit(repo,'cosmetic','cosmetic@example.org','generated only')
    path=tmp_path/'cached.db'
    with MetricsStore(path) as store:
        first=sync_repository(store,'repo',repo,'refs/heads/main')
        assert first['processed'] == 5
        report=annual_report(store,[('repo','refs/heads/main')],2026)
        scored=score_annual_store(store,[('repo','refs/heads/main')],2026,report=report)
        by_email={c['email']:c for c in scored['contributors']}
        assert scored['complete'] is True
        assert by_email['cosmetic@example.org']['ice_git'] == 0
        assert by_email['a@example.org']['ice_git'] > 0
        assert by_email['a@example.org']['material_commits'] == 2
        assert any(e['sha']==sha and e['path']=='a.py' for e in by_email['a@example.org']['file_evidence'])
        assert all(e['category']!='generated' for c in scored['contributors'] for e in c['file_evidence'])
        assert store.db.execute('SELECT COUNT(*) FROM file_changes').fetchone()[0] > 0
        again=sync_repository(store,'repo',repo,'refs/heads/main')
        assert again['processed']==0 and again['reused']==5
        rerun=score_annual_store(store,[('repo','refs/heads/main')],2026)
        assert [(x['email'],x['ice_git']) for x in scored['contributors']] == [(x['email'],x['ice_git']) for x in rerun['contributors']]
    with MetricsStore(path) as reopened:
        persisted=score_annual_store(reopened,[('repo','refs/heads/main')],2026)
        assert persisted['contributors'][0]['ice_git'] is not None


def test_missing_ref_withholds_scores(tmp_path):
    with MetricsStore(tmp_path/'empty.db') as store:
        report=score_annual_store(store,[('r','refs/heads/main')],2026)
        assert report['complete'] is False
        assert report['contributors']==[]
        assert report['status']=='incomplete_history'


def test_policy_reference_json_is_machine_readable():
    content=json.loads((Path(__file__).parents[1]/'docs'/'ice-git-policy.json').read_text())
    policy=ICEPolicy(**content)
    assert policy.methodology == 'ICE-Git/1'


def test_json_cli_runs_without_streamlit_git_or_sqlite(tmp_path):
    proc=subprocess.run(['python','-m','scripts.score_ice_json',
                         '--input','docs/ice-git-example.json','--policy','docs/ice-git-policy.json'],
                        capture_output=True,text=True,cwd=Path(__file__).parents[1],check=True)
    output=json.loads(proc.stdout)
    by_email={x['email']:x for x in output['contributors']}
    assert output['methodology']=='ICE-Git/1'
    assert by_email['dev-a@example.org']['ice_git']==0
    assert by_email['dev-b@example.org']['ice_git']>0
    assert all(x['ice_combined'] is None for x in output['contributors'])
    assert all(x['coverage_percent']==85 for x in output['contributors'])


def test_one_material_author_among_cosmetic_only_still_has_nonzero_evidence():
    rows=[_row(f'zero{i}@example.org',0,0,0,commits=1000) for i in range(4)]
    rows.append(_row('unique@example.org',9,4.2,2,commits=9))
    got={r['email']:r for r in score_cohort(rows)['contributors']}
    assert got['unique@example.org']['components']['delivery']>0
    assert got['unique@example.org']['components']['technical_diff']>0
    assert all(got[f'zero{i}@example.org']['ice_git']==0 for i in range(4))


def test_commit_counts_must_be_integral():
    with pytest.raises(ValueError):
        score_cohort([_row('a@example.org',1.5,4)])


def test_score_ui_shows_components_without_demanding_network(monkeypatch):
    import importlib
    import sys
    import types
    from contextlib import nullcontext
    events=[]
    def log(name):
        def call(*args,**kwargs):
            events.append((name,args,kwargs))
        return call
    fake=types.ModuleType('streamlit')
    for name in ('dataframe','metric','download_button','markdown','caption','info','write'):
        setattr(fake,name,log(name))
    fake.selectbox=lambda name,choices,**kw:choices[0]
    fake.expander=lambda *a,**kw:nullcontext()
    fake.columns=lambda n:[types.SimpleNamespace(metric=log('col_metric')) for _ in range(n)]
    monkeypatch.setitem(sys.modules,'streamlit',fake)
    sys.modules.pop('gitinsights.ui_annual',None)
    ui=importlib.import_module('gitinsights.ui_annual')
    try:
        people=[_row(f'person{i}@example.org',100+i*5,50+i*2,10+i)
                for i in range(5)]
        scores=score_cohort(people)
        scores['year']=2026
        ui._render_ice_git(scores,'project')
        tables=[args[0] for name,args,_ in events if name=='dataframe']
        assert tables and 'ICE-Git · evidência relativa' in tables[0].columns
        assert any(name=='col_metric' and args[0]=='ICE-Git' for name,args,_ in events)
        assert any(name=='download_button' and 'evidências' in args[0] for name,args,_ in events)
    finally:
        sys.modules.pop('gitinsights.ui_annual',None)


def test_cli_does_not_overwrite_an_existing_file(tmp_path):
    existing=tmp_path/'important.json'
    existing.write_text('{"keep":true}',encoding='utf-8')
    run=subprocess.run(['python','-m','scripts.score_ice_json',
                        '--input','docs/ice-git-example.json','--out',str(existing)],
                       capture_output=True,text=True,cwd=Path(__file__).parents[1])
    assert run.returncode != 0
    assert existing.read_text()=='{"keep":true}'


def test_sqlite_adapter_optional_pr_data_requires_complete_mapped_snapshot(tmp_path):
    repo=tmp_path/'github-demo';repo.mkdir()
    _git(repo,'init','-b','main')
    _git(repo,'config','user.name','Test')
    _git(repo,'config','user.email','test@example.org')
    for dev in ('alpha','beta','gamma'):
        (repo/f'{dev}.py').write_text(f'answer_{dev} = 42\n',encoding='utf-8')
        _commit(repo,dev,f'{dev}@example.org',f'add {dev}')
    with MetricsStore(tmp_path/'metrics.db') as store:
        sync_repository(store,'r',repo,'refs/heads/main')
        for dev in ('alpha','beta','gamma'):
            store.map_github_login(f'{dev}@example.org',dev)
        prs=[{'number':i+1,'author_login':dev,'created_at':'2026-03-01T00:00:00Z',
              'merged_at':'2026-04-01T00:00:00Z','state':'MERGED',
              'url':f'https://github.com/example/repo/pull/{i+1}',
              'reviews':[{'login':'alpha','state':'APPROVED','submitted_at':'2026-04-01T00:00:00Z'}]}
             for i,dev in enumerate(('alpha','beta','gamma'))]
        store.save_pull_requests('r',prs,complete=False)
        incomplete=score_annual_store(store,[('r','refs/heads/main')],2026)
        assert all(x['ice_combined'] is None for x in incomplete['contributors'])
        store.save_pull_requests('r',prs,complete=True)
        complete=score_annual_store(store,[('r','refs/heads/main')],2026)
        assert all(x['ice_combined'] is not None for x in complete['contributors'])
        assert all(x['coverage_percent']==100 for x in complete['contributors'])
        assert {x['email']:x['merged_prs'] for x in complete['contributors']} == {
            'alpha@example.org':1,'beta@example.org':1,'gamma@example.org':1,
        }
