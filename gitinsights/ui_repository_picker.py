"""GitHub CLI repository browser, rendered only when opened by the user."""
from __future__ import annotations

import streamlit as st

MAX_BATCH_REPOS = 25

from .catalog import Catalog, CatalogError
from .git_engine import GitError
from .github import list_accessible_repositories
from .remote import clone_mirror


def _url_key(url: str) -> str:
    return url.strip().lower().removesuffix('.git')


def render_github_picker(catalog: Catalog, project_id: str, repos: list[dict], mirror_home) -> bool:
    """Return True when at least one repository was registered in this click.

    List, import and filters are distinct user interactions. Merely opening or
    rerendering this surface never contacts GitHub or runs git clone.
    """
    st.caption(
        'Usa o GitHub CLI já autenticado. Listar consulta somente metadados; '
        'Adicionar selecionados clona cópias bare de leitura em cache local. '
        'A seleção e o clique bastam, sem pedir autorização por repositório.'
    )
    discovered_key = f'gh-discovered-{project_id}'
    report_key = f'gh-import-report-{project_id}'
    selected_key = f'gh-picker-{project_id}'
    if st.session_state.pop(f'gh-clear-selection-{project_id}', False):
        st.session_state.pop(selected_key, None)

    if st.button('Listar repositórios que posso acessar', key=f'gh-list-{project_id}', width='stretch'):
        try:
            with st.spinner('Consultando repositórios via gh...'):
                st.session_state[discovered_key] = list_accessible_repositories()
            st.session_state.pop(report_key, None)
            st.session_state.pop(selected_key, None)
        except GitError as exc:
            st.session_state.pop(discovered_key, None)
            st.error(str(exc))
    previous = st.session_state.get(report_key)
    if previous:
        if previous['added']:
            st.success(f'{previous["added"]} repositório(s) adicionado(s) ao projeto.')
        if previous['errors']:
            st.warning('Não adicionados:\n' + '\n'.join(previous['errors'][:8]))

    available = st.session_state.get(discovered_key)
    if available is None:
        st.info('Clique em listar para consultar sua conta do GitHub CLI. Nenhum clone será feito ao listar.')
        return False
    st.caption(f'{len(available)} repositório(s) acessível(is) retornado(s) pelo GitHub.')
    owners = sorted({r['full_name'].partition('/')[0] for r in available}, key=str.casefold)
    owner = st.selectbox('Proprietário', ['Todos', *owners], key=f'gh-owner-{project_id}')
    visibility = st.selectbox('Visibilidade', ['Todos', 'Privados', 'Públicos'], key=f'gh-visibility-{project_id}')
    include_archived = st.checkbox('Incluir repositórios arquivados', key=f'gh-archived-{project_id}')
    known = {_url_key(r.get('url', '')) for r in repos if r.get('kind') == 'mirror'}
    options = [r for r in available
               if (owner == 'Todos' or r['full_name'].partition('/')[0] == owner)
               and (visibility == 'Todos' or r['private'] == (visibility == 'Privados'))
               and (include_archived or not r['archived'])
               and _url_key(r['clone_url']) not in known]
    repo_map = {r['full_name']: r for r in options}
    selections = st.multiselect(
        'Escolha os repositórios para análise',
        sorted(repo_map, key=str.casefold),
        format_func=lambda name: name + (' · privado' if repo_map[name]['private'] else ' · público'),
        key=selected_key,
        help='Digite no campo para pesquisar por nome. Os repositórios existentes não aparecem novamente.',
    )
    st.caption(f'{len(options)} disponível(is) após filtros. Já cadastrados foram ocultados.')
    if len(selections) > MAX_BATCH_REPOS:
        st.warning(f'Selecione no máximo {MAX_BATCH_REPOS} repositórios por lote para limitar uso de disco e duração da operação.')
    if not st.button(
        f'Adicionar {len(selections)} selecionado(s) ao dashboard',
        type='primary', width='stretch', disabled=not selections or len(selections) > MAX_BATCH_REPOS,
        key=f'gh-import-{project_id}',
    ):
        return False
    added = 0
    errors: list[str] = []
    with st.spinner('Clonando espelhos em cache local (somente leitura na origem)...'):
        for name in selections:
            entry = repo_map.get(name)
            if not entry:
                errors.append(f'{name}: repositório fora da lista atual.')
                continue
            try:
                target = clone_mirror(entry['clone_url'], mirror_home, use_gh_auth=True)
                catalog.add_mirror_repo(
                    project_id, str(target), entry['clone_url'], name, auth_via_gh=True,
                )
                added += 1
            except (GitError, CatalogError, OSError) as exc:
                errors.append(f'{name}: {exc}')
    st.session_state[report_key] = {'added': added, 'errors': errors}
    if added:
        st.session_state[f'gh-clear-selection-{project_id}'] = True
        return True
    if errors:
        st.warning('\n'.join(errors))
    return False
