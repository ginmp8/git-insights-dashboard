"""Acceptance: GitHub picker loads accessible repos, validates and authorizes one-click imports."""
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from gitinsights.catalog import Catalog
from gitinsights.git_engine import GitError
from gitinsights.github import list_accessible_repositories
from gitinsights.remote import clone_mirror


def test_gh_lists_private_collaborator_org_repositories_without_paste(monkeypatch):
    rows = [
        ['alice/tool', 'https://github.com/alice/tool.git', False, False, '2026-01-01T10:00:00Z', 'main'],
        ['team/private', 'https://github.com/team/private.git', True, False, '2026-02-02T10:00:00Z', 'dev'],
        ['team/private', 'https://github.com/team/private.git', True, False, '2026-02-02T10:00:00Z', 'dev'],
    ]
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Mock(returncode=0, stdout='\n'.join(json.dumps(row) for row in rows), stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    repos = list_accessible_repositories()
    assert [r['full_name'] for r in repos] == ['alice/tool', 'team/private']
    assert repos[1]['private'] is True
    assert repos[1]['default_branch'] == 'dev'
    assert calls[0][0][0:2] == ['gh', 'api']
    assert '--paginate' in calls[0][0]
    assert 'user/repos' in ' '.join(calls[0][0])
    assert calls[0][1]['env']['GH_PROMPT_DISABLED'] == '1'


def test_gh_list_invalid_or_missing_cli_fails_without_leaking_response(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: Mock(returncode=0, stdout='{"token":"SECRET"}\n', stderr=''))
    with pytest.raises(GitError, match='formato') as exc:
        list_accessible_repositories()
    assert 'SECRET' not in str(exc.value)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: Mock(returncode=1, stdout='', stderr='token=SECRET'))
    with pytest.raises(GitError) as exc:
        list_accessible_repositories()
    assert 'SECRET' not in str(exc.value)


def test_gh_list_rejects_untrusted_urls(monkeypatch):
    rows = [['team/tool', 'https://user:secret@github.com/team/tool.git', True, False, '', 'main']]
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: Mock(returncode=0, stdout=json.dumps(rows[0]), stderr=''))
    with pytest.raises(GitError):
        list_accessible_repositories()


def test_clone_with_gh_credentials_does_not_need_global_git_config(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        Path(args[-1]).mkdir(parents=True)
        return Mock(returncode=0, stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr('gitinsights.remote.git_is_repo', lambda p: True)
    destination = clone_mirror('https://github.com/team/private.git', tmp_path, use_gh_auth=True)
    assert destination.is_dir()
    assert '-c' in calls[0]
    assert 'credential.helper=!gh auth git-credential' in calls[0]
    assert 'clone' in calls[0]
    assert '--mirror' in calls[0]


def test_catalog_records_gh_auth_for_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr('gitinsights.catalog.git_is_repo', lambda p: True)
    catalog = Catalog(tmp_path / 'catalog.json')
    project = catalog.add_project('my team')
    entry = catalog.add_mirror_repo(project, str(tmp_path / 'mirror'), 'https://github.com/team/repo.git', 'team/repo', auth_via_gh=True)
    assert next(r for r in catalog.get_project(project)['repos'] if r['id'] == entry)['auth_via_gh'] is True
