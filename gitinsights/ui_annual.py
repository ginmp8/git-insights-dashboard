"""Annual per-developer evidence panels backed by the local SQLite cache."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from .git_engine import GitError, get_branches
from .export import csv_bytes
from .github import list_pr_collaboration, parse_github_repo
from .incremental import MetricsStore, annual_report, choose_integration_ref, sync_repository


def _table_rows(report: dict) -> list[dict]:
    """Display names reflect observed signals, not an objective quality rating."""
    rows=[]
    for a in report['contributors']:
        rows.append({
            'Desenvolvedor (Git)':a['author'], 'E-mail (identidade)':a['email'],
            'Commits integrados':a['commits'], 'Dias ativos':a['active_days'],
            'Commits substantivos':a['substantive_commits'],
            'Commits só cosméticos':a['cosmetic_only_commits'],
            '% commits substantivos':a['substantive_commit_pct'],
            '% commits com testes':a['test_touch_pct'],
            '% churn após ajustes':a['effective_change_ratio_pct'],
            'Churn bruto':a['gross_churn'],
            'Churn com moves':a['rename_aware_churn'],
            'Churn sem whitespace':a['adjusted_churn'],
            'Código revisável (aprox.)':a['reviewable_churn'],
            'Churn código-fonte':a['source_churn'], 'Churn testes':a['test_churn'],
            'Churn documentação':a['docs_churn'],
            'Churn gerado/lockfiles':a['generated_churn'],
            'Moves':a['moved_files'], 'Moves puros':a['pure_moves'],
            'Commits que tocaram testes':a['test_touched_commits'],
            'PRs mesclados':a['merged_prs'], 'PRs revisados':a['reviews_submitted'],
            'PRs aprovados':a['reviews_approved'],
            'GitHub':a['github_login'] or 'não associado',
        })
    return rows


def _save_identity_ui(store: MetricsStore, report: dict, project_id: str):
    known=sorted({email for row in report['contributors'] for email in row['aliases']})
    if not known:
        return
    with st.expander('Associar e-mails e contas GitHub (opcional)'):
        st.caption('Associações são manuais e locais; não presumimos que o nome do autor Git seja a conta GitHub. '
                   'Múltiplos e-mails do mesmo desenvolvedor podem ser agrupados sem reprocessar commits.')
        with st.form(f'author-alias-{project_id}'):
            email=st.selectbox('E-mail alternativo',known,key=f'annual-alias-from-{project_id}')
            target=st.selectbox('E-mail canônico',known,key=f'annual-alias-to-{project_id}')
            if st.form_submit_button('Salvar associação de e-mails'):
                try:
                    store.set_author_alias(email,target)
                    st.success('Associação salva. A tabela será recalculada do cache local.')
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with st.form(f'gh-identity-{project_id}'):
            canonical=st.selectbox('E-mail do desenvolvedor',
                                   sorted({r['email'] for r in report['contributors']}),
                                   key=f'annual-gh-email-{project_id}')
            login=st.text_input('Login GitHub',key=f'annual-gh-login-{project_id}',
                                help='Ex.: octocat. Nunca informe tokens ou senhas.')
            if st.form_submit_button('Associar conta GitHub'):
                try:
                    store.map_github_login(canonical,login.strip())
                    st.success('Conta associada somente neste banco local.')
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def render_annual(project: dict, repos: list[dict], db_path: Path) -> None:
    """Explicit full scan and optional remote refresh; display reads are offline."""
    st.subheader('Contribuição anual · histórico completo')
    st.caption('Indicadores observáveis de mudanças, entregas e colaboração por desenvolvedor. '
               'Não é uma pontuação objetiva de produtividade nem uma avaliação individual automatizada.')
    year=int(st.number_input('Ano de referência',min_value=2000,max_value=2100,
                             value=date.today().year,step=1,key=f'annual-year-{project["id"]}'))
    selections=[]
    live_refs={}
    for repo in repos:
        try:
            branches=get_branches(repo['path'])
            refs=[x['ref'] for x in branches]
            live_refs.update({(repo['id'],x['ref']):x['sha'] for x in branches})
            default=choose_integration_ref(repo['path'])
        except (GitError,OSError) as exc:
            st.error(f'{repo["name"]}: {exc}')
            continue
        if default not in refs:
            refs.insert(0,default)
        chosen=st.selectbox(f'Referência de integração: {repo["name"]}',refs,
                            index=refs.index(default),key=f'annual-ref-{project["id"]}-{repo["id"]}',
                            help='Use a branch principal para contar entregas integradas. Uma branch de feature inclui trabalhos não mesclados.')
        selections.append((repo,chosen))
    if not selections:
        st.info('Selecione ao menos um repositório Git válido.')
        return
    st.caption('A primeira análise pode ser demorada: lê todo o histórico alcançável da ref. '
               'Reexecuções consultam SHAs já indexados e processam apenas os novos ou invalidados. '
               'Nenhuma operação GitHub é automática.')
    full_refresh=st.button('Indexar / atualizar histórico integral (Git local)',type='primary',
                           key=f'annual-refresh-{project["id"]}',width='stretch')
    if full_refresh:
        results=[];errors=[]
        with MetricsStore(db_path) as store:
            progress=st.progress(0, text='Preparando histórico Git...')
            for i,(repo,ref) in enumerate(selections):
                try:
                    with st.spinner(f'Indexando commits: {repo["name"]} ({ref})'):
                        def advance(done: int,total: int):
                            progress.progress((i + done/max(total,1))/len(selections),
                                              text=f'{repo["name"]}: {done:,} / {total:,} novos commits')
                        results.append(sync_repository(store,repo['id'],repo['path'],ref,progress_callback=advance))
                except (GitError,OSError,ValueError,RuntimeError) as exc:
                    errors.append(f'{repo["name"]}: {exc}')
                progress.progress((i+1)/len(selections))
        st.session_state[f'annual-last-sync-{project["id"]}']={'results':results,'errors':errors}
    sync_result=st.session_state.get(f'annual-last-sync-{project["id"]}')
    if sync_result:
        if sync_result['results']:
            reused=sum(s['reused'] for s in sync_result['results'])
            processed=sum(s['processed'] for s in sync_result['results'])
            st.success(f'Novos commits processados: {processed:,} · registros reutilizados: {reused:,}.')
        if sync_result['errors']:
            st.warning('Falhas na atualização: '+'; '.join(sync_result['errors'][:10]))

    with MetricsStore(db_path) as store:
        report=annual_report(store,[(r['id'],ref) for r,ref in selections],year)
        # A full snapshot becomes stale when a local ref advances or is rebased.
        # Never display its old membership as current 100% coverage.
        stale=[]
        for state in report['repo_coverage']:
            observed=live_refs.get((state['repo_id'],state['ref']))
            if observed and observed != state['head_sha']:
                stale.append({'repo_id':state['repo_id'],'ref':state['ref'],
                              'cached_head':state['head_sha'],'current_head':observed})
        report['stale_refs']=stale
        if stale:
            report['complete']=False
            report['coverage_percent']=None
            st.warning(f'Índice desatualizado para {len(stale)} referência(s): novos commits, rebase ou movimentação de branch. '
                       'Clique em Indexar / atualizar antes de comparar desenvolvedores.')
        st.caption('Esta visão anual usa o índice SQLite completo, não o limite de 2.000–10.000 commits das visões legadas.')
        if not report['complete'] and report['missing_repositories']:
            st.warning(f"Cobertura anual ainda não comprovada: {len(report['missing_repositories'])} "
                       'referência(s) não indexada(s) por completo. Clique em Indexar / atualizar.')
        elif report['complete'] and report['repo_coverage']:
            st.caption('Cobertura: 100% dos commits alcançáveis indexados, filtrados pelo ano da data do autor. '
                       'Não inclui alterações fora das referências selecionadas nem commits eliminados por squash.')
        if not report['pr_metadata_complete']:
            st.caption('PRs e revisões não possuem snapshot completo para todos os repositórios; células vazias significam dados indisponíveis, não zero.')
        contributors=report['contributors']
        if not contributors:
            st.info('Não há commits indexados para o ano/filtros. Se for o primeiro uso, clique em Indexar / atualizar.')
            return
        totals=report['totals']
        cols=st.columns(5)
        items=[('Commits analisados',report['processed_commits']),
               ('Contribuidores',len(contributors)),('Commits substantivos',totals['substantive_commits']),
               ('Churn bruto',totals['gross_churn']),('Churn ajustado',totals['adjusted_churn'])]
        for col,(name,val) in zip(cols,items):
            col.metric(name,f'{val:,}')
        cols=st.columns(4)
        for col,(name,key) in zip(cols,[('Código revisável','reviewable_churn'),
                                        ('Moves detectados','moved_files'),
                                        ('Commits só cosméticos','cosmetic_only_commits'),
                                        ('Commits com testes','test_touched_commits')]):
            col.metric(name,f'{totals[key]:,}')
        st.markdown('#### Indicadores por desenvolvedor')
        st.caption('Ordenação por commits (não por valor). Churn = atividade textual; mudanças de baixo volume '
                   'podem ter alto impacto. PRs e revisões só aparecem com atualização explícita e login associado.')
        rows=_table_rows(report)
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',height=540)
        st.download_button('Exportar indicadores anuais (CSV)',
                           csv_bytes(rows),
                           f'git-insights-contribuidores-{year}.csv','text/csv',on_click='ignore')
        st.markdown('#### Evolução mensal por desenvolvedor')
        by_email={row['email']:row for row in contributors}
        dev_email=st.selectbox('Contribuidor',
                               sorted(by_email,key=lambda email:by_email[email]['author'].casefold()),
                               format_func=lambda email:f"{by_email[email]['author']} ({email})",
                               key=f'annual-dev-{project["id"]}')
        trend=[m for m in report['monthly'] if m['email']==dev_email]
        if trend:
            data=pd.DataFrame(trend)
            st.line_chart(data.set_index('month')[['commits','test_touched_commits']])
            st.dataframe(data[['month','commits','adjusted_churn','reviewable_churn','test_touched_commits']],
                         hide_index=True,width='stretch')
        with st.expander('Cobertura, fontes e limites de interpretação'):
            st.write(report['repo_coverage'])
            st.markdown('''
- **Commits integrados:** alcançáveis na ref selecionada, por ano do autor. Merge conta como commit, sem churn próprio; squash muda atribuição.
- **Commits substantivos:** diffs com alteração textual após ignorar espaços; não garante funcionalidade ou qualidade.
- **Código revisável:** alterações ajustadas em arquivos de código/teste, excluindo arquivos provavelmente gerados/lockfiles por nome.
- **PRs/revisões:** consulta separada ao GitHub, associada manualmente ao e-mail do Git; cobertura pode ser parcial.
- **Cache:** SQLite local, SHA + versão do algoritmo; um novo commit não exige reprocessar os anteriores. Ref reescrita é reconciliada na atualização.
- **Limites:** autores podem usar e-mails diferentes; mudanças de indentação em Python são semânticas mesmo quando ignoradas por -w. Nenhuma métrica representa valor entregue isoladamente.
''')
        st.download_button('Exportar relatório de evidências (JSON)',
                           json.dumps(report,ensure_ascii=False,indent=2,default=str),
                           f'git-insights-evidencias-{year}.json','application/json',on_click='ignore')
        _save_identity_ui(store,report,project['id'])

    with st.expander('Integrar métricas de PRs e revisões (GitHub CLI, opcional)'):
        st.caption('Consulte apenas quando desejar. Requer gh autenticado e autorização para leitura. '
                   'O resultado é persistido no SQLite, junto da data e da cobertura. Não muda o Git remoto.')
        if st.button('Atualizar PRs e revisões via GitHub (rede)',
                     key=f'annual-pr-refresh-{project["id"]}'):
            successes=[];errors=[]
            with MetricsStore(db_path) as store:
                for repo,ref in selections:
                    slug=parse_github_repo(repo.get('url',''))
                    if not slug:
                        st.warning(f'{repo["name"]}: nenhuma URL GitHub validada no catálogo.')
                        continue
                    try:
                        items,complete=list_pr_collaboration(slug)
                        store.save_pull_requests(repo['id'],items,complete=complete)
                        successes.append(f'{repo["name"]}: {len(items)} PRs'+(' (limite atingido; incompleto)' if not complete else ''))
                    except (GitError,ValueError,OSError) as exc:
                        errors.append(f'{repo["name"]}: {exc}')
            if successes:st.success('; '.join(successes))
            if errors:st.warning('Falhas: '+'; '.join(errors))
            st.rerun()
    st.caption('Para refletir novos commits, execute Indexar / atualizar. A abertura da aba só lê o banco local.')
