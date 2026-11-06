# ICE-Git/1 — Índice de Evidências de Contribuição (experimental)

**Objetivo:** oferecer uma comparação **rastreável e relativa** das mudanças de código integradas por desenvolvedor, usando o histórico Git e os diffs já persistidos no SQLite local. O índice **não mede produtividade, qualidade, impacto de negócio ou esforço humano de forma objetiva**. Um score alto significa apenas maior presença dos sinais escolhidos **dentro do mesmo grupo, período, política e conjunto de referências**.

O ICE-Git atende à necessidade operacional de comparar **50 ou mais contribuidores** com históricos anuais grandes sem reprocessar as diferenças dos commits que já foram indexados. O cálculo se apoia no trabalho da [indexação integral](annual-contribution.md). Não cria novo banco, não altera o Git original e não faz chamadas de rede.

## Onde encontrar

1. Abra **Contribuição anual** e selecione o ano e as referências de integração desejadas, idealmente a branch principal de cada repositório.
2. Clique em **Indexar / atualizar histórico integral** para carregar novos commits no SQLite. A pontuação só é gerada com snapshot completo e atualizado.
3. Consulte **ICE-Git · evidências de contribuição (experimental)** abaixo da tabela anual. A tabela é ordenada por ICE-Git, não por quantidade de commits.
4. Selecione um desenvolvedor em **Auditar evidências ICE-Git** para consultar as quatro dimensões e os caminhos dos arquivos/SHAs que contribuíram para o cálculo.
5. Exporte CSV de scores ou JSON com política, quantis de referência, cobertura e amostra de proveniência.

A pontuação pode ficar **indisponível** se houver menos de três contribuidores, se o índice estiver incompleto ou se a referência de integração tiver sido alterada desde a última indexação. Nessas situações não é correto fabricar uma nota.

## Duas saídas, duas interpretações

| Saída | Cobertura dos pesos | Fonte | Condição |
|---|---|---|---|
| **ICE-Git (0–100)** | 85% das dimensões do modelo, com pesos renormalizados | Commits e diffs Git locais | Histórico completo e ≥3 contribuidores |
| **ICE ampliado (0–100)** | 100% dos pesos | Git + PRs/revisões GitHub | Todos os snapshots de PR completos e pelo menos 3 identidades explicitamente mapeadas; caso contrário **N/D** |

A coluna **Cobertura dos pesos (%)** significa **quais dimensões estão disponíveis**, não qual porcentagem dos commits foi analisada. A cobertura histórica do Git é indicada separadamente pela interface e pelo relatório anual. Um PR não consultado, inacessível ou sem conta GitHub vinculada é **desconhecido**, não zero. Um PR com contagem zero e snapshot comprovadamente completo é zero.

## Dimensões, pesos e fórmula

| Dimensão | Peso do ICE ampliado | Sinal observado | O que **não** significa |
|---|---:|---|---|
| **Entrega integrada (E)** | 30% | Número de commits alcançáveis pela referência escolhida com **diff textual material** em código, testes ou documentação | Não verifica a conclusão de uma história, funcionalidade ou requisito |
| **Substância técnica do diff (T)** | 30% | Crédito limitado por arquivo/commit para alterações de código, testes e docs após detecção de renomeações e ignorar espaços (`-M -w`) | Não identifica complexidade, utilidade, correção ou equivalência semântica |
| **Sinais de sustentação (S)** | 25% | Proporção de commits materiais que também mudaram arquivos de testes ou documentação | Não prova testes executados, cobertura, qualidade, revisão ou manutenção |
| **Colaboração GitHub (C)** | 15% | PRs mesclados e PRs revisados, mediante mapeamento explícito e snapshot completo | Não mede qualidade da revisão nem influência fora do GitHub |

**Fórmulas:**

- `ICE-Git = (0,30 × E + 0,30 × T + 0,25 × S) / 0,85`
- `ICE ampliado = 0,30 × E + 0,30 × T + 0,25 × S + 0,15 × C` (somente quando C é conhecido)
- `E = min(100, 100 × ln(1 + commits_materiais) / ln(1 + P75_commits_materiais))`
- `T = min(100, 100 × ln(1 + credito_diff) / ln(1 + P75_credito_diff))`
- `S = min(100, 100 × (commits_com_testes_ou_docs / commits_materiais) / 0,25)`
- `C = 0,5 × escala_log(PRs_mesclados, P75_PRs) + 0,5 × escala_log(PRs_revisados, P75_revisões)`

Se o denominador ou a referência for zero, sua dimensão fica zero. O percentil P75 usa interpolação linear sobre **todos os contribuidores no mesmo escopo**; quando ele é zero apesar de existirem observações positivas, a referência passa a ser o P75 dos valores positivos (evita zerar trabalho real em grupos com muitos indicadores nulos). As dimensões E, T e C têm retorno decrescente (`ln(1+x)`) e saturam em 100 pontos no P75. Não há multiplicação ilimitada de score para alguém com 8.000 commits em relação a um colega com 1.000. A dimensão S é um **indicador de mudança em arquivos de suporte**, não validação de teste.

### Como o Git gera o crédito técnico

O índice lê **`file_changes` no SQLite** (`mode='adjusted'`) para cada commit alcançável pela referência e com ano da data do autor escolhido. Os arquivos estão previamente analisados por `git log --numstat -M -w`; o cache é indexado por repositório/SHA e versão do algoritmo. Não executamos `git diff` uma segunda vez para pontuar.

1. Uma alteração **gerada, de lockfile, binária, sem diferença textual ou de categoria desconhecida** não recebe crédito automático. Ela continua presente nos dados históricos para inspeção.
2. Para cada arquivo elegível: `linhas_limitadas = min(adições + remoções ajustadas, 120)`. Os pesos iniciais são **1,00 código-fonte**, **0,85 testes** e **0,65 documentação**. **São hipóteses de calibração**, não valores cientificamente comprovados.
3. Por commit, some os créditos por arquivo e limite a **150 linhas ponderadas**, independentemente do número de arquivos. `credito_commit = ln(1 + min(soma,150)) / ln(151)`. Cada commit material contribui no máximo 1 unidade de crédito técnico.
4. Agregue as unidades por contribuinte, com identidades Git normalizadas/associadas no catálogo local. A visualização mostra até 20 arquivos de maior peso por contribuinte com repositório, SHA, caminho, categoria e linhas; a rastreabilidade **integral** permanece no SQLite.
5. Aplique os percentis e pesos da política versionada. Uma reindexação da mesma referência e da mesma versão do método deve preservar o score, salvo alteração em identidade, política, escopo ou evidências de PRs.

**Exemplo:** 8.000 commits que só geram lockfiles/cosmética recebem **zero crédito material de diff**. Já centenas de commits com modificações reais em código, testes ou documentação produzem crédito; grandes mudanças são limitadas por arquivo e commit. Isso **não permite afirmar** que o segundo desenvolvedor entregou mais valor de negócio ou código de maior qualidade.

**Cobertura e deduplicação:** uma análise de clone raso é recusada, pois a profundidade insuficiente pode ocultar commits antigos. Quando múltiplas referências do mesmo repositório são selecionadas por consumidores da API, o mesmo SHA é contado somente uma vez nos indicadores anuais e no ICE-Git; repositórios distintos permanecem independentes. Sem referências selecionadas, os scores são indisponíveis.

## Confiabilidade e comparabilidade

- **Cobertura Git:** exige indexação integral do histórico alcançável das refs escolhidas. Se a ref mudar, a interface suspende o score até indexar novamente.
- **Identidades:** múltiplos e-mails Git do mesmo profissional devem ser associados explicitamente. Squash e pair programming podem atribuir incorretamente trabalhos de outras pessoas.
- **Coorte:** comparar apenas profissionais de função, contexto, regime, disponibilidade e oportunidades semelhantes. P75 é relativo: **não compare ICE de anos, squads ou filtros distintos** sem congelar a mesma referência e o mesmo universo.
- **Incentivos:** alteração mínima artificial de testes/docs e fragmentação de commits podem afetar S/E/T; o índice não é à prova de manipulação. Não utilizar isoladamente para promoções, remuneração, ranking disciplinar ou avaliação de RH.
- **Diferenças que escapam ao Git:** o ajuste `-w` pode ocultar mudança semântica de indentação em Python; renomeações, arquivos binários, mudanças fora da branch integrada, revisão de arquitetura, suporte a incidentes e qualidade não textual podem não receber crédito.
- **PRs:** o índice ampliado é N/D na ausência de snapshots completos e mapeamento explícito; sua referência P75 é calculada somente sobre o subgrupo com dados completos.
- **Segurança:** caminhos de arquivos, e-mails, SHAs, mensagens e metadados no SQLite/exports podem ser confidenciais. Preserve as permissões locais e não envie os relatórios brutos a terceiros sem revisão.

## Contrato portável (sem Git, SQLite ou Streamlit)

O módulo **`gitinsights.ice_score.score_cohort`** é uma função pura de biblioteca padrão Python. Quem tiver dados derivados em outro sistema pode passá-los em JSON, usando esta interface:

```python
from gitinsights.ice_score import ICEPolicy, score_cohort

rows = [
    {"email": "dev-a@example.org", "author": "Developer A", "commits": 1000,
     "material_commits": 700, "bounded_diff_credit": 415.2,
     "supported_commits": 105, "merged_prs": None, "reviews_submitted": None},
    # ... pelo menos duas outras identidades do mesmo grupo
]
result = score_cohort(rows, policy=ICEPolicy())
```

Para uso direto no projeto, sem importar UI:

```python
from gitinsights.incremental import MetricsStore
from gitinsights.ice_score import score_annual_store

with MetricsStore(".git-insights-data/annual-metrics.sqlite3") as store:
    report = score_annual_store(store, [("repo-id-do-catalogo", "refs/heads/main")], 2026)
```

O adaptador **`score_annual_store`** lê o snapshot SQLite já existente e constrói os sinais a partir dos diffs reais. Sem GitHub CLI, o ICE-Git permanece disponível; o ampliado retorna N/D. Não migra o esquema de banco atual.

**Arquivos de referência:** [política em JSON](../ice-git-policy.json), [exemplo de entrada em JSON](../ice-git-example.json), [implementação](../../gitinsights/ice_score.py), [testes](../../tests/test_ice_score.py). Os nomes do objeto JSON (`methodology`, `contributors`, `components`, `references`, `file_evidence`) compõem a saída pública **`ICE-Git/1`**; mudanças semânticas exigem uma nova versão da metodologia.

### Uso como CLI offline

```sh
python -m scripts.score_ice_json --input docs/ice-git-example.json --policy docs/ice-git-policy.json --out ice-result.json
```

A opção `--collaboration-complete` só deve ser usada quando a fonte externa comprovar cobertura **completa** e mapeamentos corretos; a CLI não valida autonomamente essa evidência. O arquivo de saída **não sobrescreve** um existente; sem `--out`, JSON é impresso em stdout. Nenhum processamento Git/rede é feito pela CLI.

## Evolução futura

Para transformar o índice em uma avaliação mais próxima de **impacto comprovado**, seriam necessários vínculos com issues aceitas, resultados de CI, regressões atribuídas com causalidade, indicadores técnicos/negócio por entrega e avaliação contextual. Esses dados **não podem ser inferidos de forma confiável por quantidade de linhas**. Nesse estágio, o ICE-Git deve continuar identificado como instrumento exploratório de evidências, não como medição objetiva de produtividade.
