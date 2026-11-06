"""Frozen acceptance: multi-ref scope, metrics, filtering, safety and persistence."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from gitinsights.analytics import build_metrics, filter_commits, recent_activity, snapshot
from gitinsights.catalog import Catalog, CatalogError, validate_remote_url
from gitinsights.git_engine import GitError, get_branches, get_commits, get_repo_summary, git_is_repo, compare_branches
from gitinsights.github import parse_github_repo


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    e = os.environ.copy()
    if env:
        e.update(env)
    result = subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True, env=e)
    return result.stdout.strip()


@pytest.fixture
def sample_repo(tmp_path):
    repo = tmp_path / 'my repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'Alice')
    git(repo, 'config', 'user.email', 'alice@example.test')
    (repo / 'src').mkdir()
    (repo / 'src' / 'app.py').write_text('a\nb\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'initial', env={
        'GIT_AUTHOR_DATE': '2025-01-01T10:00:00+00:00',
        'GIT_COMMITTER_DATE': '2025-01-01T10:00:00+00:00',
    })
    git(repo, 'branch', 'feature')
    (repo / 'src' / 'app.py').write_text('a\nb\nc\n')
    (repo / 'README.md').write_text('# Example\n')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Bob', '-c', 'user.email=bob@example.test', 'commit', '-m', 'main work', env={
        'GIT_AUTHOR_DATE': '2025-01-02T12:00:00+00:00',
        'GIT_COMMITTER_DATE': '2025-01-02T12:00:00+00:00',
    })
    git(repo, 'switch', 'feature')
    (repo / 'tests').mkdir()
    (repo / 'tests' / 'a test.py').write_text('assert True\n')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Alicia', '-c', 'user.email=alice@example.test', 'commit', '-m', 'feature work', env={
        'GIT_AUTHOR_DATE': '2025-01-03T08:00:00+00:00',
        'GIT_COMMITTER_DATE': '2025-01-03T08:00:00+00:00',
    })
    return repo


def test_all_branches_deduplicates_shared_commits_and_filters(sample_repo):
    assert git_is_repo(sample_repo)
    all_commits, trunc = get_commits(sample_repo, branch=None, since_days=None, max_count=None)
    assert not trunc
    assert len(all_commits) == 3
    assert len({c['sha'] for c in all_commits}) == 3
    branches = get_branches(sample_repo)
    refs = {b['ref'] for b in branches}
    assert 'refs/heads/main' in refs
    assert 'refs/heads/feature' in refs
    assert len(get_commits(sample_repo, branch='refs/heads/main', since_days=None)[0]) == 2
    assert len(get_commits(sample_repo, branch='refs/heads/feature', since_days=None)[0]) == 2
    with pytest.raises(GitError):
        get_commits(sample_repo, branch='--upload-pack=evil', since_days=None)


def test_metrics_and_path_filter_no_cross_branch_double_count(sample_repo):
    commits = get_commits(sample_repo, since_days=None)[0]
    src_commits = filter_commits(commits, folder='src/')
    assert len(src_commits) == 2
    m = build_metrics(src_commits)
    assert m['commits'] == 2
    assert m['additions'] == 3  # first 2 + main extra 1
    assert m['deletions'] == 0
    assert len(m['hotspots']) == 1
    assert m['hotspots'][0]['file'] == 'src/app.py'
    assert m['hotspots'][0]['touches'] == 2
    assert m['contributors'] == 2
    a = build_metrics(commits)
    assert a['contributors'] == 2  # aliases via same email
    assert a['additions'] == 5
    assert a['deletions'] == 0
    assert a['file_types'][0]['extension'] == '.py'


def test_file_name_with_newline_is_parsed(tmp_path):
    repo = tmp_path / 'odd-path'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'X')
    git(repo, 'config', 'user.email', 'x@example.test')
    filename = 'with\nnewline.py'
    (repo / filename).write_text('print(1)\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'odd')
    commits = get_commits(repo, since_days=None)[0]
    assert commits[0]['files'][0]['path'] == filename


def test_limit_is_explicit_and_reported(sample_repo):
    commits, truncated = get_commits(sample_repo, since_days=None, max_count=2)
    assert len(commits) == 2
    assert truncated
    data = snapshot({'repo-1': commits}, truncated={'repo-1': True})
    assert data['summary']['truncated_repos'] == ['repo-1']


def test_catalog_removal_does_not_delete_repository(tmp_path, sample_repo):
    path = tmp_path / 'catalog.json'
    catalog = Catalog(path)
    project_id = catalog.add_project('Equipe A')
    repo_id = catalog.add_local_repo(project_id, str(sample_repo))
    assert catalog.get_project(project_id)['repos'][0]['id'] == repo_id
    assert Catalog(path).get_project(project_id)['repos'][0]['id'] == repo_id
    with pytest.raises(CatalogError):
        catalog.add_local_repo(project_id, str(sample_repo))
    catalog.remove_repo(project_id, repo_id)
    assert sample_repo.exists()
    assert Catalog(path).get_project(project_id)['repos'] == []


@pytest.mark.parametrize('url', [
    'https://example.com/x', 'https://user:pass@github.com/u/r.git',
    'https://github.com/u/r.git?token=s3cr3t', 'file:///tmp/private',
    '-c evil', 'ssh://host/repo', 'git@invalidhost:x/y',
])
def test_remote_validation_rejects_unapproved_endpoints(url):
    with pytest.raises(CatalogError):
        validate_remote_url(url)


def test_remote_validation_explicit_github_only():
    assert validate_remote_url('https://github.com/team/repo.git') == 'https://github.com/team/repo.git'
    assert validate_remote_url('git@github.com:team/repo.git') == 'git@github.com:team/repo.git'
    assert parse_github_repo('git@github.com:team/repo.git') == 'team/repo'
    assert parse_github_repo('https://gitlab.com/team/repo') is None


def test_filter_author_day_repo_and_activity(sample_repo):
    commits = get_commits(sample_repo, since_days=None)[0]
    alice = filter_commits(commits, emails={'alice@example.test'})
    assert len(alice) == 2
    only_jan2 = filter_commits(commits, start_date='2025-01-02', end_date='2025-01-02')
    assert len(only_jan2) == 1
    assert recent_activity(only_jan2)[0]['message'] == 'main work'
    summary = get_repo_summary(sample_repo)
    assert summary['local_branches'] == 2
    assert summary['tags'] == 0


def test_branch_comparison_reports_divergence(sample_repo):
    result = compare_branches(sample_repo, 'refs/heads/main', 'refs/heads/feature')
    assert result['ahead'] == 1
    assert result['behind'] == 1
    assert not result['truncated']
    assert result['files'][0]['file'] == 'tests/a test.py'
    assert result['files'][0]['additions'] == 1
    with pytest.raises(GitError):
        compare_branches(sample_repo, 'refs/heads/main', '--exec=evil')
