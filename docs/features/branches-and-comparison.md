# Branches e comparação

## Histórico disponível

A aba **Branches** mostra referências locais e referências remotas que já estão presentes no clone, seus SHAs, atividade e contagem de commits alcançáveis.

A opção **Todas as branches (sem duplicar commits)** usa o conjunto de commits alcançáveis das referências locais conhecidas; um commit compartilhado por duas branches é contado uma vez na visão consolidada. Ao escolher uma branch específica, os commits ficam limitados ao histórico alcançável a partir dela.

**Importante:** o dashboard não faz fetch em segundo plano. Branches que ainda não foram buscadas não aparecem. A contagem individual por branch pode repetir commits entre branches; não some esses totais.

## Comparar duas branches

1. Na aba **Branches**, selecione o repositório.
2. Defina **Base** e **Destino**.
3. Clique em **Comparar branches (somente leitura)**.

O resultado inclui divergência **ahead/behind** e os arquivos alterados no diff de três pontos (base...destino), calculado a partir do merge-base. Esse diff não é a soma do churn de cada commit. A tabela de arquivos é limitada a até **500** entradas; o dashboard indica quando é truncada.

O comparador de branches usa diff de arquivos **sem reconhecimento de renomeações** nesta versão. Para identificar movimentações e mudanças cosméticas em commits, utilize a aba [Mudanças ajustadas](change-quality.md).

## Situações de atenção

- Quando uma branch está ausente de um repositório selecionado, o histórico desse repositório é ignorado naquele filtro e um aviso é exibido.
- Branches divergentes podem apresentar commits exclusivos de ambos os lados.
- A comparação é local e de leitura; não executa checkout, merge ou rebase.

**Código de referência:** [gitinsights/git_engine.py](../../gitinsights/git_engine.py) e [app.py](../../app.py).
