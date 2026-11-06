"""Incremental, fully covered annual Git indicators persisted in local SQLite.

No remote I/O. Git batches are bounded; only missing/obsolete analysis versions
are recalculated. These indicators describe changes and collaboration, NOT an
objective productivity/quality score. Commit membership is scoped to an
explicit integration ref and replaced atomically only after a full scan.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable

from .change_quality import CODE_EXTENSIONS, TEST_PATH, parse_name_status, parse_numstat
from .git_engine import GitError, _run, get_branches, git_is_repo

ANALYSIS_VERSION = 3
SCHEMA_VERSION = 1
BATCH_SIZE = 400
_SHA = re.compile(r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')
_EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
_GH_LOGIN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
_GH_ACTOR = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._\-\[\]]{0,100}$')
_GENERATED = re.compile(
    r'(^|/)(?:node_modules|dist|build|bin|obj|coverage|vendor)/|'
    r'(^|/)(?:package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock)$|'
    r'(?:\.min\.(?:js|css)|\.g\.cs|\.generated\.[^/]+|\.Designer\.cs)$',
    re.IGNORECASE,
)
_DOC_EXT = frozenset({'.md', '.rst', '.adoc', '.txt'})
_METRIC_COLUMNS = (
    'gross_churn', 'rename_aware_churn', 'adjusted_churn', 'estimated_move_churn',
    'estimated_space_churn', 'reviewable_churn', 'source_churn', 'test_churn',
    'docs_churn', 'generated_churn', 'moved_files', 'pure_moves',
    'source_files_touched', 'test_files_touched', 'docs_files_touched',
    'generated_files_touched', 'binary_files_touched', 'substantive_commits',
    'cosmetic_only_commits', 'test_touched_commits',
)


def _today() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normal_email(value: str) -> str:
    e = value.strip().lower()
    if not _EMAIL.fullmatch(e):
        raise ValueError('E-mail de autor inválido.')
    return e


class MetricsStore:
    """Private local data store. Only creates new owned database tables."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA busy_timeout = 30000')
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.execute('PRAGMA journal_mode = WAL')
        self._init_schema()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.db.close()

    def _init_schema(self):
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commits (
                repo_id TEXT NOT NULL, sha TEXT NOT NULL, author TEXT NOT NULL,
                email TEXT NOT NULL, authored_at TEXT NOT NULL,
                message TEXT NOT NULL, parents TEXT NOT NULL,
                is_merge INTEGER NOT NULL, analysis_version INTEGER NOT NULL,
                PRIMARY KEY (repo_id, sha)
            );
            CREATE TABLE IF NOT EXISTS commit_metrics (
                repo_id TEXT NOT NULL, sha TEXT NOT NULL,
                gross_churn INTEGER NOT NULL, rename_aware_churn INTEGER NOT NULL,
                adjusted_churn INTEGER NOT NULL, estimated_move_churn INTEGER NOT NULL,
                estimated_space_churn INTEGER NOT NULL, reviewable_churn INTEGER NOT NULL,
                source_churn INTEGER NOT NULL, test_churn INTEGER NOT NULL,
                docs_churn INTEGER NOT NULL, generated_churn INTEGER NOT NULL,
                moved_files INTEGER NOT NULL, pure_moves INTEGER NOT NULL,
                source_files_touched INTEGER NOT NULL, test_files_touched INTEGER NOT NULL,
                docs_files_touched INTEGER NOT NULL, generated_files_touched INTEGER NOT NULL,
                binary_files_touched INTEGER NOT NULL, substantive_commits INTEGER NOT NULL,
                cosmetic_only_commits INTEGER NOT NULL, test_touched_commits INTEGER NOT NULL,
                PRIMARY KEY (repo_id, sha),
                FOREIGN KEY (repo_id, sha) REFERENCES commits(repo_id, sha)
            );
            CREATE TABLE IF NOT EXISTS file_changes (
                repo_id TEXT NOT NULL, sha TEXT NOT NULL, mode TEXT NOT NULL,
                path TEXT NOT NULL, old_path TEXT NOT NULL DEFAULT '',
                additions INTEGER NOT NULL DEFAULT 0, deletions INTEGER NOT NULL DEFAULT 0,
                binary INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (repo_id, sha, mode, path, old_path),
                FOREIGN KEY (repo_id, sha) REFERENCES commits(repo_id, sha)
            );
            CREATE TABLE IF NOT EXISTS ref_commits (
                repo_id TEXT NOT NULL, ref TEXT NOT NULL, sha TEXT NOT NULL,
                PRIMARY KEY (repo_id, ref, sha),
                FOREIGN KEY (repo_id, sha) REFERENCES commits(repo_id, sha)
            );
            CREATE TABLE IF NOT EXISTS ref_state (
                repo_id TEXT NOT NULL, ref TEXT NOT NULL, path TEXT NOT NULL,
                head_sha TEXT NOT NULL, indexed_at TEXT NOT NULL,
                eligible_commits INTEGER NOT NULL, analysis_version INTEGER NOT NULL,
                PRIMARY KEY (repo_id, ref)
            );
            CREATE TABLE IF NOT EXISTS author_aliases (
                email TEXT PRIMARY KEY, canonical_email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS github_identities (
                email TEXT PRIMARY KEY, login TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pull_requests (
                repo_id TEXT NOT NULL, number INTEGER NOT NULL,
                author_login TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL, merged_at TEXT NOT NULL,
                url TEXT NOT NULL, PRIMARY KEY(repo_id, number)
            );
            CREATE TABLE IF NOT EXISTS pr_reviews (
                repo_id TEXT NOT NULL, number INTEGER NOT NULL,
                reviewer_login TEXT NOT NULL, state TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                PRIMARY KEY(repo_id, number, reviewer_login, submitted_at, state),
                FOREIGN KEY(repo_id, number) REFERENCES pull_requests(repo_id, number)
            );
            CREATE TABLE IF NOT EXISTS pr_state (
                repo_id TEXT PRIMARY KEY, fetched_at TEXT NOT NULL,
                received INTEGER NOT NULL, complete INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_commits_author_date ON commits(authored_at, email);
            CREATE INDEX IF NOT EXISTS idx_ref_membership ON ref_commits(repo_id, sha);
            CREATE INDEX IF NOT EXISTS idx_files_commit ON file_changes(repo_id, sha);
            CREATE INDEX IF NOT EXISTS idx_pr_merged ON pull_requests(repo_id, merged_at);
            CREATE INDEX IF NOT EXISTS idx_reviews_date ON pr_reviews(repo_id, submitted_at);
        ''')
        version = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if version and int(version['value']) != SCHEMA_VERSION:
            raise RuntimeError('Schema de métricas local desconhecido; não sobrescreva o banco existente.')
        if not version:
            with self.db:
                self.db.execute("INSERT INTO metadata(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def indexed_shas(self, repo_id: str) -> set[str]:
        return {
            row['sha'] for row in self.db.execute(
                'SELECT sha FROM commits WHERE repo_id=? AND analysis_version=?',
                (repo_id, ANALYSIS_VERSION),
            )
        }

    def save_batch(self, repo_id: str, records: list[dict[str, Any]]):
        """An entire batch of four validated Git output modes is transactional."""
        with self.db:
            for c in records:
                sha = c['sha']
                # Foreign key requires old children to be removed before parent.
                self.db.execute('DELETE FROM file_changes WHERE repo_id=? AND sha=?', (repo_id, sha))
                self.db.execute('DELETE FROM commit_metrics WHERE repo_id=? AND sha=?', (repo_id, sha))
                self.db.execute('''INSERT INTO commits
                    (repo_id,sha,author,email,authored_at,message,parents,is_merge,analysis_version)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(repo_id,sha) DO UPDATE SET
                    author=excluded.author, email=excluded.email,
                    authored_at=excluded.authored_at, message=excluded.message,
                    parents=excluded.parents, is_merge=excluded.is_merge,
                    analysis_version=excluded.analysis_version''',
                    (repo_id, sha, c['author'], c['email'].lower(), c['authored_at'],
                     c['message'], c['parents'], int(c['is_merge']), ANALYSIS_VERSION))
                measures = _measure_commit(c)
                cols = ','.join(_METRIC_COLUMNS)
                placeholders = ','.join('?' for _ in _METRIC_COLUMNS)
                self.db.execute(
                    f'INSERT INTO commit_metrics (repo_id,sha,{cols}) VALUES(?,?,{placeholders})',
                    (repo_id, sha, *(measures[k] for k in _METRIC_COLUMNS)))
                rows = []
                for mode, items in c['files'].items():
                    for item in items:
                        rows.append((repo_id,sha,mode,item['path'],item.get('old_path') or '',
                                     item.get('additions',0),item.get('deletions',0),
                                     int(item.get('binary',False)),item.get('status','')))
                self.db.executemany('''INSERT INTO file_changes
                    (repo_id,sha,mode,path,old_path,additions,deletions,binary,status)
                    VALUES(?,?,?,?,?,?,?,?,?)''', rows)

    def refresh_identity_metadata(self, repo_id: str, history: list[dict[str,Any]]):
        """Apply current Git .mailmap author identity without recomputing diffs.

        Only changes rows when Git metadata differs. The commit SHA keeps its
        existing immutable content metrics and processing version.
        """
        with self.db:
            self.db.executemany('''UPDATE commits SET author=?,email=?,authored_at=?,message=?,parents=?,is_merge=?
                WHERE repo_id=? AND sha=? AND
                (author<>? OR email<>? OR authored_at<>? OR message<>? OR parents<>? OR is_merge<>?)''',
                ((c['author'],c['email'].lower(),c['authored_at'],c['message'],c['parents'],int(c['is_merge']),
                  repo_id,c['sha'],c['author'],c['email'].lower(),c['authored_at'],c['message'],c['parents'],int(c['is_merge']))
                 for c in history))

    def replace_membership(self, repo_id: str, ref: str, repo_path: str,
                           head_sha: str, shas: list[str]):
        with self.db:
            self.db.execute('DELETE FROM ref_commits WHERE repo_id=? AND ref=?', (repo_id,ref))
            self.db.executemany('INSERT INTO ref_commits(repo_id,ref,sha) VALUES(?,?,?)',
                                ((repo_id,ref,sha) for sha in shas))
            self.db.execute('''INSERT INTO ref_state(repo_id,ref,path,head_sha,indexed_at,eligible_commits,analysis_version)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(repo_id,ref) DO UPDATE SET
                path=excluded.path,head_sha=excluded.head_sha,indexed_at=excluded.indexed_at,
                eligible_commits=excluded.eligible_commits,analysis_version=excluded.analysis_version''',
                (repo_id,ref,str(repo_path),head_sha,_today(),len(shas),ANALYSIS_VERSION))

    def set_author_alias(self, email: str, canonical_email: str):
        email = _normal_email(email)
        canonical_email = _normal_email(canonical_email)
        if email == canonical_email:
            with self.db:
                self.db.execute('DELETE FROM author_aliases WHERE email=?', (email,))
            return
        if self.db.execute('SELECT 1 FROM author_aliases WHERE email=?', (canonical_email,)).fetchone():
            raise ValueError('O e-mail canônico não pode ser um alias de outro e-mail.')
        if self.db.execute('SELECT 1 FROM author_aliases WHERE canonical_email=?', (email,)).fetchone():
            raise ValueError('O e-mail indicado já é identidade canônica de outro alias.')
        with self.db:
            self.db.execute('''INSERT INTO author_aliases(email,canonical_email) VALUES(?,?)
                ON CONFLICT(email) DO UPDATE SET canonical_email=excluded.canonical_email''',
                (email,canonical_email))

    def map_github_login(self, email: str, login: str):
        email = _normal_email(email)
        if not _GH_LOGIN.fullmatch(login):
            raise ValueError('Login GitHub inválido.')
        with self.db:
            self.db.execute('''INSERT INTO github_identities(email,login) VALUES(?,?)
                ON CONFLICT(email) DO UPDATE SET login=excluded.login''', (email,login))

    def save_pull_requests(self, repo_id: str, items: list[dict], *, complete: bool=True):
        """Replace one explicit GitHub snapshot atomically, never merge stale PR pages."""
        normalized = []
        for item in items:
            number = item['number']
            if not isinstance(number,int) or number<1 or not _GH_ACTOR.fullmatch(item.get('author_login','')):
                raise ValueError('PR ou autor GitHub inválido.')
            if not str(item.get('url','')).startswith('https://github.com/'):
                raise ValueError('URL de Pull Request inválida.')
            reviews = []
            for review in item.get('reviews',[]):
                login=review.get('login','')
                if login and _GH_ACTOR.fullmatch(login) and review.get('submitted_at'):
                    reviews.append((repo_id,number,login.lower(),str(review.get('state','')).upper(),
                                    review['submitted_at']))
            normalized.append(((repo_id,number,item['author_login'].lower(),
                               str(item.get('state','')).upper(), item.get('created_at') or '',
                               item.get('merged_at') or '',item['url']),reviews))
        with self.db:
            self.db.execute('DELETE FROM pr_reviews WHERE repo_id=?', (repo_id,))
            self.db.execute('DELETE FROM pull_requests WHERE repo_id=?', (repo_id,))
            self.db.executemany('''INSERT INTO pull_requests(repo_id,number,author_login,state,created_at,merged_at,url)
                VALUES(?,?,?,?,?,?,?)''', (p for p,_ in normalized))
            self.db.executemany('''INSERT OR IGNORE INTO pr_reviews
                (repo_id,number,reviewer_login,state,submitted_at) VALUES(?,?,?,?,?)''',
                (review for _,rs in normalized for review in rs))
            self.db.execute('''INSERT INTO pr_state(repo_id,fetched_at,received,complete)
                VALUES(?,?,?,?) ON CONFLICT(repo_id) DO UPDATE SET
                fetched_at=excluded.fetched_at, received=excluded.received, complete=excluded.complete''',
                (repo_id,_today(),len(items),int(complete)))


def _category(path: str) -> str:
    p = Path(path)
    if _GENERATED.search(path):
        return 'generated'
    if TEST_PATH.search(path):
        return 'test'
    if p.suffix.lower() in CODE_EXTENSIONS:
        return 'source'
    if p.suffix.lower() in _DOC_EXT:
        return 'docs'
    return 'other'


def _measure_commit(c: dict[str, Any]) -> dict[str,int]:
    files=c['files']
    stats={k:0 for k in _METRIC_COLUMNS}
    if c['is_merge']:
        return stats
    def churn(items):
        return sum(item['additions']+item['deletions'] for item in items)
    gross=churn(files['raw'])
    aware=churn(files['aware'])
    adjusted=churn(files['adjusted'])
    stats.update(gross_churn=gross,rename_aware_churn=aware,adjusted_churn=adjusted,
                 estimated_move_churn=max(0,gross-aware),estimated_space_churn=max(0,aware-adjusted))
    statuses=files['status']
    stats['moved_files']=sum(s['status'].startswith('R') for s in statuses)
    stats['pure_moves']=sum(s['status']=='R100' for s in statuses)
    stats['binary_files_touched']=sum(s.get('binary',False) for s in files['raw'])
    for s in statuses:
        category=_category(s['path'])
        key=f'{category}_files_touched'
        if key in stats:
            stats[key]+=1
    for f in files['adjusted']:
        category=_category(f['path'])
        metric={'source':'source_churn','test':'test_churn','docs':'docs_churn',
                'generated':'generated_churn'}.get(category)
        if metric:
            stats[metric]+=f['additions']+f['deletions']
    stats['reviewable_churn']=stats['source_churn']+stats['test_churn']
    stats['substantive_commits']=int(adjusted>0)
    stats['cosmetic_only_commits']=int(gross>0 and adjusted==0)
    stats['test_touched_commits']=int(stats['test_files_touched']>0)
    return stats


def choose_integration_ref(repo_path: str | Path) -> str:
    if not git_is_repo(repo_path):
        raise GitError('Repositório Git inválido.')
    refs={row['ref'] for row in get_branches(repo_path)}
    for ref in ('refs/remotes/origin/main','refs/heads/main',
                'refs/remotes/origin/master','refs/heads/master',
                'refs/remotes/origin/development','refs/heads/development'):
        if ref in refs:
            return ref
    if refs:
        # Stable deterministic fallback. Unintegrated feature branches should
        # be selected explicitly rather than silently unioned with main.
        return sorted(refs)[0]
    try:
        _run(repo_path,'rev-parse','--verify','HEAD^{commit}',timeout=15)
    except GitError as exc:
        raise GitError('Nenhuma referência com commits neste repositório.') from exc
    return 'HEAD'


def _ref_head(repo_path: str | Path, ref: str) -> str:
    allowed={row['ref'] for row in get_branches(repo_path)}|{'HEAD'}
    if ref not in allowed:
        raise GitError('Ref de integração não encontrada: selecione uma branch local conhecida.')
    sha=_run(repo_path,'rev-parse','--verify',ref+'^{commit}',timeout=30).decode().strip()
    if not _SHA.fullmatch(sha):
        raise GitError('Ref aponta para um commit inválido.')
    return sha


def _history(repo_path: str | Path, ref: str) -> list[dict[str,str]]:
    fmt='%H%x1f%aN%x1f%aE%x1f%aI%x1f%s%x1f%P'
    content=_run(repo_path,'log','--use-mailmap','--no-patch','-z',f'--format={fmt}',ref,timeout=900)
    rows=[]
    seen=set()
    for entry in content.split(b'\x00'):
        if not entry:
            continue
        fields=entry.decode('utf-8', errors='replace').split('\x1f')
        if len(fields)!=6 or not _SHA.fullmatch(fields[0]):
            raise GitError('Formato inesperado de histórico Git.')
        sha,author,email,authored_at,message,parents=fields
        if sha in seen:
            raise GitError('Commit duplicado no histórico da referência.')
        seen.add(sha)
        rows.append({'sha':sha,'author':author,'email':email,'authored_at':authored_at,
                     'message':message,'parents':parents,'is_merge':len(parents.split())>1})
    return rows


def _split_git_sections(payload: bytes, expected: set[str], kind: str) -> dict[str,list[dict]]:
    """Split on actual SHA marker, not control bytes within normal file paths."""
    sections=re.split(rb'\x1e(?=[0-9a-f]{40}(?:[0-9a-f]{24})?\x00)',payload)
    out={}
    for section in sections:
        if not section.strip(b'\r\n\x00'):
            continue
        sha_raw,sep,body=section.partition(b'\x00')
        if not sep:
            raise GitError('Cabeçalho de lote Git incompleto.')
        sha=sha_raw.decode('ascii', errors='replace')
        if sha not in expected or sha in out:
            raise GitError('Histórico Git alterado ou lote retornou SHA inesperado.')
        body=body.lstrip(b'\r\n')
        out[sha]=parse_name_status(body) if kind=='status' else parse_numstat(body)
    if set(out)!=expected:
        raise GitError('Git retornou um lote incompleto de commits.')
    return out


def _fetch_batch(repo_path: str | Path, records: list[dict[str,Any]]) -> list[dict[str,Any]]:
    shas=[c['sha'] for c in records]
    expected=set(shas)
    if len(expected)!=len(shas):
        raise GitError('SHAs duplicados no lote Git.')
    kinds={
        'raw':['--numstat','--no-renames'],
        'aware':['--numstat','-M'],
        'adjusted':['--numstat','-M','-w'],
        'status':['--name-status','-M'],
    }
    data={}
    for kind,flags in kinds.items():
        payload=_run(repo_path,'log','--no-walk=unsorted','--root','-z',
                     '--format=%x1e%H',*flags,*shas,timeout=900)
        data[kind]=_split_git_sections(payload,expected,kind)
    return [{**c,'files':{kind:rows[c['sha']] for kind,rows in data.items()}} for c in records]


def sync_repository(store: MetricsStore, repo_id: str, repo_path: str | Path, ref: str,
                    *, batch_size: int=BATCH_SIZE, progress_callback=None) -> dict[str,Any]:
    """Scan complete reachable history and index missing commits in bounded batches.

    Existing analysis-version rows are immutable. A failure leaves the prior
    complete ref membership unchanged; successful batches are reusable later.
    """
    if not repo_id or not isinstance(repo_id,str) or len(repo_id)>128:
        raise ValueError('Identificador local do repositório inválido.')
    if not 1<=batch_size<=1000:
        raise ValueError('O tamanho do lote deve estar entre 1 e 1000.')
    repo_path=Path(repo_path).expanduser().resolve()
    if not git_is_repo(repo_path):
        raise GitError('Diretório não contém um repositório Git.')
    initial=_ref_head(repo_path,ref)
    history=_history(repo_path,ref)
    existing=store.indexed_shas(repo_id)
    missing=[c for c in history if c['sha'] not in existing]
    completed=0
    for offset in range(0,len(missing),batch_size):
        batch=_fetch_batch(repo_path,missing[offset:offset+batch_size])
        store.save_batch(repo_id,batch)
        completed+=len(batch)
        if progress_callback is not None:
            progress_callback(completed,len(missing))
    if _ref_head(repo_path,ref)!=initial:
        raise GitError('A referência Git mudou durante a análise. Execute novamente para atualizar a cobertura.')
    store.refresh_identity_metadata(repo_id,history)
    store.replace_membership(repo_id,ref,str(repo_path),initial,[c['sha'] for c in history])
    return {'repo_id':repo_id,'ref':ref,'head_sha':initial,'eligible':len(history),
            'processed':completed,'reused':len(history)-completed,
            'complete':True,'algorithm_version':ANALYSIS_VERSION,'indexed_at':_today()}


def _blank_author(email: str, author: str) -> dict[str,Any]:
    fields={'email':email,'author':author,'aliases':set(), 'commits':0, 'active_days':set(),
            **{k:0 for k in _METRIC_COLUMNS}}
    return fields


def annual_report(store: MetricsStore, selections: Iterable[tuple[str,str]], year: int) -> dict[str,Any]:
    """Aggregate every indexed reachable commit, including monthly trends."""
    if not isinstance(year,int) or not 1900<=year<=2100:
        raise ValueError('Ano deve estar entre 1900 e 2100.')
    refs=list(dict.fromkeys(selections))
    aliases=dict(store.db.execute('SELECT email,canonical_email FROM author_aliases').fetchall())
    github=dict(store.db.execute('SELECT email,login FROM github_identities').fetchall())
    contributors: dict[str,dict[str,Any]]={}
    monthly: dict[tuple[str,str],dict[str,Any]]={}
    totals={k:0 for k in _METRIC_COLUMNS}
    processed=0
    missing_refs=[]
    repo_coverage=[]
    start=f'{year:04d}-01-01'
    end=f'{year+1:04d}-01-01'
    for repo_id,ref in refs:
        state=store.db.execute('''SELECT * FROM ref_state WHERE repo_id=? AND ref=? AND analysis_version=?''',
                               (repo_id,ref,ANALYSIS_VERSION)).fetchone()
        if state is None:
            missing_refs.append({'repo_id':repo_id,'ref':ref})
            continue
        repo_coverage.append({'repo_id':repo_id,'ref':ref,'indexed_at':state['indexed_at'],
                              'head_sha':state['head_sha'],'history_commits':state['eligible_commits']})
        sql='''SELECT c.email,c.author,c.authored_at,m.* FROM ref_commits rc
            JOIN commits c ON c.repo_id=rc.repo_id AND c.sha=rc.sha
            JOIN commit_metrics m ON m.repo_id=c.repo_id AND m.sha=c.sha
            WHERE rc.repo_id=? AND rc.ref=? AND c.authored_at>=? AND c.authored_at<?
            AND c.analysis_version=?'''
        for row in store.db.execute(sql,(repo_id,ref,start,end,ANALYSIS_VERSION)):
            processed+=1
            source_email=row['email'].lower()
            email=aliases.get(source_email,source_email)
            author=contributors.setdefault(email,_blank_author(email,row['author']))
            if source_email == email:  # prefer the canonical author's own display name
                author['author'] = row['author']
            author['aliases'].add(source_email)
            author['commits']+=1
            author['active_days'].add(row['authored_at'][:10])
            month=row['authored_at'][:7]
            m=monthly.setdefault((email,month),{'email':email,'month':month,'commits':0,
                                                  'adjusted_churn':0,'reviewable_churn':0,
                                                  'test_touched_commits':0})
            m['commits']+=1
            for k in _METRIC_COLUMNS:
                val=row[k]
                author[k]+=val
                totals[k]+=val
            m['adjusted_churn']+=row['adjusted_churn']
            m['reviewable_churn']+=row['reviewable_churn']
            m['test_touched_commits']+=row['test_touched_commits']
    # Aggregate GitHub outcomes only when login has been explicitly linked and
    # an explicit PR snapshot is present. Incomplete snapshots remain flagged.
    pr_states={row['repo_id']:dict(row) for row in store.db.execute('SELECT * FROM pr_state')}
    snapshots_complete=bool(refs) and all(r in pr_states and pr_states[r]['complete'] for r,_ in refs)
    for email,rec in contributors.items():
        rec['active_days']=len(rec['active_days'])
        rec['aliases']=sorted(rec['aliases'])
        rec['effective_change_ratio_pct']=round(100*rec['adjusted_churn']/rec['gross_churn'],1) if rec['gross_churn'] else None
        rec['reviewable_ratio_pct']=round(100*rec['reviewable_churn']/rec['gross_churn'],1) if rec['gross_churn'] else None
        rec['substantive_commit_pct']=round(100*rec['substantive_commits']/rec['commits'],1) if rec['commits'] else None
        rec['test_touch_pct']=round(100*rec['test_touched_commits']/rec['commits'],1) if rec['commits'] else None
        login=github.get(email)
        rec['github_login']=login
        rec['merged_prs']=None
        rec['reviews_submitted']=None
        rec['reviews_approved']=None
        if not login or not snapshots_complete:
            continue
        ids=tuple(dict.fromkeys(r for r,_ in refs))
        qs=','.join('?' for _ in ids)
        rec['merged_prs']=store.db.execute(
            f'''SELECT COUNT(*) FROM pull_requests WHERE repo_id IN ({qs})
                AND author_login=? AND merged_at>=? AND merged_at<?''',
            (*ids,login.lower(),start,end),
        ).fetchone()[0]
        reviews=store.db.execute(
            f'''SELECT COUNT(DISTINCT repo_id || ':' || number) AS all_reviews,
                COUNT(DISTINCT CASE WHEN state='APPROVED' THEN repo_id || ':' || number END) AS approvals
                FROM pr_reviews WHERE repo_id IN ({qs}) AND reviewer_login=?
                AND submitted_at>=? AND submitted_at<?''',
            (*ids,login.lower(),start,end),
        ).fetchone()
        rec['reviews_submitted']=reviews['all_reviews']
        rec['reviews_approved']=reviews['approvals']
    return {
        'year':year,'eligible_commits':processed,'processed_commits':processed,
        'coverage_percent':100 if not missing_refs else None,
        'complete':not missing_refs,'missing_repositories':missing_refs,
        'repo_coverage':repo_coverage,'totals':totals,
        'contributors':sorted(contributors.values(),key=lambda r:(-r['commits'],r['email'])),
        'monthly':sorted(monthly.values(),key=lambda r:(r['month'],r['email'])),
        'pr_metadata_complete':snapshots_complete,
        'pr_snapshots':[{**pr_states.get(r,{'repo_id':r,'fetched_at':None,'complete':False})}
                        for r,_ in refs],
        'methodology':'Full reachable Git history per selected integration ref, author-date year; '
                      'churn and review measures are proxies, not productivity/quality rankings.',
    }
