"""Git Insights Local: Streamlit dashboards over read-only Git histories.

Start with `python -m streamlit run app.py`. Remote reads are explicit actions.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gitinsights.analytics import build_metrics, filter_commits, recent_activity, snapshot
from gitinsights.catalog import Catalog, CatalogError
from gitinsights.git_engine import GitError, get_branches, get_commits, get_origin_url, get_repo_summary, ref_commit_counts, compare_branches
from gitinsights.github import list_pull_requests, parse_github_repo
from gitinsights.export import csv_bytes
from gitinsights.remote import clone_mirror, refresh_mirror
from gitinsights.ui_repository_picker import render_github_picker
from gitinsights.ui_change_quality import render_change_quality
from gitinsights.ui_annual import render_annual


st.set_page_config(page_title='Git Insights | Local', page_icon=':bar_chart:', layout='wide', initial_sidebar_state='expanded')

ROOT = Path(__file__).resolve().parent
DATA_HOME = Path(os.environ.get('GIT_INSIGHTS_HOME', str(ROOT / '.git-insights-data'))).expanduser().resolve()
CATALOG_FILE = DATA_HOME / 'catalog.json'
MIRROR_HOME = DATA_HOME / 'mirrors'
ACCENT = '#B1E26C'
BLUE = '#70A8E8'
RED = '#E47776'
SOFT = '#8B9BAA'


@st.cache_data(ttl=300, max_entries=30, show_spinner=False)
def load_commits(path: str, branch: str | None, days: int | None, max_commits: int | None):
    return get_commits(path, branch=branch, since_days=days, max_count=max_commits)


@st.cache_data(ttl=120, max_entries=80, show_spinner=False)
def load_branch_details(path: str):
    refs = get_branches(path)
    counts = ref_commit_counts(path, [item['ref'] for item in refs], max_refs=80)
    for item in refs:
        item['commits_reachable'] = counts.get(item['ref'])
    return refs


def plot_style(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=height, margin=dict(l=12, r=15, t=24, b=24),
        font=dict(color='#C6D2DA', size=12),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor='#28343D', zeroline=False),
        legend=dict(orientation='h', y=1.16, x=0),
        hoverlabel=dict(bgcolor='#1F2C36', font_size=12),
    )
    return fig


def bar_figure(rows: list[dict], label: str, value: str, *, color: str = ACCENT, height: int = 325, horizontal: bool = False):
    fig = go.Figure()
    rows = rows[:15]
    if horizontal:
        fig.add_trace(go.Bar(x=[r[value] for r in reversed(rows)], y=[r[label] for r in reversed(rows)], orientation='h', marker_color=color, hovertemplate='%{y}: %{x:,}<extra></extra>'))
    else:
        fig.add_trace(go.Bar(x=[r[label] for r in rows], y=[r[value] for r in rows], marker_color=color, hovertemplate='%{x}: %{y:,}<extra></extra>'))
    return plot_style(fig, height)


def activity_figure(days: list[dict], height: int = 325) -> go.Figure:
    fig = go.Figure()
    if days:
        counts = {d['date']: d['commits'] for d in days}
        start = date.fromisoformat(days[0]['date'])
        end = date.fromisoformat(days[-1]['date'])
        # Bound dense chart rendering even for years-long history.
        if (end - start).days <= 1000:
            axis = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            x = [d.isoformat() for d in axis]
        else:
            x = sorted(counts)
        y = [counts.get(i, 0) for i in x]
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', line=dict(color=ACCENT, width=2), fill='tozeroy', fillcolor='rgba(177,226,108,.11)', hovertemplate='%{x}<br>%{y} commits<extra></extra>'))
    fig.update_layout(xaxis_title=None, yaxis_title='Commits')
    return plot_style(fig, height)


def churn_figure(rows: list[dict], label_key: str, *, height=330) -> go.Figure:
    rows = rows[:12]
    fig = go.Figure()
    fig.add_bar(x=[r[label_key] for r in rows], y=[r['additions'] for r in rows], name='Adições', marker_color=ACCENT)
    fig.add_bar(x=[r[label_key] for r in rows], y=[-r['deletions'] for r in rows], name='Remoções', marker_color=RED)
    fig.update_layout(barmode='relative', yaxis_title='Linhas')
    return plot_style(fig, height)


def heatmap_figure(commits: list[dict]) -> go.Figure:
    weekdays = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
    grid = [[0 for _ in range(24)] for _ in range(7)]
    for c in commits:
        dt = datetime.fromisoformat(c['date'])
        grid[dt.weekday()][dt.hour] += 1
    fig = go.Figure(go.Heatmap(
        z=grid, x=[f'{i:02d}h' for i in range(24)], y=weekdays,
        colorscale=[[0, '#18282D'], [0.2, '#254C49'], [0.65, '#609D63'], [1, ACCENT]],
        colorbar=dict(title='Commits', thickness=9),
        hovertemplate='%{y} • %{x}<br>%{z} commits<extra></extra>',
    ))
    fig.update_layout(yaxis=dict(autorange='reversed'), xaxis_title='Hora do commit (fuso registrado pelo autor)')
    return plot_style(fig, 295)


def dataframe(rows: list[dict], *, height=330) -> None:
    if not rows:
        st.info('Nenhum registro para os filtros atuais.')
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=height)


def short_number(value: int) -> str:
    return f'{value:,}'.replace(',', '.')


def init_catalog() -> Catalog:
    try:
        return Catalog(CATALOG_FILE)
    except CatalogError as exc:
        st.error(f'Falha ao abrir o catálogo: {exc}')
        st.stop()
        raise


def sidebar_catalog(catalog: Catalog) -> tuple[dict | None, list[dict]]:
    with st.sidebar:
        st.markdown('## GIT INSIGHTS')
        st.caption('ANALYTICS / LOCAL WORKSPACE')
        st.divider()
        project_ids = [p['id'] for p in catalog.projects]
        if st.session_state.pop('pending-project-reset', False):
            st.session_state['project-picker'] = project_ids[0] if project_ids else None
        if 'pending-project-selection' in st.session_state:
            st.session_state['project-picker'] = st.session_state.pop('pending-project-selection')
        selected_id = st.selectbox('Projeto', project_ids, format_func=lambda id: catalog.get_project(id)['name'], index=0 if project_ids else None, placeholder='Selecione um projeto', key='project-picker')
        project = catalog.get_project(selected_id) if selected_id else None
        with st.expander('Adicionar projeto', expanded=not bool(project)):
            with st.form('new-project', clear_on_submit=True):
                project_name = st.text_input('Nome do projeto', placeholder='Ex.: Plataforma / Corporate')
                if st.form_submit_button('Criar projeto', width='stretch'):
                    try:
                        new_id = catalog.add_project(project_name)
                        st.session_state['pending-project-selection'] = new_id
                        st.rerun()
                    except CatalogError as exc:
                        st.error(str(exc))
        if not project:
            return None, []

        repos = project['repos']
        with st.expander('Remover projeto do catálogo'):
            with st.form('remove-project'):
                confirmed = st.checkbox(f"Remover apenas o cadastro de '{project['name']}'")
                if st.form_submit_button('Remover projeto'):
                    if confirmed:
                        catalog.remove_project(project['id'])
                        st.session_state['pending-project-reset'] = True
                        st.rerun()
                    else:
                        st.warning('Confirme antes de remover o cadastro.')
        with st.expander('Adicionar repositório', expanded=not bool(repos)):
            mode = st.radio(
                'Origem', ['GitHub CLI · escolher da lista', 'Pasta local', 'GitHub · URL manual'],
                horizontal=False, key='repo-source',
            )
            if mode == 'GitHub CLI · escolher da lista':
                if render_github_picker(catalog, project['id'], repos, MIRROR_HOME):
                    load_commits.clear()
                    load_branch_details.clear()
                    # Newly imported repos must be eligible for default selection.
                    st.session_state.pop(f'repo-filter-{project["id"]}', None)
                    st.rerun()
            elif mode == 'Pasta local':
                with st.form('add-local', clear_on_submit=True):
                    local = st.text_input('Caminho absoluto', placeholder=r'C:\dev\meu-repo ou /home/me/repositorio')
                    display = st.text_input('Apelido opcional')
                    if st.form_submit_button('Adicionar pasta', width='stretch'):
                        try:
                            catalog.add_local_repo(project['id'], local, display)
                            st.rerun()
                        except (CatalogError, OSError) as exc:
                            st.error(str(exc))
            else:
                st.caption('Modo avançado: um clique em Clonar faz a conexão Git. '
                           'Na opção GitHub CLI, a URL não é necessária.')
                with st.form('add-mirror', clear_on_submit=True):
                    url = st.text_input('URL GitHub', placeholder='https://github.com/owner/repo.git')
                    display = st.text_input('Apelido opcional', key='remote-label')
                    if st.form_submit_button('Clonar espelho e adicionar', width='stretch'):
                        try:
                            if url.strip().lower().removesuffix('.git') in {
                                r.get('url', '').lower().removesuffix('.git') for r in repos if r['kind'] == 'mirror'
                            }:
                                raise CatalogError('Este repositório já está cadastrado neste projeto.')
                            with st.spinner('Clonando espelho Git...'):
                                target = clone_mirror(url, MIRROR_HOME)
                                catalog.add_mirror_repo(project['id'], str(target), url,
                                                        display or url.rstrip('/').split('/')[-1].removesuffix('.git'))
                            st.rerun()
                        except (GitError, CatalogError, OSError) as exc:
                            st.error(str(exc))
        if repos:
            with st.expander('Gerenciar repositórios'):
                with st.form('unregister-repo'):
                    chosen = st.selectbox('Remover somente do catálogo', [r['id'] for r in repos], format_func=lambda id: next(r['name'] for r in repos if r['id'] == id))
                    accept = st.checkbox('Entendo que isso não apaga arquivos Git.')
                    if st.form_submit_button('Remover entrada', width='stretch'):
                        if accept:
                            catalog.remove_repo(project['id'], chosen)
                            st.rerun()
                        else:
                            st.warning('Confirme a remoção do catálogo.')
            st.caption(f'{len(repos)} repositório(s) cadastrado(s)')
            if st.button('Recalcular dados locais', width='stretch', help='Limpa o cache de leitura. Não faz fetch nem modifica repositórios.'):
                load_commits.clear()
                load_branch_details.clear()
                st.rerun()
            mirrors = [r for r in repos if r['kind'] == 'mirror']
            if mirrors:
                with st.expander('Atualização externa'):
                    st.warning('Isto consulta servidores GitHub. Ação explícita e independente da leitura local.')
                    if st.button('Fazer fetch dos espelhos', width='stretch'):
                        errors = []
                        with st.spinner('Atualizando espelhos...'):
                            for repo in mirrors:
                                try:
                                    refresh_mirror(repo['path'], MIRROR_HOME, use_gh_auth=repo.get('auth_via_gh', False))
                                except GitError as exc:
                                    errors.append(f'{repo["name"]}: {exc}')
                        load_commits.clear()
                        load_branch_details.clear()
                        if errors:
                            st.error('\n'.join(errors))
                        else:
                            st.success('Espelhos atualizados. Atualize os filtros para recalcular.')
            repo_labels = {r['id']: f'{r["name"]} · {r["id"][:5]}' for r in repos}
            selected_repos = st.multiselect('Repositórios', [r['id'] for r in repos], default=[r['id'] for r in repos], format_func=lambda id: repo_labels[id], key=f'repo-filter-{project["id"]}')
        else:
            selected_repos = []
        st.divider()
        st.caption('OFFLINE POR PADRÃO · ANALISADOR SOMENTE LEITURA')
        return project, [r for r in repos if r['id'] in selected_repos]


def sidebar_filters(selected_repos: list[dict]):
    with st.sidebar:
        st.markdown('### Filtros de análise')
        branch_options: list[str | None] = [None]
        repo_branches: dict[str, list[dict]] = {}
        for repo in selected_repos:
            try:
                branches = get_branches(repo['path'])
                repo_branches[repo['id']] = branches
                branch_options.extend(b['ref'] for b in branches if b['ref'] not in branch_options)
            except GitError as exc:
                st.warning(f'{repo["name"]}: {exc}')
                repo_branches[repo['id']] = []
        branch = st.selectbox('Branch', branch_options, format_func=lambda ref: 'Todas as branches (sem duplicar commits)' if ref is None else ref, key='branch-filter')
        days_label = st.selectbox('Período de ingestão', ['Últimos 30 dias', 'Últimos 90 dias', 'Últimos 180 dias', 'Últimos 365 dias', 'Todo o histórico'], index=1)
        days = {'Últimos 30 dias': 30, 'Últimos 90 dias': 90, 'Últimos 180 dias': 180, 'Últimos 365 dias': 365, 'Todo o histórico': None}[days_label]
        limit_label = st.selectbox('Máximo de commits por repositório', ['2.000', '5.000', '10.000', 'Sem limite'], index=1)
        limit = {'2.000': 2000, '5.000': 5000, '10.000': 10000, 'Sem limite': None}[limit_label]
        folder = st.text_input('Pasta / prefixo (opcional)', placeholder='Ex.: src/ ou apps/api/')
        repo_folders = {}
        if len(selected_repos) > 1:
            with st.expander('Pastas específicas por repositório'):
                st.caption('Se preenchido, substitui o prefixo global apenas neste repositório.')
                for repo in selected_repos:
                    repo_folders[repo['id']] = st.text_input(
                        f"{repo['name']} · {repo['id'][:5]}",
                        placeholder='Ex.: src/service/', key=f'repo-folder-{repo["id"]}',
                    )
        use_exact = st.toggle('Filtrar por datas específicas', value=False)
        start_date = end_date = None
        if use_exact:
            start_date = st.date_input('Data inicial', value=date.today() - timedelta(days=90))
            end_date = st.date_input('Data final', value=date.today())
            if start_date > end_date:
                st.error('Data inicial maior que a final.')
                st.stop()
        st.caption('Branches remotas somente se já existirem no clone local. Não ocorre fetch automático.')
        return branch, days, limit, folder, repo_folders, (start_date.isoformat() if start_date else None), (end_date.isoformat() if end_date else None), repo_branches


def render_overview(metrics, commits, repo_count):
    cols = st.columns(6, gap='small')
    kpis = [
        ('Repositórios', repo_count), ('Commits', metrics['commits']),
        ('Contribuidores', metrics['contributors']), ('Adições', metrics['additions']),
        ('Remoções', metrics['deletions']), ('Churn total', metrics['churn']),
    ]
    for col, (label, val) in zip(cols, kpis):
        with col:
            st.metric(label, short_number(val))
    st.caption('Churn = adições + remoções históricas. Não corresponde ao tamanho atual do código.')
    left, right = st.columns([1.5, 1], gap='large')
    with left:
        st.subheader('Evolução de commits')
        st.plotly_chart(activity_figure(metrics['days']), width='stretch', key='activity-overview')
    with right:
        st.subheader('Contribuidores mais ativos')
        st.plotly_chart(bar_figure(metrics['authors'], 'author', 'commits', horizontal=True), width='stretch', key='contributors-overview')
    bottom_left, bottom_right = st.columns([1.15, 1], gap='large')
    with bottom_left:
        st.subheader('Movimento de linhas por repositório')
        if metrics['repos']:
            st.plotly_chart(churn_figure(metrics['repos'], 'repo'), width='stretch', key='churn-overview')
        else:
            st.info('Sem alterações no período.')
    with bottom_right:
        st.subheader('Arquivos mais modificados')
        rows = [{'Repositório': r['repo'], 'Arquivo': r['file'], 'Mudanças': r['touches'], 'Churn': r['additions']+r['deletions']} for r in metrics['hotspots'][:9]]
        dataframe(rows, height=345)


def render_contributors(metrics, commits):
    st.subheader('Contribuições e atividade')
    st.caption('Identidades agrupadas por e-mail do autor; respeita .mailmap quando presente.')
    rows = [{
        'Autor': r['author'], 'E-mail': r['email'], 'Commits': r['commits'],
        'Repositórios': r['repos'], 'Adições': r['additions'],
        'Remoções': r['deletions'], 'Churn': r['churn'],
    } for r in metrics['authors']]
    dataframe(rows, height=340)
    l, r = st.columns(2, gap='large')
    with l:
        st.markdown('#### Commits por autor')
        st.plotly_chart(bar_figure(metrics['authors'], 'author', 'commits', horizontal=True), width='stretch', key='contrib-commits')
    with r:
        st.markdown('#### Churn por autor')
        st.plotly_chart(churn_figure(metrics['authors'], 'author'), width='stretch', key='contrib-churn')
    st.markdown('#### Horários de atividade')
    st.plotly_chart(heatmap_figure(commits), width='stretch', key='contrib-heatmap')


def render_files(metrics):
    st.subheader('Arquivos e hotspots')
    st.caption('Hotspot = frequência de alteração. Não constitui prova de defeito ou dívida técnica.')
    hotspots = [{
        'Repositório': r['repo'], 'Arquivo': r['file'], 'Alterações': r['touches'],
        'Adições': r['additions'], 'Remoções': r['deletions'], 'Churn': r['additions'] + r['deletions'],
    } for r in metrics['hotspots']]
    dataframe(hotspots, height=380)
    left, right = st.columns(2, gap='large')
    with left:
        st.markdown('#### 12 arquivos mais alterados')
        rows = [{'path': f"{r['repo']}/{r['file']}", 'touches': r['touches']} for r in metrics['hotspots'][:12]]
        st.plotly_chart(bar_figure(rows, 'path', 'touches', horizontal=True, height=385), width='stretch', key='files-hotspots')
    with right:
        st.markdown('#### Tipos de arquivo')
        if metrics['file_types']:
            fig = go.Figure(go.Pie(
                labels=[r['extension'] for r in metrics['file_types'][:10]],
                values=[r['files_touched'] for r in metrics['file_types'][:10]], hole=0.63,
                marker=dict(colors=['#B1E26C', '#70A8E8', '#DBAA71', '#8F83E8', '#E47776', '#66B6B2', '#C7CD86', '#E29DB6', '#7EAAC2', '#A8BAC0']),
                textinfo='label+percent', sort=False,
            ))
            st.plotly_chart(plot_style(fig, 385), width='stretch', key='file-types')
        else:
            st.info('Sem arquivos alterados.')
    st.markdown('#### Detalhamento por extensão')
    dataframe([{
        'Extensão': r['extension'], 'Toques': r['files_touched'],
        'Adições': r['additions'], 'Remoções': r['deletions'],
    } for r in metrics['file_types']], height=270)


def render_branches(selected_repos: list[dict], repo_labels: dict[str, str]):
    st.subheader('Branches disponíveis localmente')
    st.caption('Commits alcançáveis consideram todo o histórico da branch, independentemente do filtro de período. Eles podem se repetir entre branches; não some esta coluna.')
    rows = []
    omitted = 0
    for repo in selected_repos:
        try:
            items = load_branch_details(repo['path'])
            for item in items:
                rows.append({
                    'Repositório': repo_labels[repo['id']], 'Branch': item['name'],
                    'Tipo': item['kind'], 'Commits alcançáveis': item['commits_reachable'],
                    'Atualização': item['updated'], 'HEAD': item['sha'][:10],
                })
            omitted += max(0, len(items) - 80)
        except GitError as exc:
            st.warning(f'{repo["name"]}: {exc}')
    dataframe(rows, height=420)
    if omitted:
        st.warning(f'Contagem indisponível para {omitted} branch(es) além do limite de 80 por repositório.')
    st.markdown('#### Resumo por repositório')
    summary = []
    for repo in selected_repos:
        try:
            meta = get_repo_summary(repo['path'])
            summary.append({'Repositório': repo_labels[repo['id']], 'Branches locais': meta['local_branches'], 'Branches remotas': meta['remote_branches'], 'Tags': meta['tags'], 'Origem': 'Espelho' if repo['kind']=='mirror' else 'Pasta local'})
        except GitError as exc:
            st.warning(f'{repo["name"]}: {exc}')
    dataframe(summary, height=210)
    st.markdown('#### Comparação entre branches')
    if not selected_repos:
        return
    repo_id = st.selectbox('Repositório para comparar', [r['id'] for r in selected_repos],
                           format_func=lambda id: repo_labels[id], key='compare-repo')
    picked = next(r for r in selected_repos if r['id'] == repo_id)
    refs = [b['ref'] for b in get_branches(picked['path'])]
    if len(refs) < 2:
        st.info('Este repositório precisa de pelo menos duas branches conhecidas.')
        return
    base_col, head_col = st.columns(2)
    with base_col:
        base_ref = st.selectbox('Base', refs, index=0, key='compare-base')
    with head_col:
        head_ref = st.selectbox('Destino', refs, index=1, key='compare-head')
    compare_key = (picked['path'], base_ref, head_ref)
    if st.button('Comparar branches (somente leitura)'):
        try:
            with st.spinner('Calculando divergência e diff...'):
                comparison = compare_branches(*compare_key)
            st.session_state['branch-comparison'] = (compare_key, comparison)
        except GitError as exc:
            st.error(str(exc))
    saved = st.session_state.get('branch-comparison')
    if saved and saved[0] == compare_key:
        result = saved[1]
        x, y, z = st.columns(3)
        x.metric('Commits apenas na base', result['behind'])
        y.metric('Commits apenas no destino', result['ahead'])
        z.metric('Arquivos no diff', len(result['files']) if not result['truncated'] else '500+')
        if result['truncated']:
            st.warning('Diferenças limitadas aos 500 arquivos com maior churn.')
        dataframe(result['files'], height=285)
        st.caption('O diff usa o merge-base (`base...destino`), não a soma de alterações de cada commit.')


def render_prs(project: dict, repos: list[dict]):
    st.subheader('Pull requests · GitHub')
    st.caption('Consulta externa opcional, somente leitura. Usa o gh CLI já autenticado. Nenhum PR é consultado ao abrir o dashboard.')
    eligible = {}
    for repo in repos:
        upstream = repo.get('url') or get_origin_url(repo['path'])
        name = parse_github_repo(upstream)
        if name:
            eligible[repo['id']] = name
    if not eligible:
        st.info('Nenhum repositório possui um origin GitHub compatível. Para PRs, configure um origin GitHub no Git local ou adicione um espelho GitHub.')
        return
    selected = st.multiselect('Consultar repositórios', list(eligible), default=list(eligible), format_func=lambda id: eligible[id], key='gh-repo-select')
    limit = st.number_input('Máximo de PRs por repositório', 1, 200, 50)
    session_key = 'gh-prs-' + project['id']
    if st.button('Consultar PRs no GitHub (rede)', type='primary'):
        records = []
        errors = []
        with st.spinner('Consultando o GitHub via gh...'):
            for id in selected:
                try:
                    records.extend(list_pull_requests(eligible[id], int(limit)))
                except (GitError, ValueError) as exc:
                    errors.append(f'{eligible[id]}: {exc}')
        st.session_state[session_key] = records
        st.session_state[session_key + '-errors'] = errors
    if st.session_state.get(session_key + '-errors'):
        st.warning('\n'.join(st.session_state[session_key + '-errors']))
    records = st.session_state.get(session_key)
    if records is None:
        st.info('Selecione os repositórios e clique em Consultar PRs.')
        return
    if not records:
        st.info('Nenhum PR retornado.')
        return
    states = Counter(r['Estado'] for r in records)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Total retornado', len(records))
    m2.metric('Abertos', states.get('OPEN', 0))
    m3.metric('Mesclados', states.get('MERGED', 0))
    m4.metric('Fechados', states.get('CLOSED', 0))
    dataframe(records, height=490)


def render_commits(commits: list[dict], repo_commits: dict[str, list[dict]], truncated: dict[str, bool]):
    st.subheader('Histórico de commits')
    rows = recent_activity(commits, limit=1000)
    dataframe([{
        'Repositório': r['repo'], 'Data': r['date'], 'Autor': r['author'],
        'Mensagem': r['message'], 'SHA': r['sha'], 'Adições': r['additions'],
        'Remoções': r['deletions'], 'Arquivos': r['files'], 'Merge': r['merge'],
    } for r in rows], height=460)
    st.markdown('#### Exportar filtros atuais')
    data = snapshot(repo_commits, truncated=truncated)
    data['generated_at'] = datetime.now().astimezone().isoformat()
    json_data = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    csv_data = csv_bytes(rows)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.download_button('Exportar relatório JSON', json_data, 'git-insights-report.json', 'application/json', width='stretch', on_click='ignore')
    with c2:
        st.download_button('Exportar commits CSV', csv_data, 'git-insights-commits.csv', 'text/csv', width='stretch', on_click='ignore')
    st.caption('O JSON inclui métricas agregadas e até 200 commits recentes. O CSV inclui até 1.000 commits; os totais consideram todos os commits carregados.')


def main() -> None:
    catalog = init_catalog()
    project, selected_repos = sidebar_catalog(catalog)
    st.title('Git Insights')
    st.caption('ENGINEERING INTELLIGENCE  /  LOCAL-FIRST  /  READ-ONLY')
    if not project:
        st.info('Crie um projeto na barra lateral e escolha repositórios pelo GitHub CLI ou adicione pastas locais.')
        st.markdown('#### O que o dashboard permite')
        st.write('Múltiplos repositórios por projeto · branches locais e remotas · contribuições · churn · hotspots · tendências · exportação · PRs opcionais.')
        return
    st.markdown(f'### {project["name"]}')
    if not selected_repos:
        st.warning('Adicione um repositório ao projeto ou selecione repositórios na barra lateral.')
        return
    branch, days, limit, folder, repo_folders, start_date, end_date, branch_map = sidebar_filters(selected_repos)
    repo_labels = {r['id']: f"{r['name']} · {r['id'][:5]}" for r in selected_repos}
    repo_commits = {}
    truncated = {}
    missing = []
    for repo in selected_repos:
        if branch is not None and branch not in {b['ref'] for b in branch_map.get(repo['id'], [])}:
            missing.append(repo_labels[repo['id']])
            continue
        try:
            with st.spinner(f'Lendo histórico: {repo["name"]}...'):
                commits, cut = load_commits(repo['path'], branch, days, limit)
            name = repo_labels[repo['id']]
            repo_commits[name] = commits
            truncated[name] = cut
        except (GitError, OSError, ValueError) as exc:
            st.error(f'Falha ao ler {repo["name"]}: {exc}')
    if missing:
        st.warning('A branch escolhida não existe em: ' + ', '.join(missing))
    cut_repos = [name for name, value in truncated.items() if value]
    if cut_repos:
        st.warning('Visões legadas com limite de commits: ' + ', '.join(cut_repos) + '. A aba Contribuição anual usa índice SQLite separado, sem esse limite.')
    if not repo_commits:
        st.error('Nenhum repositório selecionado pôde ser analisado.')
        return
    all_rows = [dict(c, repo=name) for name, commits in repo_commits.items() for c in commits]
    email_map = {c['email']: c['author'] for c in all_rows}
    with st.sidebar:
        author_emails = st.multiselect('Autor', sorted(email_map), format_func=lambda e: f'{email_map[e]} ({e})', key=f'author-filter-{project["id"]}')
    if start_date and end_date and days is not None:
        st.caption('O filtro de datas específicas atua dentro do período de ingestão selecionado. Para datas antigas, selecione Todo o histórico.')
    selected = {}
    for repo in selected_repos:
        repo_name = repo_labels[repo['id']]
        if repo_name not in repo_commits:
            continue
        selected[repo_name] = filter_commits(
            repo_commits[repo_name],
            emails=set(author_emails) if author_emails else None,
            folder=repo_folders.get(repo['id']) or folder,
            start_date=start_date, end_date=end_date,
        )
    filtered = [dict(c, repo=repo) for repo, commits in selected.items() for c in commits]
    metrics = build_metrics(filtered)
    if not filtered:
        st.info('Nenhum commit corresponde aos filtros selecionados. As abas de branches e PRs continuam disponíveis.')
    st.divider()
    tab_annual, tab_overview, tab_contrib, tab_files, tab_quality, tab_branches, tab_prs, tab_commits = st.tabs([
        'Contribuição anual', 'Visão geral', 'Contribuidores', 'Arquivos', 'Mudanças ajustadas',
        'Branches', 'Pull requests', 'Commits e exportação',
    ])
    with tab_annual:
        render_annual(project, selected_repos, DATA_HOME / 'annual-metrics.sqlite3')
    with tab_overview:
        render_overview(metrics, filtered, len(repo_commits))
    with tab_contrib:
        render_contributors(metrics, filtered)
    with tab_files:
        render_files(metrics)
    with tab_quality:
        render_change_quality(project, selected, selected_repos, repo_labels)
    with tab_branches:
        render_branches(selected_repos, repo_labels)
    with tab_prs:
        render_prs(project, selected_repos)
    with tab_commits:
        render_commits(filtered, selected, truncated)
    st.divider()
    st.caption('Fonte: histórico Git dos clones cadastrados. Métricas e arquivos são calculados localmente; GitHub é opcional e acionado manualmente.')


if __name__ == '__main__':
    main()
