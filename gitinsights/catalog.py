"""Small atomic local project catalog; Git working directories are never changed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from .git_engine import git_is_repo


class CatalogError(ValueError):
    pass


_GITHUB_RE = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$')


def validate_remote_url(value: str) -> str:
    """Allow only credential-free HTTPS/SSH GitHub repositories."""
    url = value.strip()
    if url.startswith('git@github.com:'):
        path = url[len('git@github.com:'):]
        if _GITHUB_RE.fullmatch(path) and not path.startswith(('/', '-')):
            return url
    elif url.startswith('https://'):
        u = urlsplit(url)
        path = u.path.lstrip('/')
        if u.hostname == 'github.com' and not u.username and not u.password and not u.query and not u.fragment and not u.port:
            if _GITHUB_RE.fullmatch(path) and not path.startswith(('/', '-')):
                return url
    raise CatalogError('URL inválida: use HTTPS ou SSH do github.com, sem credenciais na URL.')


class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {'version': 1, 'projects': []}
        try:
            result = json.loads(self.path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise CatalogError('Catálogo local danificado ou inacessível.') from exc
        if not isinstance(result, dict) or result.get('version') != 1 or not isinstance(result.get('projects'), list):
            raise CatalogError('Versão/estrutura de catálogo não suportada.')
        return result

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.data, ensure_ascii=False, indent=2) + '\n'
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, prefix='.catalog-', delete=False) as tmp:
                tmp_name = tmp.name
                tmp.write(content)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @property
    def projects(self) -> list[dict]:
        return list(self.data['projects'])

    def get_project(self, id: str) -> dict:
        for project in self.data['projects']:
            if project['id'] == id:
                return project
        raise CatalogError('Projeto não encontrado.')

    def add_project(self, name: str) -> str:
        name = name.strip()
        if not (1 <= len(name) <= 80):
            raise CatalogError('Nome do projeto precisa ter entre 1 e 80 caracteres.')
        if any(project['name'].casefold() == name.casefold() for project in self.data['projects']):
            raise CatalogError('Já existe um projeto com este nome.')
        id = uuid4().hex
        self.data['projects'].append({'id': id, 'name': name, 'repos': []})
        self._save()
        return id

    def add_local_repo(self, project_id: str, path: str, name: str = '') -> str:
        repo_path = Path(path).expanduser().resolve()
        if not git_is_repo(repo_path):
            raise CatalogError('Caminho não corresponde a um repositório Git acessível.')
        return self._add_repo(project_id, str(repo_path), name or repo_path.name, 'local')

    def add_mirror_repo(self, project_id: str, path: str, url: str, name: str = '', *, auth_via_gh: bool = False) -> str:
        """Register an already cloned mirror; cloning requires a separate explicit action."""
        validate_remote_url(url)
        repo_path = Path(path).resolve()
        if not git_is_repo(repo_path):
            raise CatalogError('Espelho Git ainda não foi criado.')
        return self._add_repo(project_id, str(repo_path), name or repo_path.name, 'mirror', url, auth_via_gh=auth_via_gh)

    def _add_repo(self, project_id: str, path: str, name: str, kind: str, url: str = '', *, auth_via_gh: bool = False) -> str:
        project = self.get_project(project_id)
        if any(r['path'] == path for r in project['repos']):
            raise CatalogError('Repositório já cadastrado neste projeto.')
        name = name.strip()
        if not (1 <= len(name) <= 80):
            raise CatalogError('Nome do repositório inválido.')
        id = uuid4().hex
        repo = {'id': id, 'name': name, 'path': path, 'kind': kind, 'url': url}
        if auth_via_gh:
            repo['auth_via_gh'] = True
        project['repos'].append(repo)
        self._save()
        return id

    def remove_repo(self, project_id: str, repo_id: str) -> None:
        """Unregister only; never remove local repositories or mirror files."""
        project = self.get_project(project_id)
        size = len(project['repos'])
        project['repos'] = [r for r in project['repos'] if r['id'] != repo_id]
        if len(project['repos']) == size:
            raise CatalogError('Repositório não encontrado.')
        self._save()

    def remove_project(self, project_id: str) -> None:
        self.get_project(project_id)
        self.data['projects'] = [p for p in self.data['projects'] if p['id'] != project_id]
        self._save()
