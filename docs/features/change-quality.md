# Mudanças ajustadas: interpretar alterações com cautela

O churn bruto pode contar como trabalho novo milhares de linhas que foram apenas movidas entre diretórios. A aba **Mudanças ajustadas** preserva essa métrica histórica e apresenta diagnósticos adicionais, **sem transformar o resultado em uma nota de produtividade**.

## Como usar

1. Aplique filtros de repositório, autor, branch, pasta e período.
2. Abra **Mudanças ajustadas**.
3. Selecione uma amostra de **25, 100, 250 ou 500 commits** (padrão: 100).
4. Clique em **Calcular métricas ajustadas (Git local)**.
5. Compare os valores por autor e commit, inspecione os caminhos antigo/novo e exporte o diagnóstico JSON.

O relatório mostra explicitamente a cobertura da amostra. Nunca compare amostras desiguais como se representassem todo o histórico.

## Indicadores disponíveis

| Indicador | Interpretação correta |
|---|---|
| Churn bruto | Linhas adicionadas + removidas no log original, sem reconhecimento de renomeações. |
| Com rename (-M) | Diff Git com tentativa de reconhecer arquivo movido/renomeado por similaridade (limiar usual: 50%). |
| Ignorando espaços (-M -w) | Diff textual que ignora diferenças de whitespace; **pode ocultar alterações funcionais de indentação em Python**. |
| Renomes/moves detectados | Pares de caminho antigo → caminho novo, com similaridade reportada pelo Git. |
| Possíveis renomes de identificador | Candidatos detectados por substituição lexical consistente de tokens. Não prova equivalência semântica. |
| Arquivos de teste alterados | Presença de arquivos com nomes/pastas associados a testes; não comprova que testes foram executados. |

## O que não se pode concluir

- Movimentação com churn ajustado zero não equivale automaticamente a contribuição sem valor.
- Uma renomeação de variável pode alterar contratos públicos, escopo, resolução de nomes, segurança ou comportamento.
- Formatação pode afetar programas sensíveis a espaços.
- Muito churn pode corresponder a trabalho relevante; pouco churn pode corrigir um defeito crítico.

Para avaliar resultados de engenharia, combine a leitura dos diffs com PRs revisados e mesclados, evidência de CI/testes, regressões corrigidas e impacto observado da mudança. O dashboard **não calcula uma métrica validada de contribuição efetiva**.

A análise lê diffs locais sob demanda e pode ficar lenta com amostras grandes. A inspeção lexical também tem limites de tamanho e quantidade de arquivos.

**Código de referência:** [gitinsights/change_quality.py](../../gitinsights/change_quality.py), [gitinsights/ui_change_quality.py](../../gitinsights/ui_change_quality.py), [tests/test_change_quality.py](../../tests/test_change_quality.py).
