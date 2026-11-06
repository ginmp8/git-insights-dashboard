"""Bounded, read-only Git ingestion. No implicit remote network operations."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
from typing import Any


class GitError(RuntimeError):
    """Git operation did not complete successfully."""


def _run(path: str | Path, *args: str, timeout: int = 180) -> bytes:
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    try:
        p = subprocess.run(
            ['git', '-C', str(Path(path).resolve()), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f'Git indisponível ou operação excedeu o tempo limite: {exc}') from exc
    if p.returncode:
        detail = p.stderr.decode('utf-8', errors='replace').strip()
        raise GitError(detail[:500] or f'git retornou {p.returncode}')
    return p.stdout


def git_is_repo(path: str | Path) -> bool:
    path = Path(path).expanduser()
    if not path.is_dir():
        return False
    try:
        return _run(path, 'rev-parse', '--git-dir').strip() != b''
    except GitError:
        return False


def get_branches(path: str | Path) -> list[dict[str, str]]:
    """Enumerate known local and remote refs without checking out or fetching."""
    data = _run(
        path, 'for-each-ref',
        '--format=%(refname)%00%(objectname)%00%(committerdate:iso8601-strict)%00%(symref)',
        'refs/heads', 'refs/remotes',
    )
    branches = []
    for line in data.decode('utf-8', errors='replace').splitlines():
        parts = line.split('\x00')
        if len(parts) != 4 or parts[3]:  # skip symbolic origin/HEAD
            continue
        ref, sha, changed, _ = parts
        if not sha or not ref.startswith(('refs/heads/', 'refs/remotes/')):
            continue
        branches.append({
            'ref': ref,
            'name': ref.removeprefix('refs/heads/').removeprefix('refs/remotes/'),
            'sha': sha,
            'updated': changed,
            'kind': 'remota' if ref.startswith('refs/remotes/') else 'local',
        })
    return branches


def get_repo_summary(path: str | Path) -> dict[str, Any]:
    if not git_is_repo(path):
        raise GitError('Não é um repositório Git válido.')
    branches = get_branches(path)
    tags = _run(path, 'tag', '--list').decode('utf-8', errors='replace').splitlines()
    return {
        'local_branches': sum(b['kind'] == 'local' for b in branches),
        'remote_branches': sum(b['kind'] == 'remota' for b in branches),
        'tags': len(tags),
        'path': str(Path(path).resolve()),
    }


def get_origin_url(path: str | Path) -> str | None:
    """Return a remote URL locally; caller must never display embedded credentials."""
    try:
        return _run(path, 'remote', 'get-url', 'origin').decode('utf-8', errors='replace').strip()
    except GitError:
        return None


def _parse_log(data: bytes) -> list[dict[str, Any]]:
    """Parse -z numstat, retaining spaces/newlines in filenames.

    Separators in Git pretty headers are ASCII control characters. A ref/path
    containing the record separator (0x1e) is not supported; this is an
    explicit parser limitation, not silently accepted input.
    """
    results: list[dict[str, Any]] = []
    for part in data.split(b'\x1e'):
        if not part.strip(b'\x00\n'):
            continue
        header, sep, tail = part.partition(b'\x00')
        if not sep:
            raise GitError('Formato inesperado de log Git (cabeçalho).')
        fields = header.decode('utf-8', errors='replace').split('\x1f')
        if len(fields) != 6 or len(fields[0]) not in (40, 64):
            raise GitError('Formato inesperado de log Git (campos).')
        sha, author, email, date, subject, parents = fields
        files: list[dict[str, Any]] = []
        # Each --numstat -z entry is additions<TAB>deletions<TAB>raw-path<NUL>.
        # --no-renames prevents the alternative rename-path representation.
        for record in tail.split(b'\x00'):
            if record.startswith(b'\n'):
                record = record[1:]
            if not record:
                continue
            counts = record.split(b'\t', 2)
            if len(counts) != 3:
                raise GitError('Formato inesperado de --numstat.')
            a, d, raw_path = counts
            path = raw_path.decode('utf-8', errors='replace')
            files.append({
                'path': path,
                'additions': int(a) if a.isdigit() else 0,
                'deletions': int(d) if d.isdigit() else 0,
                'binary': a == b'-' or d == b'-',
            })
        results.append({
            'sha': sha,
            'author': author,
            'email': email.strip().lower(),
            'date': date,
            'message': subject,
            'parents': parents.split() if parents else [],
            'merge': len(parents.split()) > 1,
            'files': files,
        })
    return results


def get_commits(
    path: str | Path,
    branch: str | None = None,
    since_days: int | None = 90,
    max_count: int | None = 5000,
) -> tuple[list[dict[str, Any]], bool]:
    """Read all locally known branches, or exactly one validated ref.

    Git deduplicates shared commits. An explicit limit is tracked and surfaced.
    """
    if not git_is_repo(path):
        raise GitError('Diretório não contém um repositório Git.')
    if since_days is not None and not (1 <= since_days <= 36500):
        raise ValueError('Período deve estar entre 1 e 36500 dias ou ser None.')
    if max_count is not None and not (1 <= max_count <= 200000):
        raise ValueError('O limite de commits deve estar entre 1 e 200000 ou ser None.')
    if branch is not None and branch not in {item['ref'] for item in get_branches(path)}:
        raise GitError('A branch selecionada não existe neste clone local.')
    fmt = '%x1e%H%x1f%aN%x1f%aE%x1f%aI%x1f%s%x1f%P'
    args = ['log', '--use-mailmap', '--no-renames', '--format=' + fmt, '--numstat', '-z']
    if since_days is not None:
        args.append(f'--since={since_days} days ago')
    if max_count is not None:
        args.append(f'--max-count={max_count + 1}')
    if branch is None:
        args.extend(['--branches', '--remotes'])
    else:
        args.append(branch)
    try:
        commits = _parse_log(_run(path, *args))
    except GitError as exc:
        # Empty, unborn repository: Git returns 0 without refs or a harmless
        # 'no commits' error depending on Git version.
        if 'does not have any commits' in str(exc) or 'your current branch' in str(exc):
            return [], False
        raise
    truncated = max_count is not None and len(commits) > max_count
    if truncated:
        commits = commits[:max_count]
    return commits, truncated


def ref_commit_counts(path: str | Path, refs: list[str], max_refs: int = 80) -> dict[str, int]:
    """Counts reachable commits per branch; not disjoint across branches."""
    allowed = {b['ref'] for b in get_branches(path)}
    out = {}
    for ref in refs[:max_refs]:
        if ref not in allowed:
            continue
        try:
            out[ref] = int(_run(path, 'rev-list', '--count', ref, timeout=20).strip() or b'0')
        except (GitError, ValueError):
            continue
    return out


def compare_branches(path: str | Path, base: str, head: str, max_files: int = 500) -> dict[str, Any]:
    """Read-only Git comparison: ahead/behind and diff from merge-base to head.

    Counts are unique commits on the two sides; file change totals reflect the
    resulting diff of `base...head`, not the sum of individual commit churn.
    """
    valid = {item['ref'] for item in get_branches(path)}
    if base not in valid or head not in valid:
        raise GitError('Branch de origem ou destino não existe neste clone.')
    if base == head:
        return {'base': base, 'head': head, 'behind': 0, 'ahead': 0, 'files': [], 'truncated': False}
    counts = _run(path, 'rev-list', '--left-right', '--count', f'{base}...{head}', timeout=30)
    try:
        behind, ahead = (int(v) for v in counts.decode('ascii').split())
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitError('Não foi possível interpretar a divergência de branches.') from exc
    data = _run(path, 'diff', '--no-renames', '--numstat', '-z', f'{base}...{head}', '--', timeout=60)
    rows = []
    for entry in data.split(b'\x00'):
        if not entry:
            continue
        fields = entry.split(b'\t', 2)
        if len(fields) != 3:
            raise GitError('Resposta numstat inesperada ao comparar branches.')
        a, d, name = fields
        rows.append({
            'file': name.decode('utf-8', errors='replace'),
            'additions': int(a) if a.isdigit() else 0,
            'deletions': int(d) if d.isdigit() else 0,
            'binary': a == b'-' or d == b'-',
        })
    rows.sort(key=lambda r: (-(r['additions'] + r['deletions']), r['file']))
    return {'base': base, 'head': head, 'behind': behind, 'ahead': ahead,
            'files': rows[:max_files], 'truncated': len(rows) > max_files}
