"""Pure deterministic metrics for already-ingested Git commits."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any


def filter_commits(
    commits: list[dict[str, Any]],
    *,
    emails: set[str] | None = None,
    folder: str = '',
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """A folder filter recalculates change totals from matching file rows only."""
    normalized = folder.replace('\\', '/').strip('/')
    email_filter = {e.lower() for e in emails} if emails is not None else None
    out = []
    for item in commits:
        if email_filter is not None and item['email'].lower() not in email_filter:
            continue
        day = item['date'][:10]
        if start_date and day < start_date:
            continue
        if end_date and day > end_date:
            continue
        if normalized:
            matches = [
                f for f in item['files']
                if f['path'] == normalized or f['path'].startswith(normalized + '/')
            ]
            if not matches:
                continue
            item = {**item, 'files': matches}
        out.append(item)
    return out


def _file_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix if suffix else '(sem extensão)'


def build_metrics(commits: list[dict[str, Any]]) -> dict[str, Any]:
    """Line metrics describe historic changes, not lines currently in source."""
    by_day: Counter[str] = Counter()
    by_hour: Counter[int] = Counter()
    by_weekday: Counter[int] = Counter()
    by_repo: dict[str, dict[str, Any]] = defaultdict(lambda: {'commits': 0, 'additions': 0, 'deletions': 0})
    author_stats: dict[str, dict[str, Any]] = {}
    hotspots: dict[str, dict[str, Any]] = {}
    extensions: dict[str, dict[str, int]] = defaultdict(lambda: {'files_touched': 0, 'additions': 0, 'deletions': 0})
    additions = 0
    deletions = 0
    for c in commits:
        dt = datetime.fromisoformat(c['date'])
        date = dt.date().isoformat()
        by_day[date] += 1
        by_hour[dt.hour] += 1
        by_weekday[dt.weekday()] += 1
        repo = c.get('repo', 'Repository')
        by_repo[repo]['commits'] += 1
        email = c['email'].lower()
        if email not in author_stats:
            author_stats[email] = {
                'email': email, 'author': c['author'], 'commits': 0,
                'additions': 0, 'deletions': 0, 'repos': set(),
            }
        author = author_stats[email]
        author['commits'] += 1
        author['repos'].add(repo)
        # Git's standard --numstat has no line changes for merge-only commits;
        # exclude merge commits from author line metrics consistently.
        for f in ([] if c.get('merge') else c['files']):
            a, d = f['additions'], f['deletions']
            additions += a
            deletions += d
            author['additions'] += a
            author['deletions'] += d
            by_repo[repo]['additions'] += a
            by_repo[repo]['deletions'] += d
            key = f'{repo}::{f["path"]}'
            if key not in hotspots:
                hotspots[key] = {
                    'repo': repo, 'file': f['path'], 'touches': 0,
                    'additions': 0, 'deletions': 0,
                }
            hotspot = hotspots[key]
            hotspot['touches'] += 1
            hotspot['additions'] += a
            hotspot['deletions'] += d
            kind = extensions[_file_type(f['path'])]
            kind['files_touched'] += 1
            kind['additions'] += a
            kind['deletions'] += d
    authors = []
    for record in author_stats.values():
        authors.append({**record, 'repos': len(record['repos']), 'churn': record['additions'] + record['deletions']})
    authors.sort(key=lambda item: (-item['commits'], item['email']))
    hot_list = sorted(hotspots.values(), key=lambda x: (-x['touches'], x['repo'], x['file']))
    return {
        'commits': len(commits),
        'contributors': len(author_stats),
        'additions': additions,
        'deletions': deletions,
        'churn': additions + deletions,
        'net': additions - deletions,
        'days': [{'date': day, 'commits': n} for day, n in sorted(by_day.items())],
        'hours': [{'hour': i, 'commits': by_hour[i]} for i in range(24)],
        'weekdays': [{'day': i, 'commits': by_weekday[i]} for i in range(7)],
        'authors': authors,
        'hotspots': hot_list,
        'file_types': sorted([
            {'extension': ext, **values} for ext, values in extensions.items()
        ], key=lambda item: (-item['files_touched'], item['extension'])),
        'repos': [{'repo': repo, **values} for repo, values in sorted(by_repo.items())],
    }


def recent_activity(commits: list[dict[str, Any]], limit: int = 200) -> list[dict[str, Any]]:
    return [
        {
            'repo': c.get('repo', 'Repository'), 'sha': c['sha'][:10],
            'date': c['date'], 'author': c['author'], 'email': c['email'],
            'message': c['message'],
            'additions': sum(f['additions'] for f in c['files']) if not c.get('merge') else 0,
            'deletions': sum(f['deletions'] for f in c['files']) if not c.get('merge') else 0,
            'files': len(c['files']), 'merge': c.get('merge', False),
        }
        for c in sorted(commits, key=lambda c: datetime.fromisoformat(c['date']), reverse=True)[:limit]
    ]


def snapshot(repo_commits: dict[str, list[dict[str, Any]]], *, truncated: dict[str, bool] | None = None) -> dict[str, Any]:
    """Produce a serializable snapshot suitable for local JSON export."""
    all_commits: list[dict[str, Any]] = []
    for repo, commits in repo_commits.items():
        all_commits.extend({**c, 'repo': repo} for c in commits)
    metrics = build_metrics(all_commits)
    return {
        'summary': {
            'repositories': len(repo_commits),
            'commits': metrics['commits'],
            'contributors': metrics['contributors'],
            'truncated_repos': sorted(name for name, value in (truncated or {}).items() if value),
        },
        'metrics': metrics,
        'recent_commits': recent_activity(all_commits),
    }
