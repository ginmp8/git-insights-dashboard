"""Optional realistic synthetic Git dataset; never touches an existing Git repo.

Run: python scripts/create_demo.py
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gitinsights.catalog import Catalog  # noqa: E402


DEVS = [
    ('Alex', 'alex@demo.local'),
    ('Bianca', 'bianca@demo.local'),
    ('Carla', 'carla@demo.local'),
    ('Diego', 'diego@demo.local'),
]


def run(repo: Path, *args: str, env=None) -> None:
    result = subprocess.run(['git', '-C', str(repo), *args], env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def create(name: str, days: int, app_home: Path) -> Path:
    repo = app_home / 'demo-repos' / name
    if repo.exists():
        raise RuntimeError(f'Repositório sintético já existe, nada foi sobrescrito: {repo}')
    repo.mkdir(parents=True)
    run(repo, 'init', '-b', 'main')
    run(repo, 'config', 'commit.gpgsign', 'false')
    run(repo, 'config', 'user.name', 'Demo')
    run(repo, 'config', 'user.email', 'demo@local.invalid')
    for i in range(days):
        if i == 14:
            run(repo, 'branch', 'release/demo')
        if i == 26:
            run(repo, 'branch', 'feature/analytics')
        author, email = DEVS[(i * 3 + (i // 7)) % len(DEVS)]
        folder = repo / ('src' if i % 5 else 'tests')
        folder.mkdir(exist_ok=True)
        target = folder / (['api.py', 'analytics.py', 'handlers.py', 'metrics.py'][i % 4])
        with target.open('a', encoding='utf-8') as f:
            f.write(f'# synthetic change {i}, repo {name}\n')
        if i % 6 == 0:
            docs = repo / 'README.md'
            with docs.open('a', encoding='utf-8') as f:
                f.write(f'Documented milestone {i}\n')
        run(repo, 'add', '.')
        when = (datetime.now(timezone.utc) - timedelta(days=days-i, hours=i%6)).replace(microsecond=0).isoformat()
        env = os.environ.copy()
        env.update({'GIT_AUTHOR_NAME': author, 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_NAME': author,
                    'GIT_COMMITTER_EMAIL': email, 'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_DATE': when})
        run(repo, 'commit', '-m', f'feat({name}): synthetic milestone {i}', env=env)
    return repo


def main() -> None:
    app_home = Path(os.environ.get('GIT_INSIGHTS_HOME', str(ROOT / '.git-insights-data'))).resolve()
    catalog = Catalog(app_home / 'catalog.json')
    existing = next((p for p in catalog.projects if p['name'] == 'DEMO · Dados fictícios'), None)
    project_id = existing['id'] if existing else catalog.add_project('DEMO · Dados fictícios')
    for repo_name in ('backend-demo', 'frontend-demo', 'infra-demo'):
        p = create(repo_name, 48 if repo_name == 'backend-demo' else 30, app_home)
        catalog.add_local_repo(project_id, str(p), repo_name)
    print('Projeto DEMO criado. Execute: python -m streamlit run app.py')


if __name__ == '__main__':
    main()
