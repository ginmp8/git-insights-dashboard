"""Optional GitHub CLI read integration, never called on ordinary dashboard reruns."""
from __future__ import annotations

import json
import os
import re
import subprocess
from urllib.parse import urlsplit

from .catalog import CatalogError, validate_remote_url
from .git_engine import GitError


def parse_github_repo(remote: str | None) -> str | None:
    if not remote:
        return None
    try:
        url = validate_remote_url(remote)
    except CatalogError:
        return None
    if url.startswith('git@github.com:'):
        name = url.split(':', 1)[1]
    else:
        name = urlsplit(url).path.strip('/')
    return name[:-4] if name.endswith('.git') else name


def list_pull_requests(repo: str, limit: int = 100) -> list[dict]:
    """Explicit remote call. Requires a pre-authenticated GitHub CLI."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise GitError('Identificador do GitHub inválido.')
    if not (1 <= limit <= 200):
        raise ValueError('Limite de PRs deve estar entre 1 e 200.')
    fields = 'number,title,state,author,createdAt,mergedAt,baseRefName,headRefName,url,additions,deletions,changedFiles'
    args = ['gh', 'pr', 'list', '--repo', repo, '--state', 'all', '--limit', str(limit), '--json', fields]
    env = os.environ.copy()
    env['GH_PROMPT_DISABLED'] = '1'
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=45, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f'GitHub CLI indisponível: {exc}') from exc
    if process.returncode:
        raise GitError('GitHub CLI falhou (confira gh auth status e conectividade). ' + process.stderr.strip()[:200])
    try:
        items = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise GitError('Resposta inválida do GitHub CLI.') from exc
    if not isinstance(items, list):
        raise GitError('Formato inesperado de PRs.')
    out = []
    for item in items:
        out.append({
            'repositório': repo,
            '#': item.get('number'),
            'Título': item.get('title', ''),
            'Estado': item.get('state', ''),
            'Autor': (item.get('author') or {}).get('login', ''),
            'Criado em': item.get('createdAt', ''),
            'Merge em': item.get('mergedAt', ''),
            'Origem': item.get('headRefName', ''),
            'Destino': item.get('baseRefName', ''),
            'Arquivos': item.get('changedFiles', 0),
            'Adições': item.get('additions', 0),
            'Remoções': item.get('deletions', 0),
            'URL': item.get('url', ''),
        })
    return out


def list_accessible_repositories(max_repositories: int = 5000) -> list[dict]:
    """Read the authenticated user's owner, collaborator and organization repositories.

    Only runs on explicit UI action. gh's jq emits one compact JSON array per
    repository, avoiding giant API response objects in Python. No token is read
    or stored by this application. Listing does not clone any repository.
    """
    if not 1 <= max_repositories <= 10000:
        raise ValueError('Limite de repositórios inválido.')
    # GET /user/repos covers owner, collaborator and organization membership;
    # `gh repo list` alone does not cover those multiple ownership boundaries.
    endpoint = ('user/repos?per_page=100&visibility=all'
                '&affiliation=owner%2Ccollaborator%2Corganization_member')
    fields = '.[] | [.full_name, .clone_url, .private, .archived, .pushed_at, .default_branch] | @json'
    command = ['gh', 'api', '--method', 'GET', '--paginate', endpoint, '--jq', fields]
    env = os.environ.copy()
    env['GH_PROMPT_DISABLED'] = '1'
    env['GH_PAGER'] = 'cat'
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError('GitHub CLI indisponível ou consulta expirou. Instale gh e execute gh auth login.') from exc
    if process.returncode:
        # gh stderr can contain private URLs or request data; do not echo it.
        raise GitError('Não foi possível listar repositórios. Confira gh auth status, permissões e conectividade.')
    result: dict[str, dict] = {}
    try:
        for line in process.stdout.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, list) or len(item) != 6:
                raise ValueError('Unexpected row')
            full_name, clone_url, private, archived, pushed_at, default_branch = item
            if not isinstance(full_name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', full_name):
                raise ValueError('Invalid repository name')
            if not isinstance(clone_url, str) or validate_remote_url(clone_url) != clone_url:
                raise ValueError('Unapproved Git remote URL')
            if parse_github_repo(clone_url) != full_name:
                raise ValueError('Repository identity mismatch')
            if not isinstance(private, bool) or not isinstance(archived, bool):
                raise ValueError('Invalid repository metadata')
            result[full_name.casefold()] = {
                'full_name': full_name, 'clone_url': clone_url,
                'private': private, 'archived': archived,
                'pushed_at': pushed_at if isinstance(pushed_at, str) else '',
                'default_branch': default_branch if isinstance(default_branch, str) else '',
            }
            if len(result) > max_repositories:
                raise GitError(f'A conta possui mais de {max_repositories} repositórios. Aumente o limite com cautela.')
    except (ValueError, TypeError, json.JSONDecodeError, CatalogError) as exc:
        raise GitError('O GitHub CLI retornou uma resposta de formato inválido.') from exc
    return sorted(result.values(), key=lambda item: item['full_name'].casefold())
