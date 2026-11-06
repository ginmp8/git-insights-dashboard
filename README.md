# Git Insights Dashboard

**Dashboard local de análise de engenharia Git, desenvolvido em Python + Streamlit.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Streamlit](https://img.shields.io/badge/Streamlit-1.50%2B-FF4B4B?logo=streamlit&logoColor=white) [![Version](https://img.shields.io/github/v/tag/ginmp8/git-insights-dashboard?sort=semver)](https://github.com/ginmp8/git-insights-dashboard/tags) ![License](https://img.shields.io/badge/license-MIT-blue)

Este é o repositório oficial do **Git Insights Dashboard**: um aplicativo **local-first** para acompanhar commits, contribuidores, branches, churn, movimentações de arquivos, hotspots e Pull Requests de vários repositórios. Inspirado nas funcionalidades de [Git Insights](https://github.com/Wasserpuncher/git-insights) e [Gita](https://github.com/janmikolas/gita), com implementação independente.


## Documentação e histórico de versões

- [Guia de funcionalidades](docs/README.md) · [Primeiros passos](docs/getting-started.md) · [Privacidade](docs/privacy-and-security.md)
- [Projetos e repositórios](docs/features/projects-and-repositories.md) · [Métricas e autores](docs/features/analytics-and-contributors.md) · [Branches](docs/features/branches-and-comparison.md)
- [Contribuição anual 0.3.0](docs/features/annual-contribution.md) · [ICE-Git/1 · score experimental](docs/features/ice-git.md) · [Mudanças ajustadas](docs/features/change-quality.md) · [GitHub CLI e PRs](docs/features/github-integration.md)
- [Histórico de versões](releases/README.md) · [Candidata 0.3.0](releases/0.3.0.md) · [Notas da 0.2.0](releases/0.2.0.md) · [Notas da 0.1.0](releases/0.1.0.md) · [Changelog](CHANGELOG.md)


**Início rápido (Windows):** tenha Python 3.11+ e Git instalados; clone este repositório e execute o inicializador.

```powershell
git clone https://github.com/ginmp8/git-insights-dashboard.git
cd git-insights-dashboard
.\start-windows.cmd
```

Abra **http://127.0.0.1:8501**. Para listar repositórios de sua conta (inclusive privados, conforme permissão), instale [GitHub CLI](https://cli.github.com/), execute `gh auth login` uma vez e utilize a seleção pela interface. **Você não precisa fornecer um token ao dashboard.** Também é possível analisar apenas repositórios locais, sem GitHub CLI.

**Importante:** o dashboard foi projetado para uma única máquina. Não exponha a porta 8501 publicamente; a aplicação não possui autenticação de usuários.

## Funcionalidades implementadas

- **ICE-Git/1 (candidata 0.3.0):** índice de evidências de contribuição por desenvolvedor, relativo ao grupo, com crédito limitado por diff de arquivo/commit, P75, componentes explícitos, rastreio por SHA e política versionada reutilizável. O índice não comprova produtividade individual ou impacto de negócio; a dimensão GitHub é opcional e indisponível sem dados completos.
- **Contribuição anual (candidata 0.3.0, branch de desenvolvimento)**: aba inicial com commits integrados, churn bruto/move/whitespace, mudanças substantivas e cosméticas, atividade de autores, arquivos de código/testes/docs/gerados, PRs/revisões opcionais e evolução mensal; todos os commits alcançáveis pela referência selecionada são indexados em SQLite local com atualização incremental por SHA.

- **Projetos com vários repositórios**, com leitura de pastas locais ou espelhos GitHub criados ao clicar em Adicionar.
- **Visão consolidada**: commits, contribuidores, linhas adicionadas/removidas, churn, histórico diário e comparação entre repositórios.
- **Contribuidores**: commits, adições/remoções, número de repositórios, gráficos e mapa de atividade por dia/hora.
- **Arquivos**: hotspots, tipo de arquivo, frequência de alteração, churn por arquivo.
- **Branches**: refs locais e remotas conhecidas, SHA, última atualização, commits alcançáveis e tags; comparação entre duas branches com ahead/behind e diff.
- **Filtros combináveis**: repositório, branch, autor/e-mail, período, pasta global e pasta específica por repositório.
- **GitHub CLI (novo)**: botão para listar todos os repositórios que a conta autenticada pode acessar (próprios, colaborador e organizações), incluindo privados; filtros por proprietário/visibilidade e seleção múltipla para importar sem copiar links nem confirmar um por um.
- **Mudanças ajustadas (novo)**: relatórios por autor e commit de churn bruto, churn reconhecendo moves (`git diff-tree -M`), churn ignorando espaços (`-w`), movimentações `antigo → novo`, potenciais renomes de identificadores e arquivos de teste alterados.
- **GitHub Pull Requests**: integração **opcional** via `gh`, ativada por botão explícito e autenticação já existente no `gh`.
- **Exportação local**: JSON agregado e CSV de commits, com proteção contra fórmulas de planilhas no CSV.
- **Persistência local**: catálogo em JSON atômico; cache de leitura em memória (até cinco minutos). Nenhum banco de dados ou servidor de terceiros é necessário.

## Rodar no Windows (PowerShell)

Pré-requisitos: **Python 3.11+** e **Git** no PATH. **GitHub CLI (`gh`) é opcional**, mas necessário para listar repositórios da conta e consultar PRs. Internet é usada na instalação das bibliotecas via pip e apenas nas operações GitHub explícitas.

```powershell
cd C:\caminho\git-insights-dashboard
.\start-windows.ps1
```

Se preferir evitar scripts do PowerShell, execute **`start-windows.cmd`** no Prompt de Comando (ou por duplo clique). Se preferir, execute manualmente:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Abra **http://127.0.0.1:8501**. A interface não possui login e **não deve ser exposta à rede pública**.

## Rodar no Linux/macOS

```sh
git clone https://github.com/ginmp8/git-insights-dashboard.git
cd git-insights-dashboard
./start-linux-macos.sh
```

Ou instale com `python3 -m venv .venv` e rode `python -m streamlit run app.py` após instalar os requisitos.

## Primeiro uso (sem copiar URLs)

1. Execute `gh auth login` **uma vez** no terminal, se ainda não estiver autenticado. Confira com `gh auth status`. Não copie tokens no dashboard.
2. Crie um **projeto** na barra lateral do dashboard.
3. Em **Adicionar repositório → GitHub CLI · escolher da lista**, clique em **Listar repositórios que posso acessar**. A listagem ocorre somente quando você clicar; não faz clones.
4. Filtre por **proprietário**, **visibilidade** ou pesquise no seletor. Selecione até **25 repositórios por lote** (limite para evitar clones acidentais muito grandes) e clique **Adicionar selecionados ao dashboard**. Esse único clique já autoriza a clonagem de espelhos locais, sem caixas de confirmação repetidas.
5. Escolha as branches, período, autores e pastas; abra **Mudanças ajustadas** e clique em **Calcular métricas ajustadas (Git local)** para analisar renames e alterações cosméticas.
6. Para atualizar os espelhos após novos commits, clique em **Fazer fetch dos espelhos** (não é automático).

**Observações:** a descoberta usa `gh api /user/repos` com paginação, e segue as permissões da conta autenticada. A clonagem de repositórios selecionados usa o próprio `gh` como helper Git **apenas durante a operação**; não altera suas configurações Git globais nem grava tokens em URLs. Se a organização exigir SSO, as permissões da conta precisam permitir o acesso. O modo de seleção automática suporta `github.com`; GitHub Enterprise com domínio personalizado não está configurado nesta versão.

O fluxo alternativo de **Pasta local** continua disponível. A opção **GitHub · URL manual** fica como fallback avançado e não exige caixa de autorização extra, porque o botão de clonar já é uma ação explícita.

### Upgrade da v0.1.0

Mantenha a pasta local `.git-insights-data/` (catálogo e mirrors) ao atualizar o código, ou defina `GIT_INSIGHTS_HOME` apontando para ela. Não apague os espelhos antigos durante a atualização.

### Ver um exemplo sem usar seus repositórios

```powershell
.\.venv\Scripts\python.exe scripts\create_demo.py
```

Isso cria **3 pequenos repositórios Git sintéticos**, com autores e commits fictícios, dentro de `.git-insights-data/demo-repos/`, e cadastra um projeto `DEMO · Dados fictícios`. O comando é **opcional** e não modifica seus projetos.

## Escopo da análise

- O padrão analisa todas as **branches locais e refs remotas já conhecidas** do clone, sem duplicar commits que aparecem em mais de uma branch do mesmo repositório. Não há `fetch` automático.
- Selecionar uma branch restringe commits alcançáveis **por aquela branch**, sem mesclá-los com outras. Ao selecionar várias pastas, cada uma é tratada como repositório separado.
- O limite padrão é **5.000 commits por repositório**, com aviso quando ocorrer truncamento. Para cobertura integral, selecione **Sem limite** — repositórios grandes podem demorar ou consumir memória.
- Se uma branch selecionada não existir em algum repositório, esse repositório é ignorado para o histórico e um aviso aparece.
- A contagem de commits **por branch** considera todo o histórico da ref e pode incluir commits compartilhados. Não some essas contagens.
- Contribuidores são agrupados por **e-mail de autor** após as normalizações Git `.mailmap` (`--use-mailmap`); pessoas com múltiplos e-mails ainda podem aparecer separadas.
- O período e o mapa horário usam a data/hora e fuso registrados pelo autor; diferenças de fuso podem afetar distribuições horárias.
- O **churn bruto histórico** continua calculado com `git log --numstat -z --no-renames`, para não mudar o comportamento original. Commits de merge são contados como commits, mas excluídos das somas de linhas. Arquivos binários contam como alterados sem adições/remoções numéricas. Renames aparecem como remoção/adição no **bruto**; a nova aba separa essas operações em uma inspeção adicional e não altera os números legados.
- Filtro por pasta recalcula churn e hotspots **somente nos arquivos que correspondem ao prefixo**, não no restante do commit.
- Commits com nomes de arquivo contendo o separador de controle ASCII `0x1e` não são suportados pelo parser de log. Caminhos com espaços ou quebra de linha são suportados.
- **Não faz** métricas de PR sem acesso opcional `gh` e não pretende medir produtividade individual ou qualidade de código pelo volume de commits.

### Como interpretar o churn ajustado

| Métrica | Interpretação e limitações |
|---|---|
| Churn bruto | Histórico sem reconhecimento de movimentos: pode superestimar esforço. |
| Com rename (`-M`) | Git identifica pares de arquivos semelhantes que foram movidos/renomeados (limiar padrão 50%); movimentações internas de blocos e cópias não são totalmente cobertas. |
| Ignorando espaços (`-M -w`) | Indicador textual conservado após ignorar espaços. **Pode esconder mudanças funcionais em Python quando a indentação muda.** Nunca assumir equivalência sem revisão. |
| Possíveis renomes de identificadores | Regra lexical estrita para substituições consistentes de nomes. Uma troca de identificador também pode alterar o programa, API pública ou segurança. Revisar diff. |
| Arquivos de teste alterados | Evidência de edição de arquivos com nomes/pastas de teste, não de execução, cobertura ou sucesso. |

A aba legada **Mudanças ajustadas** continua sendo um diagnóstico rápido, limitado aos 25/100/250/500 commits mais recentes. **A nova aba Contribuição anual da 0.3.0 não usa essa amostragem:** indexa integralmente os SHAs da referência Git selecionada e consulta o SQLite local. Os indicadores não constituem avaliação objetiva da produtividade individual. Consulte [metodologia e cobertura](docs/features/annual-contribution.md).

Para analisar contribuição com mais confiança, cruzar essas métricas com PRs revisados/mesclados, resultados de testes/CI, correções de regressões e impacto real de entregas. Nenhum número de linhas sozinho mede valor entregue.

## Rede, privacidade e armazenamento

| Operação | Rede? | Modifica repositório original? |
|---|---|---|
| Ler histórico, branches e arquivos localmente | Não | Não |
| Recalcular análise | Não | Não |
| Salvar catálogo e relatórios no diretório da aplicação | Não | Não |
| Listar repositórios que a conta `gh` acessa (clique) | **Sim** | Não; carrega metadados na sessão |
| Adicionar repositórios selecionados (clique) | **Sim** | Não; clona espelhos no cache `.git-insights-data/mirrors/` |
| Clonar manualmente por URL (clique) | **Sim** | Não; clona espelho no cache |
| Atualizar espelhos (botão explícito) | **Sim** | Não; atualiza apenas o espelho da aplicação |
| Consultar PRs via `gh` (botão explícito) | **Sim** | Não |
| Instalação inicial via `pip` | **Sim** | Não |

- O servidor Streamlit é configurado para `127.0.0.1:8501` e a coleta de estatísticas de uso do Streamlit é desativada (`browser.gatherUsageStats = false`).
- Não contém API keys, serviços de IA, webhooks ou telemetria própria. O dashboard não envia seus arquivos para processamento externo.
- A pasta `.git-insights-data/` fica **dentro do projeto**, com `catalog.json`, caches Git clonados quando autorizados, e repositórios demo se usados. Configure `GIT_INSIGHTS_HOME` para mudar o local.
- Remover um repositório do catálogo **não apaga arquivos**, mesmo se for um espelho; remova resíduos de espelhos manualmente somente se desejar.
- O `gh` utiliza a autenticação local existente para listar repositórios, operar como helper de credenciais nos clones selecionados e consultar PRs. **A descoberta não clona nada; apenas o clique em Adicionar executa os clones.** Repositórios privados clonados são cópias em disco e precisam ser protegidos pelas permissões do usuário local. Evite executar em servidor compartilhado ou com privilégios elevados.
- A instalação de pacotes Python também acessa o índice configurado pelo seu pip; o comportamento de suas dependências deve ser verificado conforme o ambiente.

## Testes e validação

Os resultados da candidata 0.3.0 estão em [VALIDATION-0.3.0.md](VALIDATION-0.3.0.md). A execução local registrou 54 testes aprovados e benchmark sintético de 50.000 commits; Streamlit real/gh autenticado não foram exercitados neste sandbox.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app.py gitinsights scripts tests
```

Os testes integram Git real em repositórios temporários para validar branches divergentes, deduplicação, filtros, churn, movimentos 100%, formatação, substituição consistente de identificador, parsing de nomes incomuns, segurança das URLs remotas, persistência e exportação. A descoberta/importação via `gh` é testada com doubles; os testes não consultam GitHub nem clonam repositórios remotos.

## Limitações e evolução

Esta versão é direcionada para **analytics local de engenharia**, não para gerenciamento operacional de tarefas. Ainda não possui login multiusuário, perfis, métricas reais de CI/CD nem dashboard executável empacotado como EXE. O processamento anual incremental em SQLite está disponível na branch de desenvolvimento 0.3.0. A comparação `merge-base`/ahead-behind já está presente. A inspeção por identificador é heurística e não substitui análise semântica de código. É uma aplicação Python/Streamlit, não um executável Tauri.

## Proveniência

Implementação independente inspirada nos recursos publicamente descritos pelos projetos [Wasserpuncher/git-insights](https://github.com/Wasserpuncher/git-insights) e [janmikolas/gita](https://github.com/janmikolas/gita). Nenhum arquivo de código-fonte desses projetos foi incluído neste pacote.
