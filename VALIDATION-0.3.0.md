# Validation — Git Insights Dashboard 0.3.0 (candidata)

## Escopo e baseline

Baseline importada do código publicado na 0.2.0: **27 testes passaram** antes das mudanças, em Python 3.13.5, Git 2.47.3, Linux. Branch de implementação `feature/0.3.0-incremental-metrics`, a partir da main `5c54ea3942e1a094d1dc0fc5d729069010d30c0e`.

## Aceitação e observações

- **Indexação completa:** relatório anual lê todos os SHAs alcançáveis pela referência, sem usar amostragem de 500 commits; dados por ano e desenvolvedor.
- **Incremental:** segunda execução reprocessa zero SHAs antigos; alterações adicionam apenas novos SHAs, e referências reescritas removem os commits órfãos dos relatórios sem apagar cache.
- **Persistência:** reiniciar a aplicação mantém métricas; dados armazenados em SQLite local.
- **Correção de medidas:** fixture Git real cobre move puro R100, whitespace, código, arquivos de teste, lockfiles e nomes incomuns.
- **Identidade e colaboração:** os autores por e-mail podem ser associados manualmente a e-mail canônico e login GitHub; PRs e revisões só são atribuídos quando ambos o login e snapshot estiverem disponíveis.
- **Falhas:** interrupção de lote preserva o último snapshot completo. O teste headless de UI também verifica que um novo commit na branch torna o snapshot antigo explicitamente desatualizado, sem alegar 100% de cobertura atual.

## Checks executados

- `[passed]` 27 testes baseline existentes, antes da implementação.
- `[passed]` Testes novos de indexação, integridade, reprocessamento, PRs e interface red antes da implementação; suite final: **40 passed**.
- `[passed]` `python -m compileall -q app.py gitinsights scripts tests`.
- `[passed]` `python scripts/benchmark_annual.py --commits 50000 --authors 50 --heavy-author-commits 8000 --repeat 3` em um repositório Git sintético, **50.000/50.000 commits, 50 autores**.
- `[passed]` A primeira indexação gerou 50.000 novos commits; duas seguintes processaram **0 novos commits** e reutilizaram 50.000 cada.

### Benchmark sintético (Linux, Python 3.13.5, Git 2.47.3)

| Execução | Tempo | Novos SHAs | SHAs reutilizados |
|---|---:|---:|---:|
| Primeira indexação | 14,662 s | 50.000 | 0 |
| Segunda | 1,522 s | 0 | 50.000 |
| Terceira | 1,490 s | 0 | 50.000 |

Tamanho SQLite no final: **83.120.128 bytes** (~79,3 MiB). Os dados simulam um arquivo Python pequeno modificado por commit, sem a distribuição de tamanho/complexidade de repositórios reais. As três execuções foram sequenciais (1 inicial e 2 com cache), **não** são repetições independentes de ambas as condições. Portanto não constituem benchmark estatístico comparativo nem promessa de desempenho em produção.

## Verificações não executadas

- `[not run]` Interface Streamlit real no navegador (Streamlit indisponível no sandbox; houve somente smoke test headless de UI).
- `[not run]` GitHub CLI real, SSO, repositórios privados e coleta real de revisões/PRs (gh indisponível no sandbox).
- `[not run]` Windows e macOS; scripts de inicialização foram preservados.
- `[not run]` Benchmark em repositórios reais de produção, carga de memória, histórico com múltiplos arquivos grandes ou tempo de indexação em armazenamento de rede.

**Regra de interpretação:** a cobertura Git anual de 100% é relativa à referência e ao ano selecionados. Dados de PRs não têm cobertura garantida sem inspeção do snapshot. Nenhum indicador valida produtividade individual ou qualidade sem contexto externo.
