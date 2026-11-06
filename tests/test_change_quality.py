"""Acceptance: moved files and whitespace-only edits do not masquerade as functional line changes."""
import os
from pathlib import Path
import subprocess

import pytest

from gitinsights.change_quality import analyze_change_quality, summarize_change_quality
from gitinsights.git_engine import get_commits


def git(repo, *args, author=None):
    env = os.environ.copy()
    env.update({'GIT_AUTHOR_DATE': '2026-02-03T12:00:00+00:00', 'GIT_COMMITTER_DATE': '2026-02-03T12:00:00+00:00'})
    if author:
        env.update({'GIT_AUTHOR_NAME': author, 'GIT_COMMITTER_NAME': author, 'GIT_AUTHOR_EMAIL': author.lower()+'@example.test', 'GIT_COMMITTER_EMAIL': author.lower()+'@example.test'})
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, env=env, check=True)
    return p.stdout.strip()


@pytest.fixture
def quality_repo(tmp_path):
    repo = tmp_path / 'repository'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'Test')
    git(repo, 'config', 'user.email', 'test@example.test')
    (repo / 'one').mkdir()
    (repo / 'one' / 'module.py').write_text(''.join('value = %d\n' % n for n in range(80)))
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'initial', author='Alice')
    (repo / 'two').mkdir()
    git(repo, 'mv', 'one/module.py', 'two/module.py')
    git(repo, 'commit', '-m', 'file move', author='Bob')
    path = repo / 'two' / 'module.py'
    path.write_text(''.join('value    =    %d\n' % n for n in range(80)))
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'spacing', author='Carol')
    path.write_text(path.read_text().replace('value', 'item'))
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'symbol rename', author='David')
    path.write_text(path.read_text() + 'if item > 10:\n    print(item)\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'logic change', author='Eve')
    return repo


def test_move_aware_and_cosmetic_metrics_are_separate(quality_repo):
    commits, truncated = get_commits(quality_repo, since_days=None)
    assert not truncated
    rows = analyze_change_quality(quality_repo, commits)
    by_author = {r['author']: r for r in rows}
    assert by_author['Bob']['gross_churn'] >= 160
    assert by_author['Bob']['rename_aware_churn'] == 0
    assert by_author['Bob']['moved_files'] == 1
    assert by_author['Bob']['moves'][0]['old_path'] == 'one/module.py'
    assert by_author['Bob']['moves'][0]['new_path'] == 'two/module.py'
    assert by_author['Carol']['rename_aware_churn'] >= 160
    assert by_author['Carol']['adjusted_churn'] == 0
    assert by_author['David']['adjusted_churn'] > 0
    assert by_author['David']['identifier_only_candidates'] >= 1
    assert by_author['David']['identifier_candidate_paths'] == ['two/module.py']
    assert by_author['Eve']['adjusted_churn'] > 0
    grouped = summarize_change_quality(rows)
    assert grouped['by_author']['bob@example.test']['moved_files'] == 1
    assert grouped['by_author']['carol@example.test']['adjusted_churn'] == 0
    assert grouped['analyzed_commits'] == 5


def test_quality_respects_subset_and_root_commits(quality_repo):
    commits = get_commits(quality_repo, since_days=None)[0]
    alice = next(c for c in commits if c['author'] == 'Alice')
    result = analyze_change_quality(quality_repo, [alice])
    assert result[0]['adjusted_churn'] == 80
    assert result[0]['identifier_only_candidates'] == 0


def test_quality_scope_respects_folder_filter(quality_repo):
    from gitinsights.analytics import filter_commits
    commits = filter_commits(get_commits(quality_repo, since_days=None)[0], folder='two')
    results = analyze_change_quality(quality_repo, commits)
    assert 'Alice' not in [row['author'] for row in results]
    assert next(row for row in results if row['author'] == 'Bob')['moved_files'] == 1
