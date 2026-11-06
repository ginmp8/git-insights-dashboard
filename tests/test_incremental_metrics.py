"""Acceptance: full-coverage, resumable annual engineering indicators, not sampled scores."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess

import pytest

from gitinsights.git_engine import GitError
from gitinsights.incremental import MetricsStore, sync_repository, annual_report, choose_integration_ref


def git(repo: Path, *args: str, env: dict | None = None):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, env=env, check=True)
    return p.stdout.strip()


def commit(repo: Path, message: str, name: str = 'Alice', email: str = 'alice@example.com'):
    env = {**os.environ, 'GIT_AUTHOR_NAME': name, 'GIT_AUTHOR_EMAIL': email,
           'GIT_COMMITTER_NAME': name, 'GIT_COMMITTER_EMAIL': email,
           'GIT_AUTHOR_DATE': '2026-06-01T12:00:00+00:00',
           'GIT_COMMITTER_DATE': '2026-06-01T12:00:00+00:00'}
    git(repo, 'add', '-A')
    git(repo, 'commit', '-m', message, env=env)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / 'source'
    r.mkdir()
    git(r, 'init', '-b', 'main')
    git(r, 'config', 'user.name', 'Test')
    git(r, 'config', 'user.email', 'test@example.com')
    (r / 'old').mkdir()
    (r / 'old' / 'code.py').write_text('amount = 1\nprint(amount)\n', encoding='utf-8')
    commit(r, 'initial')
    git(r, 'branch', 'unmerged')
    (r / 'new').mkdir()
    git(r, 'mv', 'old/code.py', 'new/code.py')
    commit(r, 'move only', 'Bob', 'bob@example.com')
    (r / 'new' / 'code.py').write_text('amount  =  1\nprint( amount )\n', encoding='utf-8')
    commit(r, 'spaces only')
    (r / 'new' / 'code.py').write_text('amount  =  1\nprint( amount )\nprint("done")\n', encoding='utf-8')
    commit(r, 'change behavior', 'Bob', 'bob@example.com')
    git(r, 'checkout', 'unmerged')
    (r / 'orphan.py').write_text('x = 1\n', encoding='utf-8')
    commit(r, 'side branch not merged')
    git(r, 'checkout', 'main')
    return r


def test_full_history_is_not_sampled_and_incremental(tmp_path, repo):
    store = MetricsStore(tmp_path / 'analytics.sqlite3')
    first = sync_repository(store, 'repo-1', repo, 'refs/heads/main', batch_size=2)
    assert first['eligible'] == 4
    assert first['processed'] == 4
    assert first['reused'] == 0
    assert first['complete'] is True
    annual = annual_report(store, [('repo-1', 'refs/heads/main')], 2026)
    assert annual['eligible_commits'] == 4
    assert annual['processed_commits'] == 4
    assert annual['coverage_percent'] == 100
    assert sum(x['commits'] for x in annual['contributors']) == 4
    assert sum(x['pure_moves'] for x in annual['contributors']) == 1
    assert annual['totals']['gross_churn'] > annual['totals']['adjusted_churn']
    assert annual['totals']['substantive_commits'] < annual['eligible_commits']
    again = sync_repository(store, 'repo-1', repo, 'refs/heads/main', batch_size=2)
    assert again['processed'] == 0
    assert again['reused'] == 4
    assert again['complete'] is True
    store.close()
    reopened = MetricsStore(tmp_path / 'analytics.sqlite3')
    persisted = annual_report(reopened, [('repo-1', 'refs/heads/main')], 2026)
    assert persisted['totals'] == annual['totals']
    reopened.close()


def test_incremental_and_branch_ref_rewrite(tmp_path, repo):
    with MetricsStore(tmp_path / 'data.db') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)
        (repo / 'tests').mkdir()
        (repo / 'tests' / 'test_logic.py').write_text('def test_ok():\n    assert True\n')
        commit(repo, 'add test', 'Bob', 'bob@example.com')
        updated = sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)
        assert updated['processed'] == 1 and updated['reused'] == 4
        report = annual_report(store, [('r', 'refs/heads/main')], 2026)
        assert report['eligible_commits'] == 5
        assert report['totals']['test_files_touched'] >= 1
        git(repo, 'reset', '--hard', 'HEAD~1')
        reset = sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)
        assert reset['eligible'] == 4 and reset['processed'] == 0
        assert annual_report(store, [('r', 'refs/heads/main')], 2026)['eligible_commits'] == 4
        # Reused SHA still exists in DB; only membership is removed.
        assert store.db.execute('SELECT COUNT(*) FROM commits WHERE repo_id=?', ('r',)).fetchone()[0] == 5


def test_failed_batch_preserves_prior_snapshot(tmp_path, repo, monkeypatch):
    import gitinsights.incremental as mod
    with MetricsStore(tmp_path / 'data.db') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)
        (repo / 'other.py').write_text('new = 1\n')
        commit(repo, 'new')
        orig = mod._fetch_batch
        def fail(*args, **kwargs):
            raise GitError('controlled failure')
        monkeypatch.setattr(mod, '_fetch_batch', fail)
        with pytest.raises(GitError):
            sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)
        # No partially updated membership / no inaccurate annual coverage.
        assert annual_report(store, [('r', 'refs/heads/main')], 2026)['eligible_commits'] == 4
        monkeypatch.setattr(mod, '_fetch_batch', orig)
        assert sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=2)['processed'] == 1


def test_pr_collaboration_metrics_explicit_identity_mapping(tmp_path, repo):
    with MetricsStore(tmp_path / 'data.db') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main')
        store.save_pull_requests('r', [
            {'number': 12, 'author_login': 'alice', 'created_at': '2026-06-01T00:00:00Z',
             'merged_at': '2026-07-01T00:00:00Z', 'state': 'MERGED', 'url': 'https://github.com/a/b/pull/12',
             'reviews': [{'login': 'bob', 'state': 'APPROVED', 'submitted_at': '2026-06-30T00:00:00Z'}]},
            {'number': 13, 'author_login': 'bob', 'created_at': '2026-06-01T00:00:00Z',
             'merged_at': None, 'state': 'OPEN', 'url': 'https://github.com/a/b/pull/13',
             'reviews': []},
        ])
        without = annual_report(store, [('r', 'refs/heads/main')], 2026)
        assert all(row['merged_prs'] is None for row in without['contributors'])
        store.map_github_login('alice@example.com', 'alice')
        store.map_github_login('bob@example.com', 'bob')
        with_links = annual_report(store, [('r', 'refs/heads/main')], 2026)
        alice = next(r for r in with_links['contributors'] if r['email'] == 'alice@example.com')
        bob = next(r for r in with_links['contributors'] if r['email'] == 'bob@example.com')
        assert alice['merged_prs'] == 1
        assert bob['reviews_submitted'] == 1
        assert bob['reviews_approved'] == 1
        assert bob['merged_prs'] == 0


def test_invalid_repo_paths_and_refs_fail_closed(tmp_path):
    with MetricsStore(tmp_path / 'test.db') as store:
        with pytest.raises(GitError):
            sync_repository(store, 'r', tmp_path / 'not-a-repo', 'refs/heads/main')
        with pytest.raises(ValueError):
            annual_report(store, [('r', 'refs/heads/main')], 1500)
        with pytest.raises(ValueError):
            store.map_github_login('not-an-email', 'test')
        with pytest.raises(ValueError):
            store.map_github_login('a@b.com', 'bad;name')


def test_default_ref_prefers_integrated_main(repo):
    assert choose_integration_ref(repo) == 'refs/heads/main'


def test_alias_merges_authors_without_reindexing(tmp_path, repo):
    with MetricsStore(tmp_path / 'data.db') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main')
        store.set_author_alias('bob@example.com', 'alice@example.com')
        report = annual_report(store, [('r','refs/heads/main')], 2026)
        assert len(report['contributors']) == 1
        assert report['contributors'][0]['commits'] == 4
        assert set(report['contributors'][0]['aliases']) == {'alice@example.com','bob@example.com'}
        assert store.db.execute('SELECT COUNT(*) FROM commits').fetchone()[0] == 4


def test_generated_changes_are_separate_and_cache_supports_unusual_names(tmp_path, repo):
    with MetricsStore(tmp_path / 'db.sqlite3') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main')
        (repo / 'package-lock.json').write_text('{"lockfileVersion": 3}\n', encoding='utf-8')
        (repo / 'strange\nfile.txt').write_text('new text\n', encoding='utf-8')
        commit(repo, 'add unusual path and lock file')
        outcome = sync_repository(store, 'r', repo, 'refs/heads/main', batch_size=1)
        assert outcome['processed'] == 1
        report = annual_report(store, [('r','refs/heads/main')], 2026)
        assert report['totals']['generated_churn'] > 0
        assert report['totals']['reviewable_churn'] <= report['totals']['adjusted_churn']


def test_partial_pr_snapshot_does_not_claim_complete_data(tmp_path, repo):
    with MetricsStore(tmp_path / 'db.sqlite3') as store:
        sync_repository(store, 'r', repo, 'refs/heads/main')
        store.map_github_login('alice@example.com', 'alice')
        store.save_pull_requests('r', [{'number':1,'author_login':'alice',
                                      'url':'https://github.com/a/b/pull/1',
                                      'created_at':'2026-01-01T00:00:00Z',
                                      'merged_at':'2026-01-02T00:00:00Z','state':'MERGED'}],complete=False)
        report = annual_report(store, [('r','refs/heads/main')], 2026)
        assert report['pr_metadata_complete'] is False
        assert all(row['merged_prs'] is None for row in report['contributors'])


def test_mailmap_changes_refresh_cached_author_identity(tmp_path, repo):
    with MetricsStore(tmp_path / 'metrics.db') as store:
        first=sync_repository(store,'r',repo,'refs/heads/main')
        assert first['processed']==4
        (repo/'.mailmap').write_text('Alice <canonical@example.com> <alice@example.com>\n',encoding='utf-8')
        commit(repo, 'mailmap identity update')
        second=sync_repository(store,'r',repo,'refs/heads/main')
        assert second['processed']==1  # old commit diffs remain cached
        result=annual_report(store,[('r','refs/heads/main')],2026)
        assert any(x['email']=='canonical@example.com' for x in result['contributors'])
        assert not any(x['email']=='alice@example.com' for x in result['contributors'])
        assert sum(x['commits'] for x in result['contributors'])==5
