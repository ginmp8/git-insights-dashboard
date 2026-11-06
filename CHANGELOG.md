# Histórico

## 0.2.0 — 2026-11-05

- Adicionada descoberta de repositórios acessíveis via GitHub CLI (próprios, colaboração e organizações), com paginação, filtros e importação em lote; não é necessário copiar URLs ou confirmar cada clone individualmente.
- Clones selecionados usam `gh auth git-credential` como helper temporário, sem escrever credenciais em URLs nem alterar `git config --global`.
- Nova aba **Mudanças ajustadas** com detecção de arquivos renomeados/movidos, churn bruto versus `-M` e `-M -w`, arquivos de teste alterados e suspeitas lexicais de troca consistente de identificadores.
- Detalhes antigo → novo dos movimentos, exportação JSON, amostragem explícita e escopo de alterações respeitando filtros.
- Mantidos o catálogo e as métricas históricas existentes; não há migração destrutiva.
- Limites: classificadores são heurísticos; não inferem contribuição real ou qualidade de código, e `-w` pode ocultar alterações semânticas de indentação.

## 0.1.0

- Dashboard Streamlit local de múltiplos repositórios, commits, autores, hotspots, comparação de branches e consultas opcionais de PRs.
