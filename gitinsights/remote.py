"""Explicit, opt-in GitHub mirroring outside the user's source repository."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from .catalog import validate_remote_url
from .git_engine import GitError, git_is_repo


def _git_auth_config(use_gh_auth: bool) -> list[str]:
    # Delegate credentials to the existing gh authentication at Git invocation
    # time; never extract tokens, write .gitconfig, or embed secrets in URLs.
    return ['-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential'] if use_gh_auth else []


def clone_mirror(url: str, cache_root: str | Path, *, use_gh_auth: bool = False) -> Path:
    """Network side effect; call only from an explicit UI submission."""
    validated = validate_remote_url(url)
    root = Path(cache_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / ('mirror-' + uuid4().hex)
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GH_PROMPT_DISABLED'] = '1'
    try:
        p = subprocess.run(['git', *_git_auth_config(use_gh_auth), 'clone', '--mirror', validated, str(destination)], capture_output=True, text=True, timeout=180, env=env)
        if p.returncode:
            raise GitError('Falha ao clonar: ' + p.stderr.strip()[:300])
        if not git_is_repo(destination):
            raise GitError('Espelho não contém repositório Git válido.')
        return destination
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f'Falha ao clonar: {exc}') from exc
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)  # Only owned, newly-created destination
        raise


def refresh_mirror(path: str | Path, trusted_cache_root: str | Path, *, use_gh_auth: bool = False) -> None:
    """Update an app-owned cache only after an explicit user click."""
    root = Path(trusted_cache_root).resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(root) or not target.name.startswith('mirror-') or not git_is_repo(target):
        raise GitError('Atualização permitida apenas em espelhos controlados pelo aplicativo.')
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GH_PROMPT_DISABLED'] = '1'
    try:
        p = subprocess.run(['git', *_git_auth_config(use_gh_auth), '-C', str(target), 'fetch', '--prune', 'origin'], capture_output=True, text=True, timeout=120, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f'Falha no fetch: {exc}') from exc
    if p.returncode:
        raise GitError('Falha ao atualizar espelho: ' + p.stderr.strip()[:300])
