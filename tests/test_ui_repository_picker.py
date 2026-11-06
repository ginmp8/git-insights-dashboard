"""Headless interaction contract for the repository picker (not a browser test)."""
from contextlib import nullcontext
import importlib
import sys
import types

from gitinsights.catalog import Catalog


def test_picker_requires_explicit_list_and_add_buttons(monkeypatch, tmp_path):
    fake = types.ModuleType('streamlit')
    fake.session_state = {}
    fake.caption = fake.info = fake.success = fake.warning = fake.error = lambda *a, **kw: None
    fake.spinner = lambda *a, **kw: nullcontext()
    fake.selectbox = lambda label, values, **kw: values[0]
    fake.checkbox = lambda *a, **kw: False
    fake.multiselect = lambda label, choices, **kw: list(choices)
    clicked = set()
    fake.button = lambda label, **kw: ('Listar' in label and 'list' in clicked) or ('Adicionar' in label and 'add' in clicked)
    monkeypatch.setitem(sys.modules, 'streamlit', fake)
    # Not the app entrypoint: pure UI unit test via test double.
    sys.modules.pop('gitinsights.ui_repository_picker', None)
    module = importlib.import_module('gitinsights.ui_repository_picker')
    call_counter = {'list': 0, 'clone': 0}
    listing = [
        {'full_name': 'team/a', 'clone_url': 'https://github.com/team/a.git', 'private': True, 'archived': False},
        {'full_name': 'team/b', 'clone_url': 'https://github.com/team/b.git', 'private': False, 'archived': False},
    ]
    def load():
        call_counter['list'] += 1
        return listing
    def clone(url, folder, *, use_gh_auth):
        assert use_gh_auth
        call_counter['clone'] += 1
        result = tmp_path / f'mirror-{call_counter["clone"]}'
        result.mkdir()
        return result
    monkeypatch.setattr(module, 'list_accessible_repositories', load)
    monkeypatch.setattr(module, 'clone_mirror', clone)
    monkeypatch.setattr('gitinsights.catalog.git_is_repo', lambda p: True)
    catalog = Catalog(tmp_path / 'catalog.json')
    project = catalog.add_project('Project A')
    assert not module.render_github_picker(catalog, project, [], tmp_path)
    assert call_counter == {'list': 0, 'clone': 0}
    clicked.add('list')
    assert not module.render_github_picker(catalog, project, [], tmp_path)
    assert call_counter == {'list': 1, 'clone': 0}
    clicked.remove('list')
    clicked.add('add')
    assert module.render_github_picker(catalog, project, [], tmp_path)
    assert call_counter == {'list': 1, 'clone': 2}
    assert len(catalog.get_project(project)['repos']) == 2
    assert all(r['auth_via_gh'] for r in catalog.get_project(project)['repos'])
    # Unhook fake module to prevent contamination of unrelated tests.
    sys.modules.pop('gitinsights.ui_repository_picker', None)
