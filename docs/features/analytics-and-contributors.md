# Dashboard, contribuidores, arquivos e exportação

## Abas da interface

- **Visão geral:** totais e evolução de commits, contribuições e movimento histórico de linhas por repositório.
- **Contribuidores:** ranking por commits e alterações, distribuição de atividade por dia/hora e participação nos repositórios.
- **Arquivos:** hotspots, churn por arquivo, tipos de arquivo e frequência de mudanças.
- **Commits e exportação:** histórico navegável, relatório JSON e tabela CSV.

As outras abas são [Mudanças ajustadas](change-quality.md), [Branches](branches-and-comparison.md) e [Pull requests](github-integration.md).

## Métricas

| Indicador | O que significa |
|---|---|
| Commits | Quantidade de commits no escopo carregado; commits compartilhados por branches são deduplicados na visão consolidada do repositório. |
| Adições / remoções | Linhas registradas pelo histórico Git, não tamanho atual do código. |
| Churn bruto | Adições + remoções. Movimentações de arquivos podem inflar este indicador. |
| Hotspot | Arquivo alterado com frequência; não prova defeito, complexidade ou dívida técnica. |
| Contribuidores | Agrupamento por e-mail Git de autor após .mailmap quando disponível; diferentes e-mails da mesma pessoa ainda podem aparecer separados. |

Commits de merge contam na quantidade de commits, mas não nas somas de alterações de linhas. Arquivos binários não adicionam contagens numéricas de linhas. O período utiliza os timestamps fornecidos pelo Git; fusos diferentes influenciam o mapa de horas.

## Filtros e cobertura

A seleção de repositório, branch, autor, período, pasta global e pasta específica por repositório é combinável. O filtro de pasta restringe os arquivos usados nos cálculos de churn e hotspots. A ingestão inicia com o limite de **5.000 commits por repositório**; o usuário pode escolher outros limites ou **Sem limite**, com custo maior de processamento.

## Exportações

O JSON contém métricas agregadas e até 200 commits recentes. O CSV exporta até 1.000 commits; os totais usam todo o conjunto carregado. A saída CSV inclui proteção contra fórmulas interpretadas por planilhas.

**Não use o ranking de churn como avaliação de produtividade individual.** Consulte a [interpretação de mudanças ajustadas](change-quality.md).

**Código de referência:** [métricas](../../gitinsights/analytics.py), [exportação](../../gitinsights/export.py) e [interface](../../app.py).
