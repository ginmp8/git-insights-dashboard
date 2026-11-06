# Contribuição anual de engenharia (0.3.0)

A aba **Contribuição anual** foi implementada para análises de histórico integral por desenvolvedor, com métricas persistidas localmente. Ela aparece antes das abas legadas no dashboard Streamlit.

## Como usar

1. Selecione um projeto com repositórios Git no catálogo.
2. Abra **Contribuição anual** e informe o ano desejado.
3. Confira a referência de integração de cada repositório. O padrão prefere `origin/main`, `main`, `origin/master` ou `master`; é possível escolher outra referência disponível.
4. Clique **Indexar / atualizar histórico integral (Git local)**. Na primeira execução, os commits são processados em lotes; em execuções seguintes, diffs já indexados por SHA e versão do algoritmo são reutilizados.
5. Observe a cobertura de referências, número de commits e desenvolvedores. A tabela apresenta indicadores por e-mail Git, com filtros de ano/ref separados dos filtros das abas legadas.
6. Opcionalmente associe e-mails da mesma pessoa ou uma conta do GitHub, e importe snapshots de Pull Requests/revisões mediante clique e autenticação prévia no GitHub CLI.

**Importante:** o limite de 2.000/5.000/10.000 commits das abas históricas e a amostragem de até 500 commits em **Mudanças ajustadas** não se aplicam aos totais desta aba. A cobertura de 100% vale somente para os commits alcançáveis pelas referências explicitamente indexadas, não para todos os commits criados em branches paralelas ou para alterações descartadas antes de chegar à branch principal.

## Métricas por desenvolvedor

| Indicador | Definição e interpretação |
|---|---|
| Commits integrados | Commits alcançáveis na ref selecionada, com data de autoria dentro do ano, após deduplicação na própria ref. Merge conta como commit sem contabilizar churn próprio. |
| Dias ativos | Datas distintas com commits registrados. Não mede horas trabalhadas. |
| Commits substantivos | Commits que mantêm diferenças de linhas após ajuste Git `-M -w`. Indica mudança textual, não prova valor/qualidade. |
| Commits só cosméticos | Commits com churn bruto positivo e churn `-M -w` zero. Inclui movimentos e formatação, sem concluir que foram desnecessários. |
| Churn bruto | Linhas adicionadas + removidas, sem reconhecer renomes. |
| Churn com moves | Churn com detecção heurística Git de arquivo renomeado/movido (`-M`). |
| Churn sem whitespace | Churn com `-M -w` (ignora espaços). Pode ocultar mudanças semânticas de indentação em Python. |
| Código revisável (aprox.) | Churn ajustado em código-fonte e testes, excluindo arquivos com padrões conhecidos de artefatos gerados/lockfiles. Não mede tamanho/complexidade de uma entrega. |
| Código-fonte, testes, documentação e gerados | Separação de churn por categorias de nome/extensão, com risco de classificação imperfeita. |
| Renomes/moves | Quantidade de arquivos detectados como renomeados, incluindo moves puros (`R100`). |
| Commits que tocaram testes | Commits que alteraram arquivos com nome/pasta de teste; **não prova testes executados nem cobertura**. |
| Taxas | Percentual de commits com mudança substantiva, percentual com arquivos de testes alterados e proporção de churn bruto ainda presente após ajustes. São razões descritivas, não pontuação de desempenho. |
| PRs mesclados | PRs associados explicitamente ao login GitHub do autor; integrados no ano do merge, conforme snapshot opcional. |
| PRs revisados / aprovados | PRs distintos revisados / aprovados pela conta GitHub mapeada, conforme as revisões disponíveis no snapshot. |

**Não existe escore universal de produtividade por desenvolvedor.** A comparação entre pessoas requer contexto de função, tipos de tarefa, revisão, incidentes, impacto do produto e períodos de disponibilidade. Não utilize um ranking de linhas ou commits como avaliação de desempenho.

## Persistência incremental

O aplicativo utiliza o arquivo local `.git-insights-data/annual-metrics.sqlite3` (ou o diretório configurado por `GIT_INSIGHTS_HOME`), sem serviço externo de banco de dados.

- `commits`: cada commit por repositório/SHA e seus metadados, com versão do algoritmo.
- `file_changes`: linhas e caminhos por SHA nos modos bruto, com renomeações, ignorando espaços e status.
- `commit_metrics`: agregados calculados por SHA, reutilizados para diferentes anos e refs.
- `ref_commits` e `ref_state`: cobertura de cada referência, atualizada somente depois de uma indexação integral bem-sucedida.
- `author_aliases` e `github_identities`: associações locais explícitas.
- `pull_requests`, `pr_reviews`, `pr_state`: snapshots opcionais obtidos por demanda e seus metadados de cobertura.

Cada atualização percorre a lista de SHAs alcançáveis (operações Git locais, sem baixar conteúdo remoto automaticamente), **processa somente os SHAs novos/versões de análise defasadas** e reconcilia a composição da referência. Em um rebase, SHAs que deixaram a referência não aparecem nas estatísticas, mas seus dados anteriores permanecem no cache para eventual reutilização. Uma falha durante a atualização não publica um estado parcial como cobertura completa. A interface compara o SHA atual de cada branch selecionada ao SHA indexado e sinaliza quando o cache está desatualizado; nesse caso a cobertura não é exibida como 100% até nova indexação. Alterações de `.mailmap` atualizam a identidade de autoria sem recalcular diffs.

Não é aplicada migração sobre o catálogo JSON da 0.2.0. O banco SQLite é criado separadamente. Proteja esse arquivo: ele contém nomes de arquivos, mensagens de commit e métricas de repositórios que podem ser privados. Abertura da aba não faz consulta à rede.

## GitHub CLI e colaboração

A integração de PRs é **opcional**: execute `gh auth login` no terminal e depois, no painel anual, clique **Atualizar PRs e revisões via GitHub (rede)**. O comando consulta os PRs das URLs GitHub registradas e persiste o snapshot no SQLite. Se um repositório for inacessível ou tiver limite/paginação desconhecido, os valores associados não são considerados cobertura plena. Vincule manualmente o e-mail Git ao login GitHub para atribuir dados de colaboração a alguém; nenhuma identidade é inferida automaticamente.

O GitHub CLI não é necessário para os indicadores Git. Revisões e PRs podem permanecer em branco, o que **não é equivalente a zero**. A API fornece dados observados em um snapshot, sujeitos a permissões, histórico disponível e limite de consulta.

## Validação e limites

- [Evidências da candidata 0.3.0](../../VALIDATION-0.3.0.md).
- [Histórico de versões](../../releases/README.md).
- Benchmarks sintéticos não representam desempenho garantido em repositórios reais, especialmente com arquivos grandes, merges e renomeações complexas.
- Git é uma fonte limitada: autoria de squash merges, pair programming, revisões fora do GitHub, trabalho não commitado, participação em incidentes e impacto de negócio não são integralmente observáveis.
- A heurística de troca lexical de identificadores da aba **Mudanças ajustadas** continua sendo uma inspeção sob demanda; a 0.3.0 não afirma equivalência semântica nem cobertura anual desse classificador.
