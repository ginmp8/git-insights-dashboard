"""ICE-Git/1: auditable, *relative evidence* index, not objective productivity.

The scoring kernel is pure Python (no Git, SQLite, pandas or Streamlit). Its
optional adapter reads the existing SQLite `file_changes` snapshot, so it never
re-diffs or reaches a network. See docs/features/ice-git.md for the contract.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import groupby
import heapq
import math
from typing import Any, Iterable, Mapping

from .incremental import ANALYSIS_VERSION, MetricsStore, _category, annual_report


@dataclass(frozen=True)
class ICEPolicy:
    """Versioned, configurable policy. Defaults are hypotheses, not benchmarks."""

    methodology: str = 'ICE-Git/1'
    min_cohort: int = 3
    reference_quantile: float = 0.75
    max_lines_per_file: int = 120
    max_weighted_lines_per_commit: float = 150.0
    source_file_weight: float = 1.0
    test_file_weight: float = 0.85
    docs_file_weight: float = 0.65
    support_ratio_target: float = 0.25
    weight_delivery: float = 0.30
    weight_technical_diff: float = 0.30
    weight_support_evidence: float = 0.25
    weight_collaboration: float = 0.15
    max_trace_files: int = 20

    def __post_init__(self):
        if self.methodology != 'ICE-Git/1':
            raise ValueError('Versão de metodologia ICE desconhecida.')
        if not isinstance(self.min_cohort, int) or self.min_cohort < 3:
            raise ValueError('O grupo comparável precisa de pelo menos três pessoas.')
        if not 0 < self.reference_quantile < 1:
            raise ValueError('Quantil de referência inválido.')
        if not isinstance(self.max_lines_per_file, int) or self.max_lines_per_file < 1:
            raise ValueError('Limite por arquivo inválido.')
        if not math.isfinite(self.max_weighted_lines_per_commit) or self.max_weighted_lines_per_commit <= 0:
            raise ValueError('Limite por commit inválido.')
        if not 0 < self.support_ratio_target <= 1:
            raise ValueError('Referência de evidência de suporte inválida.')
        for name in ('source_file_weight','test_file_weight','docs_file_weight',
                     'weight_delivery','weight_technical_diff','weight_support_evidence',
                     'weight_collaboration'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0 or value > 1:
                raise ValueError(f'Peso inválido: {name}.')
        total = sum(getattr(self, k) for k in
                    ('weight_delivery','weight_technical_diff','weight_support_evidence',
                     'weight_collaboration'))
        if abs(total - 1) > 1e-9:
            raise ValueError('A soma dos pesos das quatro dimensões deve ser 1.')
        if not isinstance(self.max_trace_files, int) or not 1 <= self.max_trace_files <= 100:
            raise ValueError('Limite de proveniência inválido.')

    def describe(self) -> dict[str, Any]:
        return asdict(self)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    fractional = pos - lower
    return ordered[lower] * (1 - fractional) + ordered[min(lower + 1, len(ordered) - 1)] * fractional


def _scaled_log(value: float, reference: float) -> float:
    """Logarithmic diminishing returns; saturation at the cohort reference."""
    if value <= 0 or reference <= 0:
        return 0.0
    return min(100.0, 100.0 * math.log1p(value) / math.log1p(reference))


def _validate_signals(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        email = row.get('email')
        if not isinstance(email, str) or not email.strip() or email in seen:
            raise ValueError('Cada identidade Git deve ser única e não vazia.')
        seen.add(email)
        for name in ('commits', 'material_commits', 'bounded_diff_credit', 'supported_commits'):
            number = row.get(name)
            if isinstance(number, bool) or not isinstance(number, (int,float)) or not math.isfinite(number) or number < 0:
                raise ValueError(f'Sinal inválido ({name}) para {email}.')
        if any(not isinstance(row[k], int) or isinstance(row[k], bool)
               for k in ('commits','material_commits','supported_commits')):
            raise ValueError('Contagens Git devem ser inteiras.')
        if row['material_commits'] > row['commits'] or row['supported_commits'] > row['material_commits']:
            raise ValueError('Sinais inconsistentes: suportados ≤ materiais ≤ commits.')
        for name in ('merged_prs', 'reviews_submitted'):
            number = row.get(name)
            if number is not None and (isinstance(number,bool) or not isinstance(number,int) or number < 0):
                raise ValueError(f'Colaboração inválida ({name}).')


def score_cohort(rows: Iterable[Mapping[str, Any]], *, policy: ICEPolicy | None = None,
                 collaboration_complete: bool = False) -> dict[str, Any]:
    """Score a comparable same-year/same-scope cohort from explicit signals.

    Missing GitHub data is NULL, never zero. Scores depend on the cohort's P75;
    the result MUST NOT be interpreted across differing periods, roles or scopes.
    """
    p = policy or ICEPolicy()
    people = [dict(r) for r in rows]
    _validate_signals(people)
    enough = len(people) >= p.min_cohort
    # A mostly-zero cohort can have P75=0 despite some valid material work.
    # Fall back to the P75 of positive observations (never to a fake zero).
    material_values = [float(r['material_commits']) for r in people]
    diff_values = [float(r['bounded_diff_credit']) for r in people]
    material_p75 = _quantile(material_values, p.reference_quantile)
    diff_p75 = _quantile(diff_values, p.reference_quantile)
    if material_p75 == 0 and any(material_values):
        material_p75 = _quantile([v for v in material_values if v > 0],p.reference_quantile)
    if diff_p75 == 0 and any(diff_values):
        diff_p75 = _quantile([v for v in diff_values if v > 0],p.reference_quantile)
    mapped = [r for r in people if r.get('merged_prs') is not None and r.get('reviews_submitted') is not None]
    optional_available = bool(collaboration_complete and enough and len(mapped) >= p.min_cohort)
    merged_p75 = _quantile([float(r['merged_prs']) for r in mapped], p.reference_quantile) if optional_available else 0
    reviewed_p75 = _quantile([float(r['reviews_submitted']) for r in mapped], p.reference_quantile) if optional_available else 0
    core_weight = p.weight_delivery + p.weight_technical_diff + p.weight_support_evidence

    for row in people:
        if not enough:
            row.update(ice_git=None, ice_combined=None, coverage_percent=0,
                       components={'delivery':None,'technical_diff':None,'support_evidence':None,
                                   'collaboration':None}, reason='insufficient_cohort')
            continue
        delivery = _scaled_log(float(row['material_commits']), material_p75)
        technical = _scaled_log(float(row['bounded_diff_credit']), diff_p75)
        supported_ratio = float(row['supported_commits']) / row['material_commits'] if row['material_commits'] else 0
        support = min(100.0, 100.0 * supported_ratio / p.support_ratio_target)
        collaboration = None
        if optional_available and row in mapped:
            collaboration = 0.5 * _scaled_log(float(row['merged_prs']), merged_p75) + 0.5 * _scaled_log(float(row['reviews_submitted']), reviewed_p75)
        base = delivery * p.weight_delivery + technical * p.weight_technical_diff + support * p.weight_support_evidence
        row.update(
            ice_git=round(base / core_weight, 1),
            ice_combined=round(base + collaboration * p.weight_collaboration, 1) if collaboration is not None else None,
            coverage_percent=100 if collaboration is not None else round(core_weight * 100, 1),
            components={'delivery':round(delivery,1), 'technical_diff':round(technical,1),
                        'support_evidence':round(support,1),
                        'collaboration':round(collaboration,1) if collaboration is not None else None},
            reason='experimental_relative_evidence',
        )
    return {
        'methodology':p.methodology, 'status':'ok' if enough else 'insufficient_cohort',
        'policy':p.describe(),
        'references':{'material_commits_p75':round(material_p75,4),
                      'bounded_diff_credit_p75':round(diff_p75,4),
                      'merged_prs_p75':round(merged_p75,4) if optional_available else None,
                      'reviews_submitted_p75':round(reviewed_p75,4) if optional_available else None,
                      'size':len(people), 'collaboration_mapped':len(mapped),
                      'collaboration_comparable':optional_available},
        'contributors':people,
        'warnings':[
            'ICE-Git é um índice RELATIVO de evidências de mudanças Git, não mede produtividade, valor ou qualidade comprovados.',
            'Diferenças, testes e documentação são proxies textuais; números não devem ser usados isoladamente em avaliação individual.',
            'Referências P75 e pesos dependem do grupo comparado e da política. Nunca compare escores de grupos diferentes.',
        ],
    }


def score_annual_store(store: MetricsStore, selections: Iterable[tuple[str, str]], year: int,
                       *, report: dict[str, Any] | None = None,
                       policy: ICEPolicy | None = None) -> dict[str, Any]:
    """Adapt an existing complete SQLite snapshot to ICE-Git without Git calls.

    Uses only the persisted per-SHA, per-file adjusted diff rows. The top file
    evidence list is an EXAMPLE of traceable paths, not the complete history.
    """
    refs = list(dict.fromkeys(selections))
    base = report if report is not None else annual_report(store, refs, year)
    p = policy or ICEPolicy()
    if not base.get('complete'):
        return {
            'methodology':p.methodology,'status':'incomplete_history','complete':False,
            'contributors':[],'warnings':['Indexação Git incompleta ou desatualizada; não publicar scores.'],
        }
    aliases = dict(store.db.execute('SELECT email,canonical_email FROM author_aliases').fetchall())
    by_email: dict[str, dict[str, Any]] = {}
    trace: dict[str, list[tuple[float, int, dict[str, Any]]]] = defaultdict(list)
    sequence = 0
    start = f'{year:04d}-01-01'; end = f'{year + 1:04d}-01-01'
    weights = {'source':p.source_file_weight,'test':p.test_file_weight,'docs':p.docs_file_weight}
    cap_scale = math.log1p(p.max_weighted_lines_per_commit)
    for repo_id, ref in refs:
        sql = '''SELECT c.sha,c.email,fc.path,fc.additions,fc.deletions,fc.binary
            FROM ref_commits rc JOIN commits c ON c.repo_id=rc.repo_id AND c.sha=rc.sha
            LEFT JOIN file_changes fc ON fc.repo_id=c.repo_id AND fc.sha=c.sha AND fc.mode='adjusted'
            WHERE rc.repo_id=? AND rc.ref=? AND c.authored_at>=? AND c.authored_at<?
            AND c.analysis_version=? ORDER BY c.sha,fc.path'''
        cursor = store.db.execute(sql, (repo_id,ref,start,end,ANALYSIS_VERSION))
        for sha, items in groupby(cursor, key=lambda r:r['sha']):
            per_commit = list(items)
            canonical = aliases.get(per_commit[0]['email'].lower(),per_commit[0]['email'].lower())
            record = by_email.setdefault(canonical, {'email':canonical,'material_commits':0,
                                                       'bounded_diff_credit':0.0,'supported_commits':0})
            weighted = 0.0
            categories = set()
            for item in per_commit:
                path = item['path']
                if path is None or item['binary']:
                    continue
                category = _category(path)
                if category not in weights:
                    continue  # generated/other/unknown files do not produce credit
                lines = (item['additions'] or 0) + (item['deletions'] or 0)
                if lines <= 0:
                    continue
                effective = min(lines,p.max_lines_per_file)
                file_weight = effective * weights[category]
                weighted += file_weight
                categories.add(category)
                evidence = {'repo_id':repo_id,'sha':sha,'path':path,'category':category,
                            'adjusted_lines':lines,'bounded_lines':effective,
                            'weighted_lines':round(file_weight,2)}
                sequence += 1
                heap = trace[canonical]
                entry = (file_weight,sequence,evidence)
                if len(heap) < p.max_trace_files:
                    heapq.heappush(heap,entry)
                elif entry[0] > heap[0][0]:
                    heapq.heapreplace(heap,entry)
            if weighted > 0:
                record['material_commits'] += 1
                record['bounded_diff_credit'] += math.log1p(min(weighted,p.max_weighted_lines_per_commit)) / cap_scale
                record['supported_commits'] += int('test' in categories or 'docs' in categories)
    rows=[]
    for person in base['contributors']:
        email=person['email']
        raw=by_email.get(email,{'material_commits':0,'bounded_diff_credit':0.0,'supported_commits':0})
        path_evidence=[e for _,__,e in sorted(trace[email], key=lambda r:(-r[0],r[2]['sha'],r[2]['path']))]
        rows.append({'email':email, 'author':person['author'], 'commits':person['commits'],
                     **raw, 'bounded_diff_credit':round(raw['bounded_diff_credit'],6),
                     'merged_prs':person.get('merged_prs'),
                     'reviews_submitted':person.get('reviews_submitted'),
                     'file_evidence':path_evidence})
    result=score_cohort(rows,policy=p,collaboration_complete=bool(base.get('pr_metadata_complete')))
    result['year']=year;result['complete']=True
    result['scope']=[{'repo_id':r,'ref':ref} for r,ref in refs]
    result['coverage']={'git':'complete_for_selected_refs','pr':'complete' if base.get('pr_metadata_complete') else 'missing_or_partial'}
    return result
