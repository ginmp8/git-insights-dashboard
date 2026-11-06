"""On-demand, read-only Git change diagnostics (NOT an individual productivity score).

Three comparable views per commit: pre-existing raw numstat, Git rename-aware
numstat, and rename-aware whitespace-insensitive numstat. Rename detection and
identifier-only candidates are heuristics. Never silently fold these indicators
into the existing historical churn metrics.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

from .git_engine import _run, GitError

CODE_EXTENSIONS = frozenset({
    '.py', '.cs', '.ts', '.tsx', '.js', '.jsx', '.java', '.kt', '.go', '.rs',
    '.cpp', '.c', '.cc', '.h', '.hpp', '.rb', '.php', '.swift', '.scala', '.dart',
})
TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|specs?)/|(^|/)(test_|spec_)([^/]+)|\.(test|spec)\.[^/]+$', re.I)
TOKEN = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|'
    r'[A-Za-z_$][A-Za-z0-9_$]*|\d+(?:\.\d+)?|[^\s]', re.S,
)
IDENTIFIER = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*$')
# Common language control keywords and literals that should never be treated
# as a cosmetic symbol rename by this heuristic.
RESERVED = frozenset(('true', 'false', 'none', 'null', 'undefined', 'return',
                      'if', 'else', 'for', 'while', 'break', 'continue',
                      'try', 'catch', 'finally', 'throw', 'await', 'async',
                      'class', 'def', 'function', 'const', 'let', 'var', 'new',
                      'public', 'private', 'protected', 'static', 'void',
                      'import', 'export', 'from', 'using', 'namespace',
                      'switch', 'case', 'default', 'yield', 'raise', 'pass',
                      'and', 'or', 'not', 'in', 'is', 'self', 'this'))


def parse_numstat(data: bytes) -> list[dict[str, Any]]:
    """Parse Git -M --numstat -z (rename rows contain TWO extra NUL paths)."""
    parts = data.split(b'\x00')
    items = []
    i = 0
    while i < len(parts):
        if not parts[i]:
            i += 1
            continue
        fields = parts[i].split(b'\t', 2)
        if len(fields) != 3:
            raise GitError('Formato inesperado do diff Git (numstat).')
        raw_add, raw_del, raw_path = fields
        if raw_path:
            old = None
            path = raw_path.decode('utf-8', errors='replace')
            i += 1
        else:
            if i + 2 >= len(parts) or not parts[i+1] or not parts[i+2]:
                raise GitError('Registro Git de rename incompleto.')
            old = parts[i+1].decode('utf-8', errors='replace')
            path = parts[i+2].decode('utf-8', errors='replace')
            i += 3
        items.append({
            'path': path, 'old_path': old,
            'additions': int(raw_add) if raw_add.isdigit() else 0,
            'deletions': int(raw_del) if raw_del.isdigit() else 0,
            'binary': raw_add == b'-' or raw_del == b'-',
        })
    return items


def parse_name_status(data: bytes) -> list[dict]:
    parts = data.split(b'\x00')
    items: list[dict] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        if not status:
            i += 1
            continue
        i += 1
        try:
            kind = status.decode('ascii')
        except UnicodeDecodeError as exc:
            raise GitError('Status inválido no diff Git.') from exc
        if not re.fullmatch(r'[A-Z](?:\d+)?', kind):
            raise GitError('Status inesperado no diff Git.')
        if kind[0] in ('R', 'C'):
            if i + 1 >= len(parts) or not parts[i] or not parts[i+1]:
                raise GitError('Rename sem caminhos no diff Git.')
            old = parts[i].decode('utf-8', errors='replace')
            path = parts[i+1].decode('utf-8', errors='replace')
            i += 2
        else:
            if i >= len(parts) or not parts[i]:
                raise GitError('Status sem caminho no diff Git.')
            old = None
            path = parts[i].decode('utf-8', errors='replace')
            i += 1
        items.append({'status': kind, 'old_path': old, 'path': path})
    return items


def identifier_only_candidate(before: str, after: str) -> bool:
    """Conservative lexical *candidate*, not a semantic-equivalence check.

    Requires token count/order to remain the same and only consistent, 1:1
    identifier substitutions. In particular, string literal, numeric, operator
    and keyword edits fail this predicate. Comments are not language-parsed.
    """
    left = TOKEN.findall(before)
    right = TOKEN.findall(after)
    if not left or len(left) != len(right) or len(left) > 25000:
        return False
    forward: dict[str, str] = {}
    reverse: dict[str, str] = {}
    changes = 0
    for old, new in zip(left, right):
        if old == new:
            continue
        if not (IDENTIFIER.fullmatch(old) and IDENTIFIER.fullmatch(new)):
            return False
        if old.lower() in RESERVED or new.lower() in RESERVED:
            return False
        if forward.setdefault(old, new) != new or reverse.setdefault(new, old) != old:
            return False
        changes += 1
    return changes > 0


def _blob(repo_path: str | Path, sha: str, path: str, max_bytes: int = 100000) -> str | None:
    try:
        payload = _run(repo_path, 'show', f'{sha}:{path}', timeout=20)
        if len(payload) > max_bytes or b'\x00' in payload:
            return None
        return payload.decode('utf-8')
    except (GitError, UnicodeError):
        return None


def _diff(repo_path: str | Path, sha: str, kind: str, *, ignore_whitespace: bool = False) -> bytes:
    args = ['diff-tree', '--root', '--no-commit-id', '-r', '--no-ext-diff', '-M', '-z']
    if ignore_whitespace:
        args.append('-w')
    args.extend([kind, sha])
    return _run(repo_path, *args, timeout=90)


def analyze_change_quality(repo_path: str | Path, commits: list[dict], *,
                           max_identifier_files_per_commit: int = 12) -> list[dict]:
    """Compute diagnostics on a caller-selected, bounded batch of commits.

    `commits` must originate from get_commits() for this exact repository.
    File filtering uses only file paths already present in each commit row.
    Merge commits contribute 0 line metrics, as in the historical dashboard.
    """
    results = []
    for c in commits:
        sha = c['sha']
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha):
            raise GitError('SHA de commit inválido.')
        original_paths = {f['path'] for f in c['files']}
        gross_churn = sum(f['additions'] + f['deletions'] for f in c['files']) if not c.get('merge') else 0
        record: dict[str, Any] = {
            'sha': sha, 'author': c['author'], 'email': c['email'].lower(),
            'date': c['date'], 'message': c['message'], 'repo': c.get('repo', ''),
            'gross_churn': gross_churn, 'rename_aware_churn': 0,
            'adjusted_churn': 0, 'estimated_move_churn': 0,
            'estimated_space_churn': 0, 'moved_files': 0,
            'pure_moves': 0, 'identifier_only_candidates': 0,
            'identifier_candidate_churn': 0, 'candidate_files_examined': 0,
            'candidate_files_skipped': 0, 'test_files_touched': 0,
            'source_files_touched': 0, 'moves': [],
            'identifier_candidate_paths': [], 'merge': bool(c.get('merge')),
        }
        if record['merge']:
            results.append(record)
            continue
        aware = [f for f in parse_numstat(_diff(repo_path, sha, '--numstat'))
                 if f['path'] in original_paths or f['old_path'] in original_paths]
        adjusted = [f for f in parse_numstat(_diff(repo_path, sha, '--numstat', ignore_whitespace=True))
                    if f['path'] in original_paths or f['old_path'] in original_paths]
        statuses = [s for s in parse_name_status(_diff(repo_path, sha, '--name-status'))
                    if s['path'] in original_paths or s['old_path'] in original_paths]
        record['rename_aware_churn'] = sum(f['additions'] + f['deletions'] for f in aware)
        record['adjusted_churn'] = sum(f['additions'] + f['deletions'] for f in adjusted)
        record['estimated_move_churn'] = max(0, gross_churn - record['rename_aware_churn'])
        record['estimated_space_churn'] = max(0, record['rename_aware_churn'] - record['adjusted_churn'])
        record['moves'] = [
            {'old_path': s['old_path'], 'new_path': s['path'],
             'similarity': int(s['status'][1:]) if s['status'][1:].isdigit() else None}
            for s in statuses if s['status'].startswith('R')
        ]
        record['moved_files'] = len(record['moves'])
        record['pure_moves'] = sum(s['status'] == 'R100' for s in statuses)
        record['test_files_touched'] = sum(bool(TEST_PATH.search(s['path'])) for s in statuses)
        record['source_files_touched'] = sum(Path(s['path']).suffix.lower() in CODE_EXTENSIONS and not TEST_PATH.search(s['path']) for s in statuses)

        # Check likely pure identifier substitutions only when code actually
        # changed and a first parent exists; unmodified pure moves need no blob reads.
        parents = c.get('parents', [])
        if parents:
            by_path = {f['path']: f for f in adjusted}
            for status in statuses:
                if record['candidate_files_examined'] >= max_identifier_files_per_commit:
                    record['candidate_files_skipped'] += 1
                    continue
                path = status['path']
                info = by_path.get(path)
                if (Path(path).suffix.lower() not in CODE_EXTENSIONS or
                        not info or not (info['additions'] and info['deletions']) or info['binary'] or
                        status['status'][0] not in ('M', 'R')):
                    continue
                record['candidate_files_examined'] += 1
                old_path = status['old_path'] or path
                old_text = _blob(repo_path, parents[0], old_path)
                new_text = _blob(repo_path, sha, path)
                if old_text is None or new_text is None:
                    record['candidate_files_skipped'] += 1
                    continue
                if identifier_only_candidate(old_text, new_text):
                    record['identifier_only_candidates'] += 1
                    record['identifier_candidate_paths'].append(path)
                    record['identifier_candidate_churn'] += info['additions'] + info['deletions']
        results.append(record)
    return results


def summarize_change_quality(rows: list[dict]) -> dict[str, Any]:
    fields = (
        'gross_churn', 'rename_aware_churn', 'adjusted_churn', 'estimated_move_churn',
        'estimated_space_churn', 'moved_files', 'pure_moves',
        'identifier_only_candidates', 'identifier_candidate_churn',
        'candidate_files_examined', 'candidate_files_skipped',
        'test_files_touched', 'source_files_touched',
    )
    totals = {field: 0 for field in fields}
    by_author: dict[str, dict] = {}
    for row in rows:
        email = row['email'].lower()
        if email not in by_author:
            by_author[email] = {'email': email, 'author': row['author'], 'commits': 0, **{f: 0 for f in fields}}
        record = by_author[email]
        record['commits'] += 1
        for field in fields:
            totals[field] += row[field]
            record[field] += row[field]
    return {
        'analyzed_commits': len(rows), 'totals': totals, 'by_author': by_author,
    }
