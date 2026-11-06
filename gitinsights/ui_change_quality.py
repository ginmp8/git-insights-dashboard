"""Explicit, bounded visual diagnostics for move-aware Git activity."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st

from .change_quality import analyze_change_quality, summarize_change_quality
from .git_engine import GitError


def render_change_quality(project: dict, selected_commits: dict[str, list[dict]],
                          selected_repos: list[dict], repo_labels: dict[str, str]) -> None:
    st.subheader('Mudanças ajustadas · renames e formatação')
    st.caption(
        'Diagnóstico sob demanda que não mede valor, qualidade ou produtividade individual. '
        'Compara churn bruto, churn com renomeações de arquivos e churn ignorando espaços.'
    )
    available = [(r, c) for r in selected_repos for c in selected_commits.get(repo_labels[r['id']], [])]
    available.sort(key=lambda item: (item[1]['date'], item[1]['sha']), reverse=True)
    sample_size = st.selectbox('Commits mais recentes a inspecionar', [25, 100, 250, 500], index=1,
                               key=f'quality-size-{project["id"]}')
    picked = available[:sample_size]
    # File-path signature ensures any folder-level filter invalidates old results.
    fingerprint = [(r['id'], c['sha'], sorted(f['path'] for f in c['files'])) for r, c in picked]
    signature = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False).encode('utf-8')).hexdigest()
    result_key = f'quality-result-{project["id"]}'
    total = len(available)
    st.caption(f'Amostra: {len(picked)} de {total} commits filtrados. Até três diffs Git locais '
               'por commit; não consulta serviços externos. O cálculo pode demorar.')
    if st.button('Calcular métricas ajustadas (Git local)', type='primary',
                 disabled=not picked, key=f'quality-run-{project["id"]}'):
        rows = []
        errors = []
        with st.spinner('Analisando diferenças de arquivos, espaços e nomes...'):
            for repo, commit in picked:
                try:
                    row = analyze_change_quality(repo['path'], [commit])[0]
                    row['repo'] = repo_labels[repo['id']]
                    rows.append(row)
                except GitError as exc:
                    errors.append(f'{repo["name"]}/{commit["sha"][:9]}: {exc}')
        st.session_state[result_key] = {
            'signature': signature, 'result': rows, 'total': total, 'errors': errors,
        }
    saved = st.session_state.get(result_key)
    if not saved or saved['signature'] != signature:
        st.info('Clique em calcular. O resultado é desta sessão e será invalidado se mudar a amostra ou filtros.')
        return
    rows = saved['result']
    if saved['errors']:
        st.warning('Falhas parciais, não incluídas nos totais: ' + '; '.join(saved['errors'][:8]))
    if not rows:
        st.warning('Nenhum commit foi analisado com sucesso.')
        return
    summary = summarize_change_quality(rows)
    totals = summary['totals']
    st.caption(f'**Cobertura: {len(rows)} / {total} commits filtrados.** '
               'Resultados não representam o histórico completo quando a amostra é parcial.')
    group = st.columns(3)
    group[0].metric('Churn bruto na amostra', f'{totals["gross_churn"]:,}')
    group[1].metric('Churn com detecção de move', f'{totals["rename_aware_churn"]:,}')
    group[2].metric('Churn ignorando espaços', f'{totals["adjusted_churn"]:,}')
    group = st.columns(4)
    group[0].metric('Renomes/moves detectados', totals['moved_files'])
    group[1].metric('Moves sem mudanças de texto', totals['pure_moves'])
    group[2].metric('Candidatos a renomeação de identificador', totals['identifier_only_candidates'])
    group[3].metric('Arquivos de teste alterados', totals['test_files_touched'])

    st.markdown('#### Comparação por contribuinte')
    contributors = [{
        'Autor': r['author'], 'E-mail': r['email'], 'Commits avaliados': r['commits'],
        'Churn bruto': r['gross_churn'], 'Com rename (-M)': r['rename_aware_churn'],
        'Ignorando espaços (-M -w)': r['adjusted_churn'],
        'Moves': r['moved_files'], 'Candidatos a troca de identificador': r['identifier_only_candidates'],
        'Linhas de candidatos': r['identifier_candidate_churn'],
        'Arquivos de código': r['source_files_touched'], 'Arquivos de teste': r['test_files_touched'],
    } for r in summary['by_author'].values()]
    st.dataframe(pd.DataFrame(sorted(contributors, key=lambda r: (-r['Churn bruto'], r['E-mail']))),
                 hide_index=True, width='stretch', height=340)
    st.markdown('#### Diagnóstico por commit')
    table = [{
        'Repositório': r['repo'], 'Data': r['date'][:10], 'Autor': r['author'],
        'SHA': r['sha'][:10], 'Mensagem': r['message'], 'Bruto': r['gross_churn'],
        'Com rename': r['rename_aware_churn'], 'Ignorando espaços': r['adjusted_churn'],
        'Renomes de arquivo': r['moved_files'], 'Candidatos de identificador': r['identifier_only_candidates'],
    } for r in rows]
    st.dataframe(pd.DataFrame(table), hide_index=True, width='stretch', height=400)
    moves = [
        {'Repositório': r['repo'], 'Commit': r['sha'][:10], 'Autor': r['author'],
         'Caminho anterior': m['old_path'], 'Novo caminho': m['new_path'],
         'Similaridade Git (%)': m['similarity']}
        for r in rows for m in r['moves']
    ]
    candidates = [
        {'Repositório': r['repo'], 'Commit': r['sha'][:10], 'Autor': r['author'],
         'Arquivo': path, 'Status': 'Substituição lexical consistente; revisar diff'}
        for r in rows for path in r['identifier_candidate_paths']
    ]
    with st.expander(f'Movimentações de arquivos ({len(moves)})', expanded=bool(moves)):
        if moves:
            st.dataframe(pd.DataFrame(moves), width='stretch', hide_index=True, height=330)
        else:
            st.info('Não foram detectados renames no escopo analisado.')
    with st.expander(f'Arquivos com possíveis trocas de identificadores ({len(candidates)})'):
        if candidates:
            st.dataframe(pd.DataFrame(candidates), width='stretch', hide_index=True, height=330)
        else:
            st.info('Nenhum candidato identificado ou alteração fora do limite de inspeção.')
    st.download_button(
        'Exportar diagnóstico (JSON)',
        json.dumps({'sample_count': len(rows), 'filtered_total': total, 'summary': summary, 'commits': rows},
                   ensure_ascii=False, indent=2),
        'git-insights-change-diagnostics.json', 'application/json', on_click='ignore',
    )
    with st.expander('O que é e não é uma contribuição efetiva'):
        st.markdown('''
- **Bruto:** linhas adicionadas + removidas na análise original. Movimentos podem inflar o valor.
- **Com rename (`-M`):** o Git tenta reconhecer renomeação/movimentação de arquivo com similaridade padrão de 50%. Mover blocos dentro do arquivo e cópias não são plenamente detectados.
- **Ignorando espaços (`-M -w`):** reduz alterações puramente de formatação. **Atenção:** mudanças de indentação em Python podem alterar a execução e serem ignoradas por `-w`.
- **Candidato a troca de identificador:** arquivos cujos tokens mudaram apenas em substituições consistentes de nomes, sem alteração de ordem ou de outros tokens. É uma *heurística lexical*, não uma prova de que a mudança não alterou o comportamento.
- **Arquivos de teste alterados:** mede arquivos com nomes/pastas associados a testes, não garante execução ou cobertura.

Nenhuma dessas métricas isoladamente mede a relevância de uma entrega. Para avaliar resultados de engenharia, complemente com análise de PRs, revisão, testes executados, bugs corrigidos e consequências observáveis em produção.
''')
