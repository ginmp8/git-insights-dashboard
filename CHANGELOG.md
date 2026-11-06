# Histórico

Notas detalhadas por versão: [releases/README.md](releases/README.md).

## 0.3.0 — candidata, branch feature/0.3.0-incremental-metrics (não publicada)\n\n- Novo **ICE-Git/1** por contribuidor: índices relativos Git (0–100), dimensões de entrega integrada, diffs técnicos com crédito limitado por arquivo/commit e sinais de testes/docs; modalidade ampliada opcional com PRs/revisões GitHub completos e mapeados, rastreabilidade por SHA, policy JSON, API e CLI reutilizável. Não representa medida objetiva de produtividade.

- Nova aba **Contribuição anual** com cobertura integral dos commits alcançáveis por referência Git selecionada, indicadores por desenvolvedor, evolução mensal e exportação CSV/JSON.
- Cache persistente e incremental em SQLite: dados por SHA, arquivos, métricas e membresia de refs; mudanças de identidade `.mailmap` e rebases reconciliados sem recalcular diffs antigos.
- Lotes Git para churn bruto, detecção de moves `-M` e ajustes `-M -w`; categorias de código/testes/docs/gerados e taxas descritivas.
- Integração voluntária de PRs/revisões via GitHub CLI com mapeamento manual e explícito de identidades.
- Limitações: não existe pontuação objetiva de produtividade; revisões/PRs podem estar indisponíveis e o classificador lexical da aba detalhada não garante cobertura anual.
- Evidência: [VALIDATION-0.3.0.md](VALIDATION-0.3.0.md). Notas: [releases/0.3.0.md](releases/0.3.0.md).

## 0.2.0 — 2026-11-05

- Adicionada descoberta de repositórios acessíveis via GitHub CLI (próprios, colaboração e organizações), com paginação, filtros e importação em lote; não é necessário copiar URLs ou confirmar cada clone individualmente.
- Clones selecionados usam `gh auth git-credential` como helper temporário, sem escrever credenciais em URLs nem alterar `git config --global`.
- Nova aba **Mudanças ajustadas** com detecção de arquivos renomeados/movidos, churn bruto versus `-M` e `-M -w`, arquivos de teste alterados e suspeitas lexicais de troca consistente de identificadores.
- Detalhes antigo → novo dos movimentos, exportação JSON, amostragem explícita e escopo de alterações respeitando filtros.
- Mantidos o catálogo e as métricas históricas existentes; não há migração destrutiva.
- Limites: classificadores são heurísticos; não inferem contribuição real ou qualidade de código, e `-w` pode ocultar alterações semânticas de indentação.

## 0.1.0

- Dashboard Streamlit local de múltiplos repositórios, commits, autores, hotspots, comparação de branches e consultas opcionais de PRs.
